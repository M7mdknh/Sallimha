"""One image, one origin (ADR-0004): the built console is served by the API container."""

from django.test import Client


def _dist(tmp_path):
    (tmp_path / "assets").mkdir()
    (tmp_path / "index.html").write_text("<!doctype html><title>Sallimha console</title>")
    (tmp_path / "assets" / "app.js").write_text("console.log('ok')")
    return tmp_path


def test_client_routes_get_the_console_and_api_paths_do_not(settings, tmp_path, db):
    settings.CONSOLE_DIST = _dist(tmp_path)
    client = Client()
    page = client.get("/events/5/tickets/9")
    assert page.status_code == 200 and b"Sallimha console" in page.content
    assert page["Cache-Control"] == "no-store"
    assert client.get("/api/does-not-exist").status_code == 404
    assert b"Sallimha console" not in client.get("/api/does-not-exist").content
    assert client.post("/events/5").status_code == 405  # console routes are read-only pages


def test_built_assets_are_served_from_the_same_origin(settings, tmp_path, db):
    settings.CONSOLE_DIST = _dist(tmp_path)
    settings.WHITENOISE_ROOT = str(tmp_path)
    asset = Client().get("/assets/app.js")
    assert asset.status_code == 200 and b"console.log" in b"".join(asset.streaming_content)


def test_the_served_app_lets_the_parking_map_and_geolocation_work(settings, tmp_path, db):
    """ADR-0013. A website-restricted Maps key is checked against the Referer, so cross-site requests must carry the
    origin (never the path, which holds ticket ids). Nothing may switch geolocation off for the app's own pages."""
    settings.CONSOLE_DIST = _dist(tmp_path)
    page = Client().get("/work")
    assert page["Referrer-Policy"] == "strict-origin-when-cross-origin"
    assert "geolocation=()" not in page.get("Permissions-Policy", "")
    assert "Content-Security-Policy" not in page or "maps.googleapis.com" in page["Content-Security-Policy"]
