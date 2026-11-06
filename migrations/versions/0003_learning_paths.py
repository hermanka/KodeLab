"""Versioned learning paths, pinned enrollments and server-owned completions."""
from alembic import op
import sqlalchemy as sa

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("learning_paths",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("course_id", sa.String(36), sa.ForeignKey("courses.id"), nullable=False),
        sa.Column("published_version_id", sa.String(36)),
        sa.Column("archived", sa.Boolean(), nullable=False))
    op.create_index("ix_learning_paths_course_id", "learning_paths", ["course_id"])
    op.create_table("path_versions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("path_id", sa.String(36), sa.ForeignKey("learning_paths.id"), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("edit_revision", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("languages", sa.JSON(), nullable=False),
        sa.Column("sequential", sa.Boolean(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.UniqueConstraint("path_id", "revision", name="uq_path_revision"))
    op.create_table("path_steps",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("path_version_id", sa.String(36), sa.ForeignKey("path_versions.id"), nullable=False),
        sa.Column("key", sa.String(80), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("module", sa.String(120), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("kind", sa.String(20), nullable=False),
        sa.Column("required", sa.Boolean(), nullable=False),
        sa.Column("prerequisites", sa.JSON(), nullable=False),
        sa.Column("lesson_version_id", sa.String(36), sa.ForeignKey("lesson_versions.id")),
        sa.Column("problem_version_id", sa.String(80), sa.ForeignKey("problem_versions.id")),
        sa.UniqueConstraint("path_version_id", "key", name="uq_path_step_key"),
        sa.UniqueConstraint("path_version_id", "position", name="uq_path_step_position"))
    op.create_index("ix_path_steps_path_version_id", "path_steps", ["path_version_id"])
    op.create_table("path_enrollments",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("path_id", sa.String(36), sa.ForeignKey("learning_paths.id"), nullable=False),
        sa.Column("path_version_id", sa.String(36), sa.ForeignKey("path_versions.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("user_id", "path_id", name="uq_user_path_enrollment"))
    op.create_index("ix_path_enrollments_user_id", "path_enrollments", ["user_id"])
    op.create_table("step_completions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("enrollment_id", sa.String(36), sa.ForeignKey("path_enrollments.id"), nullable=False),
        sa.Column("step_id", sa.String(36), sa.ForeignKey("path_steps.id"), nullable=False),
        sa.Column("attempt_id", sa.String(36), sa.ForeignKey("judging_attempts.id")),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("enrollment_id", "step_id", name="uq_enrollment_completion"))
    op.create_index("ix_step_completions_enrollment_id", "step_completions", ["enrollment_id"])
    for column, target in (("enrollment_id", "path_enrollments"), ("path_step_id", "path_steps")):
        op.add_column("submissions", sa.Column(column, sa.String(36)))
        op.create_foreign_key("fk_submission_" + column, "submissions", target, [column], ["id"])


def downgrade():
    raise RuntimeError("Restore a verified backup to revert learning history")
