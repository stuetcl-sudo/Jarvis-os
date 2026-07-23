import os
import re
import tempfile
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from app import config, home_setup
from app.auth.service import auth_service, initialize_auth_tables
from app.db import init_db
from app.main_auth import app
from app.setup_state import setup_status

ROOT = Path(__file__).resolve().parents[1]


def credential():
    return "".join(["Family", "View", "Pass", "-42!"])


@contextmanager
def environment():
    previous = config.DB_PATH
    with tempfile.TemporaryDirectory() as folder, patch.dict(
        os.environ,
        {
            "HOME_ASSISTANT_URL": "http://home-assistant.example.com:8123",
            "HOME_ASSISTANT_" + "TOKEN": "example-token",
        },
    ):
        config.DB_PATH = str(Path(folder) / "family.db")
        init_db()
        initialize_auth_tables()
        client = TestClient(app, follow_redirects=False)
        try:
            yield client
        finally:
            client.close()
            config.DB_PATH = previous


def create_and_login(client, role, display_name):
    username = f"family-{role}"
    auth_service.create_user(username, display_name, role, credential())
    response = client.post(
        "/api/auth/login",
        json={"username": username, "password": credential()},
    )
    assert response.status_code == 200, response.text


def complete_ready_setup():
    home_setup.save_home_settings(
        "Example home", "Europe/Copenhagen", "Example owner", db_path=config.DB_PATH
    )
    home_setup.complete_setup(db_path=config.DB_PATH)
    assert setup_status(db_path=config.DB_PATH)["state"] == "ready"


def assert_no_technical_presentation(text):
    for marker in [
        "Sikker tilstand",
        "Docker-systemer online",
        "Aktive hændelser",
        'data-family-section="technical-status"',
        'data-family-section="technical-system"',
        "<dt>CPU</dt>",
        "<dt>Hukommelse</dt>",
        "<dt>Disk</dt>",
    ]:
        assert marker not in text


def test_anonymous_family_view_is_public_and_non_technical():
    with environment() as client:
        response = client.get("/")
        assert response.status_code == 200
        text = response.text
        assert 'data-family-role="anonymous"' in text
        assert 'data-family-display-name=""' in text
        assert "Fælles overblik" in text
        assert 'href="/login">Log ind</a>' in text
        assert 'href="/admin"' not in text
        assert "Mission Control" not in text
        assert "Ikke tilsluttet endnu" in text
        assert_no_technical_presentation(text)


def test_owner_family_view_is_personalized_and_may_be_technical():
    with environment() as client:
        display_name = '<Ejer & "Hjem">'
        create_and_login(client, "owner", display_name)
        text = client.get("/").text
        assert 'data-family-role="owner"' in text
        assert "Familiens overblik" in text
        assert display_name not in text
        assert '&lt;Ejer &amp; &quot;Hjem&quot;&gt;' in text
        assert 'href="/admin">Administration</a>' in text
        assert "Mission Control" not in text
        assert 'href="/login">Skift bruger</a>' in text
        assert 'data-family-section="technical-status"' in text
        assert "<dt>CPU</dt>" in text and "<dt>Hukommelse</dt>" in text and "<dt>Disk</dt>" in text


def test_adult_family_view_is_personalized_without_technical_details():
    with environment() as client:
        create_and_login(client, "adult", "Voksen Test")
        text = client.get("/").text
        assert 'data-family-role="adult"' in text
        assert 'data-family-display-name="Voksen Test"' in text
        assert "Familiens dag" in text
        assert 'href="/login">Skift bruger</a>' in text
        assert 'href="/admin"' not in text
        for card in ["calendar", "weather", "home", "meal", "tasks"]:
            assert f'data-family-card="{card}"' in text
        assert_no_technical_presentation(text)


def test_child_family_view_prioritizes_day_cards_without_technical_details():
    with environment() as client:
        create_and_login(client, "child", "Barn Test")
        text = client.get("/").text
        assert 'data-family-role="child"' in text
        assert 'data-family-display-name="Barn Test"' in text
        assert "Din dag" in text
        assert 'href="/login">Skift bruger</a>' in text
        assert 'href="/admin"' not in text
        positions = [text.index(f'data-family-card="{card}"') for card in ["calendar", "weather", "meal", "tasks"]]
        assert positions == sorted(positions)
        assert 'data-family-card="home"' not in text
        assert "Madplan" in text and "Lektier og opgaver" in text
        assert_no_technical_presentation(text)


def test_wall_display_is_shared_kiosk_without_personal_name():
    with environment() as client:
        create_and_login(client, "wall_display", "Skjult Skærmnavn")
        text = client.get("/").text
        assert 'data-family-role="wall_display"' in text
        assert 'data-family-view="shared-display"' in text
        assert 'data-family-kiosk="true"' in text
        assert 'data-family-display-name=""' in text
        assert "Fælles husholdningsskærm" in text
        assert "Skjult Skærmnavn" not in text
        assert 'href="/login">Skift bruger</a>' in text
        assert 'href="/admin"' not in text
        for card in ["calendar", "weather", "home", "meal", "tasks"]:
            assert f'data-family-card="{card}"' in text
        assert_no_technical_presentation(text)


def test_role_cannot_be_changed_by_query_and_invalid_role_falls_back():
    with environment() as client:
        anonymous = client.get("/?role=owner&display_name=Injected")
        assert 'data-family-role="anonymous"' in anonymous.text
        assert "Injected" not in anonymous.text
        assert 'href="/admin"' not in anonymous.text

        client.cookies.set("jarvis_session", "invalid-role-fixture")
        invalid_user = {"username": "invalid", "display_name": "Should Not Render", "role": "administrator"}
        with patch.object(auth_service, "resolve_session", return_value=invalid_user):
            invalid = client.get("/?role=owner")
        assert 'data-family-role="anonymous"' in invalid.text
        assert "Should Not Render" not in invalid.text
        assert 'href="/admin"' not in invalid.text


def test_family_frontend_is_safe_read_only_and_admin_boundary_is_unchanged():
    javascript = (ROOT / "app/static/js/family.js").read_text()
    assert "textContent" in javascript
    assert "innerHTML" not in javascript
    assert "localStorage" not in javascript
    assert "sessionStorage" not in javascript
    assert not re.search(r"\b(POST|PUT|PATCH|DELETE)\b", javascript, re.IGNORECASE)
    assert "method:" not in javascript
    assert "URLSearchParams" not in javascript
    assert "location.hash" not in javascript

    with environment() as client:
        assert client.get("/admin").status_code == 303
        create_and_login(client, "adult", "Voksen Test")
        assert client.get("/admin").status_code == 403

    with environment() as client:
        create_and_login(client, "owner", "Ejer Test")
        complete_ready_setup()
        assert client.get("/admin").status_code == 200


if __name__ == "__main__":
    for test in [
        test_anonymous_family_view_is_public_and_non_technical,
        test_owner_family_view_is_personalized_and_may_be_technical,
        test_adult_family_view_is_personalized_without_technical_details,
        test_child_family_view_prioritizes_day_cards_without_technical_details,
        test_wall_display_is_shared_kiosk_without_personal_name,
        test_role_cannot_be_changed_by_query_and_invalid_role_falls_back,
        test_family_frontend_is_safe_read_only_and_admin_boundary_is_unchanged,
    ]:
        test()
    print("Family role view tests OK")
