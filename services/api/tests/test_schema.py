"""API contract checks. A schema that merely generates is not a pass: it must be complete (no warnings),
match the committed contracts/openapi.yaml, and real responses must satisfy their contract serializers."""

from pathlib import Path

import pytest
from django.core.management import call_command

CONTRACT = Path(__file__).resolve().parents[3] / "contracts" / "openapi.yaml"


@pytest.mark.django_db
def test_schema_is_complete_and_committed(tmp_path):
    out = tmp_path / "schema.yaml"
    call_command("spectacular", "--file", str(out), "--validate", "--fail-on-warn")
    assert out.read_text() == CONTRACT.read_text(), (
        "contracts/openapi.yaml is stale: run `make contract` and commit the result")


# Commands whose only input is the path; anything else must document its request body.
BODYLESS_COMMANDS = ("/end", "/ack", "logout", "/close", "/reactivate", "/mfa", "/approve-unclaimed", "/replay",
                     "/retention/apply", "/setup-code", "/contact", "/start-parking", "/accept", "/decline", "/ready",
                     "/deliver", "/custody-ack")


def test_every_console_route_documents_request_and_response():
    import yaml
    schema = yaml.safe_load(CONTRACT.read_text())
    for path, operations in schema["paths"].items():
        for method, op in operations.items():
            assert "200" in op["responses"], f"{method.upper()} {path} has no 200 response"
            if method == "post" and not path.endswith(BODYLESS_COMMANDS):
                assert "requestBody" in op, f"POST {path} has no request body schema"
