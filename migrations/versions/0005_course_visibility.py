"""Class descriptions/settings and revocable six-digit invitations."""
from alembic import op
import sqlalchemy as sa

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("courses", sa.Column("description", sa.Text(), nullable=False, server_default=""))
    op.add_column("courses", sa.Column("edit_revision", sa.Integer(), nullable=False, server_default="1"))
    op.add_column("courses", sa.Column("invite_digest", sa.String(64), nullable=True))
    op.add_column("courses", sa.Column("invite_expires_at", sa.DateTime(), nullable=True))
    op.create_unique_constraint("uq_course_invite_digest", "courses", ["invite_digest"])


def downgrade():
    op.drop_constraint("uq_course_invite_digest", "courses", type_="unique")
    for name in ("invite_expires_at", "invite_digest", "edit_revision", "description"):
        op.drop_column("courses", name)
