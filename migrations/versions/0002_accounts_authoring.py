"""Accounts, ownership, content versions, reference validation and audit.

Legacy submissions retain NULL owners and are accessible only to administrators.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.mysql import MEDIUMTEXT

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("users",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("username", sa.String(40), nullable=False, unique=True),
        sa.Column("password_hash", sa.Text(), nullable=False),
        sa.Column("role", sa.String(20), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False))
    op.create_table("auth_sessions",
        sa.Column("token_hash", sa.String(64), primary_key=True),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("csrf_hash", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("last_seen", sa.DateTime(), nullable=False))
    op.create_index("ix_auth_sessions_user_id", "auth_sessions", ["user_id"])
    op.create_table("audit_events",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("actor_id", sa.String(36), sa.ForeignKey("users.id")),
        sa.Column("action", sa.String(80), nullable=False),
        sa.Column("object_id", sa.String(80), nullable=False),
        sa.Column("details", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False))
    op.create_index("ix_audit_events_action", "audit_events", ["action"])
    op.create_table("rate_buckets",
        sa.Column("key", sa.String(64), primary_key=True),
        sa.Column("window_start", sa.DateTime(), nullable=False),
        sa.Column("count", sa.Integer(), nullable=False))
    op.create_table("quota_locks", sa.Column("id", sa.String(40), primary_key=True))
    op.create_table("courses",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("owner_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("is_public", sa.Boolean(), nullable=False),
        sa.Column("provider", sa.String(30)))
    op.create_table("course_members",
        sa.Column("course_id", sa.String(36), sa.ForeignKey("courses.id"), primary_key=True),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id"), primary_key=True),
        sa.Column("role", sa.String(20), nullable=False))
    op.create_table("lessons",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("course_id", sa.String(36), sa.ForeignKey("courses.id"), nullable=False),
        sa.Column("published_version_id", sa.String(36)),
        sa.Column("archived", sa.Boolean(), nullable=False))
    op.create_table("lesson_versions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("lesson_id", sa.String(36), sa.ForeignKey("lessons.id"), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("edit_revision", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("body_markdown", sa.Text(), nullable=False),
        sa.Column("body_html", sa.Text().with_variant(MEDIUMTEXT(), "mysql"), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.UniqueConstraint("lesson_id", "revision"))
    op.create_table("problems",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("course_id", sa.String(36), sa.ForeignKey("courses.id"), nullable=False),
        sa.Column("published_version_id", sa.String(80)),
        sa.Column("archived", sa.Boolean(), nullable=False))
    op.add_column("problem_versions", sa.Column("problem_id", sa.String(36)))
    op.add_column("problem_versions", sa.Column("validation_job_id", sa.String(36)))
    op.create_foreign_key("fk_problem_version_problem", "problem_versions", "problems", ["problem_id"], ["id"])
    for name in ("revision", "edit_revision"):
        op.add_column("problem_versions", sa.Column(name, sa.Integer(), nullable=False, server_default="1"))
        op.alter_column("problem_versions", name, existing_type=sa.Integer(), server_default=None)
    op.add_column("problem_versions", sa.Column("status", sa.String(20), nullable=False, server_default="published"))
    op.alter_column("problem_versions", "status", existing_type=sa.String(20), server_default=None)
    op.create_unique_constraint("uq_problem_version_revision", "problem_versions", ["problem_id", "revision"])
    op.add_column("submissions", sa.Column("owner_id", sa.String(36)))
    op.create_foreign_key("fk_submission_owner", "submissions", "users", ["owner_id"], ["id"])
    op.create_index("ix_submissions_owner_id", "submissions", ["owner_id"])
    uniques = sa.inspect(op.get_bind()).get_unique_constraints("submissions")
    for constraint in uniques:
        if constraint["column_names"] == ["idempotency_key"]:
            op.drop_constraint(constraint["name"], "submissions", type_="unique")
    op.create_unique_constraint("uq_submission_owner_key", "submissions", ["owner_id", "idempotency_key"])
    op.create_table("reference_solutions",
        sa.Column("problem_version_id", sa.String(80), sa.ForeignKey("problem_versions.id"), primary_key=True),
        sa.Column("language", sa.String(20), primary_key=True),
        sa.Column("source", sa.Text(), nullable=False))
    op.create_table("problem_validation_jobs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("problem_version_id", sa.String(80), sa.ForeignKey("problem_versions.id"), nullable=False),
        sa.Column("actor_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("edit_revision", sa.Integer(), nullable=False),
        sa.Column("provider", sa.String(30), nullable=False),
        sa.Column("state", sa.String(30), nullable=False),
        sa.Column("valid", sa.Boolean()), sa.Column("result", sa.JSON()),
        sa.Column("retries", sa.Integer(), nullable=False),
        sa.Column("lease_token", sa.String(36)), sa.Column("lease_until", sa.DateTime()),
        sa.Column("dispatch_after", sa.DateTime(), nullable=False),
        sa.Column("error_code", sa.String(80)),
        sa.Column("created_at", sa.DateTime(), nullable=False))
    op.create_index("ix_problem_validation_jobs_state", "problem_validation_jobs", ["state"])
    op.create_index("ix_problem_validation_jobs_dispatch_after", "problem_validation_jobs", ["dispatch_after"])


def downgrade():
    # Published academic data must not be silently discarded by a generic rollback.
    raise RuntimeError("Restore a tested backup to revert this data-bearing migration")
