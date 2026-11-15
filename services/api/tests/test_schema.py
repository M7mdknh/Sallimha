import pytest
from django.core.management import call_command


@pytest.mark.django_db
def test_openapi_schema_generates(tmp_path):
    out = tmp_path / "schema.yaml"
    call_command("spectacular", "--file", str(out), "--validate")
    assert "openapi:" in out.read_text()
