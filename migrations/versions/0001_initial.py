"""Initial immutable problem versions, submissions and leased judging attempts."""
from alembic import op
import sqlalchemy as sa

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "problem_versions",
        sa.Column("id", sa.String(80), primary_key=True),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("statement", sa.Text(), nullable=False),
        sa.Column("languages", sa.JSON(), nullable=False),
        sa.Column("limits", sa.JSON(), nullable=False),
        sa.Column("provider", sa.String(30)),
        sa.Column("scoring_policy", sa.String(30), nullable=False),
        sa.Column("checker", sa.String(30), nullable=False),
    )
    op.create_table(
        "test_cases",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("problem_version_id", sa.String(80), sa.ForeignKey("problem_versions.id"), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("input", sa.Text(), nullable=False),
        sa.Column("expected", sa.Text(), nullable=False),
        sa.Column("public", sa.Boolean(), nullable=False),
        sa.UniqueConstraint("problem_version_id", "position"),
    )
    op.create_table(
        "submissions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("problem_version_id", sa.String(80), sa.ForeignKey("problem_versions.id"), nullable=False),
        sa.Column("language", sa.String(20), nullable=False),
        sa.Column("source", sa.Text(), nullable=False),
        sa.Column("mode", sa.String(10), nullable=False),
        sa.Column("custom_input", sa.Text()),
        sa.Column("idempotency_key", sa.String(36), unique=True),
        sa.Column("request_hash", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_table(
        "judging_attempts",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("submission_id", sa.String(36), sa.ForeignKey("submissions.id"), nullable=False, unique=True),
        sa.Column("provider", sa.String(30), nullable=False),
        sa.Column("snapshot", sa.JSON(), nullable=False),
        sa.Column("state", sa.String(30), nullable=False),
        sa.Column("verdict", sa.String(40)),
        sa.Column("score", sa.Integer()),
        sa.Column("result", sa.JSON()),
        sa.Column("retries", sa.Integer(), nullable=False),
        sa.Column("lease_token", sa.String(36)),
        sa.Column("lease_until", sa.DateTime()),
        sa.Column("dispatch_after", sa.DateTime(), nullable=False),
        sa.Column("error_code", sa.String(80)),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("finished_at", sa.DateTime()),
    )
    op.create_index("ix_judging_attempts_state", "judging_attempts", ["state"])
    op.create_index("ix_judging_attempts_dispatch_after", "judging_attempts", ["dispatch_after"])


def downgrade():
    op.drop_table("judging_attempts")
    op.drop_table("submissions")
    op.drop_table("test_cases")
    op.drop_table("problem_versions")
