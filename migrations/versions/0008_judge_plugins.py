"""Installable judging plugins and immutable provider revisions."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.mysql import MEDIUMTEXT

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade():
    # MariaDB DDL commits implicitly: permit resuming an interrupted additive upgrade.
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table("judge_plugins"):
        op.create_table("judge_plugins",
            sa.Column("id", sa.String(30), primary_key=True),
            sa.Column("enabled", sa.Boolean(), nullable=False, server_default="0"),
            sa.Column("active_revision", sa.String(64), nullable=False))
    if not inspector.has_table("judge_plugin_versions"):
        op.create_table("judge_plugin_versions",
            sa.Column("revision", sa.String(64), primary_key=True),
            sa.Column("plugin_id", sa.String(30), sa.ForeignKey("judge_plugins.id"), nullable=False),
            sa.Column("version", sa.String(40), nullable=False),
            sa.Column("manifest", sa.JSON(), nullable=False),
            sa.Column("source", sa.Text().with_variant(MEDIUMTEXT(), "mysql"), nullable=False),
            sa.Column("installed_at", sa.DateTime(), nullable=False),
            sa.UniqueConstraint("plugin_id", "version", name="uq_judge_plugin_version"))
    if not any(index["name"] == "ix_judge_plugin_versions_plugin_id"
               for index in sa.inspect(op.get_bind()).get_indexes("judge_plugin_versions")):
        op.create_index("ix_judge_plugin_versions_plugin_id", "judge_plugin_versions", ["plugin_id"])
    for table in ("problem_versions", "problem_validation_jobs"):
        if not any(column["name"] == "provider_revision" for column in inspector.get_columns(table)):
            op.add_column(table, sa.Column("provider_revision", sa.String(64)))


def downgrade():
    op.drop_column("problem_validation_jobs", "provider_revision")
    op.drop_column("problem_versions", "provider_revision")
    op.drop_table("judge_plugin_versions")
    op.drop_table("judge_plugins")
