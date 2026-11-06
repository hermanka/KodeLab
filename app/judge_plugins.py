"""Trusted admin packages; installation validates code without executing it."""
import ast
import base64
import binascii
import hashlib
import io
import json
import zipfile
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import Field, ValidationError, model_validator
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.auth import administrator, audit
from app.contracts import Language, StrictModel
from app.db import get_db
from app.models import (Attempt, Course, JudgePlugin, JudgePluginVersion, ProblemVersion,
                        QuotaLock, User, ValidationJob)

router = APIRouter(tags=["judging plugins"])
PACKAGE_LIMIT = 262144
RESERVED = {"custom", "domjudge"}


class PluginCapabilities(StrictModel):
    languages: list[Language] = Field(min_length=1, max_length=2)
    custom_input: bool = True

    @model_validator(mode="after")
    def unique_languages(self):
        if len(set(self.languages)) != len(self.languages):
            raise ValueError("Duplicate plugin language")
        return self


class PluginManifest(StrictModel):
    api_version: Literal[1]
    id: str = Field(pattern=r"^[a-z][a-z0-9-]{0,29}$")
    name: str = Field(min_length=1, max_length=80)
    version: str = Field(min_length=1, max_length=40, pattern=r"^[0-9]+\.[0-9]+\.[0-9]+(?:-[a-zA-Z0-9.-]+)?$")
    description: str = Field(default="", max_length=1000)
    capabilities: PluginCapabilities


class InstallPlugin(StrictModel):
    package_base64: str = Field(min_length=1, max_length=349528)
    trusted_code: Literal[True]


class PluginState(StrictModel):
    enabled: bool
    revision: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")


def read_package(encoded):
    try:
        payload = base64.b64decode(encoded, validate=True)
        if len(payload) > PACKAGE_LIMIT:
            raise ValueError("Package too large")
        with zipfile.ZipFile(io.BytesIO(payload)) as archive:
            entries = archive.infolist()
            names = [entry.filename for entry in entries]
            if (len(names) != len(set(names)) or not {"plugin.json", "plugin.py"}.issubset(names)
                    or set(names) - {"plugin.json", "plugin.py", "README.md"}
                    or sum(entry.file_size for entry in entries) > PACKAGE_LIMIT
                    or any(entry.flag_bits & 1 or entry.is_dir() or
                           ((entry.external_attr >> 16) & 0o170000) == 0o120000 for entry in entries)):
                raise ValueError("Invalid archive entries")
            manifest = PluginManifest.model_validate_json(archive.read("plugin.json"))
            source = archive.read("plugin.py").decode("utf-8")
        if manifest.id in RESERVED or not source.strip():
            raise ValueError("Reserved ID or empty code")
        tree = ast.parse(source)
        classes = [node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == "Plugin"]
        if len(classes) != 1 or not any(isinstance(node, ast.FunctionDef) and node.name == "judge" for node in classes[0].body):
            raise ValueError("A Plugin class with a synchronous judge method is required")
        data = manifest.model_dump()
        revision = hashlib.sha256((json.dumps(data, sort_keys=True) + "\n" + source).encode()).hexdigest()
        return data, source, revision
    except (ValueError, binascii.Error, zipfile.BadZipFile, RuntimeError, NotImplementedError,
            SyntaxError, ValidationError, KeyError, OSError) as exc:
        raise HTTPException(422, "Invalid plugin package: use API v1, plugin.json and plugin.py (maximum 256 KiB)") from exc


def plugin_view(db, plugin):
    versions = db.scalars(select(JudgePluginVersion).where(
        JudgePluginVersion.plugin_id == plugin.id).order_by(JudgePluginVersion.installed_at.desc(), JudgePluginVersion.version)).all()
    active = next(v for v in versions if v.revision == plugin.active_revision)
    return {"id": plugin.id, "enabled": plugin.enabled, "active_revision": plugin.active_revision,
            "name": active.manifest["name"], "description": active.manifest["description"],
            "version": active.version, "versions": [
                {"version": v.version, "revision": v.revision, "installed_at": v.installed_at.isoformat() + "Z"}
                for v in versions]}


def lock_plugins(db):
    # Same admission lock as submission/validation/deletion: changes cannot race new jobs.
    db.scalar(select(QuotaLock).where(QuotaLock.id == "admission").with_for_update())


@router.get("/admin/judge-plugins")
def list_plugins(user: User = Depends(administrator), db: Session = Depends(get_db)):
    return [plugin_view(db, p) for p in db.scalars(select(JudgePlugin).order_by(JudgePlugin.id))]


@router.post("/admin/judge-plugins", status_code=201)
def install_plugin(data: InstallPlugin, user: User = Depends(administrator), db: Session = Depends(get_db)):
    manifest, source, revision = read_package(data.package_base64)
    lock_plugins(db)
    if db.scalar(select(JudgePluginVersion).where(JudgePluginVersion.plugin_id == manifest["id"],
                                                JudgePluginVersion.version == manifest["version"])):
        raise HTTPException(409, "Plugin version already installed; use a new version number")
    plugin = db.get(JudgePlugin, manifest["id"])
    if not plugin:
        plugin = JudgePlugin(id=manifest["id"], active_revision=revision)
        db.add(plugin)
        db.flush()
    db.add(JudgePluginVersion(revision=revision, plugin_id=plugin.id, version=manifest["version"],
                              manifest=manifest, source=source))
    audit(db, user, "judge_plugin.installed", plugin.id, version=manifest["version"], revision=revision)
    db.commit()
    return plugin_view(db, plugin)


@router.patch("/admin/judge-plugins/{plugin_id}")
def configure_plugin(plugin_id: str, data: PluginState, user: User = Depends(administrator), db: Session = Depends(get_db)):
    lock_plugins(db)
    plugin = db.get(JudgePlugin, plugin_id)
    if not plugin:
        raise HTTPException(404, "Plugin not found")
    if data.revision:
        version = db.get(JudgePluginVersion, data.revision)
        if not version or version.plugin_id != plugin.id:
            raise HTTPException(422, "Plugin revision not found")
        plugin.active_revision = version.revision
    plugin.enabled = data.enabled
    audit(db, user, "judge_plugin.configured", plugin.id, enabled=plugin.enabled, revision=plugin.active_revision)
    db.commit()
    return plugin_view(db, plugin)


@router.delete("/admin/judge-plugins/{plugin_id}")
def uninstall_plugin(plugin_id: str, user: User = Depends(administrator), db: Session = Depends(get_db)):
    lock_plugins(db)
    plugin = db.get(JudgePlugin, plugin_id)
    if not plugin:
        raise HTTPException(404, "Plugin not found")
    if plugin.enabled:
        raise HTTPException(409, "Deactivate the plugin before uninstalling")
    if any(db.scalar(select(model).where(model.provider == plugin_id).limit(1)) is not None
           for model in (ProblemVersion, Course, Attempt, ValidationJob)):
        raise HTTPException(409, "Plugin is referenced by problems or judging history; keep it installed")
    db.execute(delete(JudgePluginVersion).where(JudgePluginVersion.plugin_id == plugin.id))
    db.delete(plugin)
    audit(db, user, "judge_plugin.uninstalled", plugin_id)
    db.commit()
    return {"status": "uninstalled"}
