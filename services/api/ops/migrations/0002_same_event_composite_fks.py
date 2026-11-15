from django.db import migrations

# ADR-0003 #10: rows that reference a ticket must belong to the ticket's event.
# Django's ForeignKey cannot express composite foreign keys, so they are added here.
FORWARD = """
ALTER TABLE ops_task
    ADD CONSTRAINT ops_task_same_event_ticket
    FOREIGN KEY (event_id, ticket_id) REFERENCES ops_ticket (event_id, id) DEFERRABLE INITIALLY IMMEDIATE;
ALTER TABLE ops_retrievalrequest
    ADD CONSTRAINT ops_request_same_event_ticket
    FOREIGN KEY (event_id, ticket_id) REFERENCES ops_ticket (event_id, id) DEFERRABLE INITIALLY IMMEDIATE;
"""

REVERSE = """
ALTER TABLE ops_task DROP CONSTRAINT IF EXISTS ops_task_same_event_ticket;
ALTER TABLE ops_retrievalrequest DROP CONSTRAINT IF EXISTS ops_request_same_event_ticket;
"""


class Migration(migrations.Migration):
    dependencies = [("ops", "0001_operational_model")]
    operations = [migrations.RunSQL(FORWARD, REVERSE)]
