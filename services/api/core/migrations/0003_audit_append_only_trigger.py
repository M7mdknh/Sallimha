from django.db import migrations

FORWARD = """
CREATE OR REPLACE FUNCTION core_auditevent_append_only() RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION 'core_auditevent is append-only (% blocked)', TG_OP
        USING ERRCODE = 'P0001';
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER core_auditevent_no_update_delete
    BEFORE UPDATE OR DELETE ON core_auditevent
    FOR EACH ROW EXECUTE FUNCTION core_auditevent_append_only();
"""

REVERSE = """
DROP TRIGGER IF EXISTS core_auditevent_no_update_delete ON core_auditevent;
DROP FUNCTION IF EXISTS core_auditevent_append_only();
"""


class Migration(migrations.Migration):
    dependencies = [("core", "0002_audit_idempotency")]
    operations = [migrations.RunSQL(FORWARD, REVERSE)]
