import os
import sys
import tempfile
from contextlib import nullcontext
from pathlib import Path
from types import ModuleType

from sqlalchemy import select

from app.contracts import JudgeRequest, JudgeResult
from app.db import session
from app.models import JudgePlugin, JudgePluginVersion
from app.plugin_sdk import PluginContext, ProviderUnavailable
from plugin.custom.provider import CustomProvider


class DomjudgeProvider:
    """Reserved adapter; no claim of a functioning DOMjudge integration yet."""

    def capabilities(self):
        return {"implemented": False, "languages": [], "custom_input": False,
                "test_details": False, "partial_scoring": False}

    def health_check(self):
        return False

    def prepare_problem(self, problem_version_id):
        raise ProviderUnavailable("domjudge_not_implemented")

    def submit(self, request, idempotency_key):
        raise ProviderUnavailable("domjudge_not_implemented")

    def get_result(self, reference):
        raise ProviderUnavailable("domjudge_not_implemented")


class InstalledProvider:
    def __init__(self, package, execution):
        self.revision, self.manifest, self.source = package.revision, package.manifest, package.source
        self.execution = execution

    def capabilities(self):
        return {"implemented": True, "test_details": True, "partial_scoring": False,
                **self.manifest["capabilities"]}

    def health_check(self):
        # Metadata availability only: HTTP API processes never execute installed code.
        return True

    def prepare_problem(self, problem_version_id):
        return problem_version_id

    def submit(self, request: JudgeRequest, idempotency_key: str):
        if not self.execution or idempotency_key != str(request.attempt_id):
            raise ProviderUnavailable("plugin_execution_requires_worker")
        directory = Path(__file__).resolve().parent.parent / "plugin" / "installed"
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / f"{self.revision}.py"
        # Database packages are authoritative; workers materialize atomic local copies.
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=directory, delete=False) as file:
            temporary = Path(file.name)
            file.write(self.source)
        try:
            temporary.replace(path)
        finally:
            temporary.unlink(missing_ok=True)
        module = ModuleType(f"judge_plugin_{self.revision}_{request.attempt_id.hex}")
        module.__file__ = str(path)
        sys.modules[module.__name__] = module
        try:
            exec(compile(self.source, str(path), "exec"), module.__dict__)
            plugin = module.Plugin(PluginContext())
            self._result = JudgeResult.model_validate(plugin.judge(request.model_copy(deep=True)))
        finally:
            sys.modules.pop(module.__name__, None)
        self._result.environment = f"plugin={self.manifest['id']}@{self.manifest['version']}; revision={self.revision}; {self._result.environment}"
        self._reference = idempotency_key
        return idempotency_key

    def get_result(self, reference):
        if reference != getattr(self, "_reference", None):
            raise ProviderUnavailable("unknown_plugin_reference")
        return self._result


def provider_for(name, revision=None, *, execution=False, db=None):
    registry = {"custom": CustomProvider, "domjudge": DomjudgeProvider}
    if name in registry:
        if revision is not None:
            raise ProviderUnavailable("unexpected_builtin_revision")
        return registry[name]()
    with (nullcontext(db) if db is not None else session()) as connection:
        plugin = connection.get(JudgePlugin, name)
        if not plugin or (not plugin.enabled and not (execution and revision)):
            raise ProviderUnavailable("plugin_unavailable")
        package = connection.get(JudgePluginVersion, revision or plugin.active_revision)
        if not package or package.plugin_id != name:
            raise ProviderUnavailable("plugin_revision_unavailable")
        return InstalledProvider(package, execution)


def available_providers(db):
    result = {name: {**provider_for(name).capabilities(), "healthy": provider_for(name).health_check(),
                     "name": name, "builtin": True} for name in ("custom", "domjudge")}
    for plugin in db.scalars(select(JudgePlugin).where(JudgePlugin.enabled.is_(True)).order_by(JudgePlugin.id)):
        provider = provider_for(plugin.id, db=db)
        result[plugin.id] = {**provider.capabilities(), "healthy": True, "builtin": False,
                             "name": provider.manifest["name"], "version": provider.manifest["version"],
                             "revision": provider.revision}
    return result


def choose_provider(override, problem_provider, course_provider=None):
    return override or problem_provider or course_provider or os.getenv("DEFAULT_PROVIDER", "custom")
