"""Profiles, recoverable encrypted invitations, and explicit private membership."""
from alembic import op
import sqlalchemy as sa

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("users", sa.Column("full_name", sa.String(120), nullable=False, server_default=""))
    op.add_column("users", sa.Column("email", sa.String(254), nullable=True))
    op.create_unique_constraint("uq_users_email", "users", ["email"])
    op.add_column("courses", sa.Column("invite_ciphertext", sa.Text(), nullable=True))
    op.add_column("course_members", sa.Column("access_source", sa.String(20), nullable=False, server_default="assignment"))
    # Prior public auto-enrollment is not an explicit invitation to a private class.
    connection = op.get_bind()
    members = connection.execute(sa.text("SELECT course_id,user_id,role FROM course_members")).mappings().all()
    events = connection.execute(sa.text("SELECT actor_id,action,object_id,details FROM audit_events WHERE action IN ('course.member_assigned','course.invitation_joined')")).mappings().all()
    import json
    assigned, invited = set(), set()
    for event in events:
        details = event["details"]
        if isinstance(details, str):
            details = json.loads(details)
        if event["action"] == "course.member_assigned":
            assigned.add((event["object_id"], details.get("user_id")))
        else:
            invited.add((event["object_id"], event["actor_id"]))
    for member in members:
        key = (member["course_id"], member["user_id"])
        source = "assignment" if member["role"] == "teacher" or key in assigned else "invite" if key in invited else "public"
        connection.execute(sa.text("UPDATE course_members SET access_source=:source WHERE course_id=:cid AND user_id=:uid"),
                           {"source": source, "cid": key[0], "uid": key[1]})


def downgrade():
    op.drop_column("course_members", "access_source")
    op.drop_column("courses", "invite_ciphertext")
    op.drop_constraint("uq_users_email", "users", type_="unique")
    op.drop_column("users", "email")
    op.drop_column("users", "full_name")
