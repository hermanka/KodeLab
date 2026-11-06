"""Do not treat a revoked historical assignment as a current private invitation."""
import json
from alembic import op
import sqlalchemy as sa

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade():
    connection = op.get_bind()
    events = connection.execute(sa.text("SELECT action,object_id,details,created_at FROM audit_events WHERE action IN ('course.member_assigned','course.member_removed')")).mappings().all()
    assigned, removed, authoritative = {}, {}, set()
    for event in events:
        details = event["details"]
        if isinstance(details, str):
            details = json.loads(details)
        key = (event["object_id"], details.get("user_id"))
        target = assigned if event["action"] == "course.member_assigned" else removed
        target[key] = max(target.get(key, event["created_at"]), event["created_at"])
        if details.get("access_source") == "assignment":
            authoritative.add(key)
    for key, revoked_at in removed.items():
        # Ties cannot establish order in legacy DATETIME columns; require a new
        # explicit invitation/assignment instead of granting uncertain access.
        if key not in authoritative and key in assigned and revoked_at >= assigned[key]:
            connection.execute(sa.text("UPDATE course_members SET access_source='public' WHERE course_id=:cid AND user_id=:uid AND role='student' AND access_source='assignment'"),
                               {"cid": key[0], "uid": key[1]})


def downgrade():
    # Restoring revoked access on downgrade would be unsafe; academic data is unchanged.
    pass
