from datetime import date
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app import config
from app.auth.service import auth_service, initialize_auth_tables
from app.db import connect, init_db
from app.main_auth import app

BASE = "/api/family/pets"


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DB_PATH", str(tmp_path / "pets.db"))
    init_db()
    initialize_auth_tables()
    with TestClient(app) as client:
        yield client


def login(client, role):
    auth_service.create_user(role, role, role, "Pets-Test-Password-123!")
    assert client.post("/api/auth/login", json={"username": role, "password": "Pets-Test-Password-123!"}).status_code == 200
    return {"X-CSRF-Token": client.get("/api/auth/me").json()["csrf_token"]}


def create(client, headers):
    result = client.post(BASE, headers=headers, json={"name": "Milo", "breed": "Jack Russell", "birth_date": "2020-05-01"})
    assert result.status_code == 201, result.text
    return result.json()["id"]


def test_anonymous_cannot_read_or_write(client):
    assert client.get(BASE).status_code == 401
    assert client.post(BASE, json={"name": "Milo"}).status_code == 401
    assert 'data-family-card="pets"' not in client.get("/").text


@pytest.mark.parametrize("role", ["owner", "adult"])
def test_profile_persistence_validation_and_cascade(client, role):
    headers = login(client, role)
    assert client.post(BASE, json={"name": "Milo"}).status_code == 403
    assert client.post(BASE, headers={"X-CSRF-Token":"wrong"}, json={"name":"Milo"}).status_code == 403
    pet = create(client, headers)
    assert client.put(f"{BASE}/{pet}", headers=headers, json={"name":"Milo 2", "weight_kg":7.4, "chip_number":"012345"}).status_code == 200
    init_db()  # Re-running initialization must preserve existing records.
    saved = client.get(BASE).json()["pets"][0]
    assert saved["name"] == "Milo 2" and saved["weight_kg"] == 7.4
    for payload in [{"name":" "}, {"name":"x", "weight_kg":-1}, {"name":"x", "birth_date":"2999-01-01"}, {"name":"x", "photo":"https://remote.invalid/image"}, {"name":"x", "photo":"data:image/svg+xml;base64,PHN2Zz4="}]:
        assert client.post(BASE, headers=headers, json=payload).status_code == 422
    day = client.get(BASE).json()["today"]
    assert client.put(f"{BASE}/{pet}/care/food", headers=headers, json={"done":True,"day":day}).status_code == 200
    reminder = client.post(f"{BASE}/{pet}/reminders", headers=headers, json={"title":"Vaccination", "kind":"vaccination", "due_date":"2027-05-01"})
    assert reminder.status_code == 201
    assert client.delete(f"{BASE}/{pet}", headers=headers).status_code == 200
    assert client.get(BASE).json()["pets"] == []
    conn = connect()
    try:
        assert conn.execute("SELECT COUNT(*) FROM pet_care").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM pet_reminders").fetchone()[0] == 0
    finally:
        conn.close()


@pytest.mark.parametrize("role", ["child", "wall_display"])
def test_restricted_roles_and_csrf(client, role):
    owner = login(client, "owner")
    pet = create(client, owner)
    headers = login(client, role)
    data = client.get(BASE).json()
    assert not data["can_edit"]
    assert client.post(BASE, headers=headers, json={"name":"Milo"}).status_code == 403
    assert client.put(f"{BASE}/{pet}", headers=headers, json={"name":"Edited"}).status_code == 403
    assert client.delete(f"{BASE}/{pet}", headers=headers).status_code == 403
    assert client.post(f"{BASE}/{pet}/reminders", headers=headers, json={"title":"Pill", "kind":"medicine", "due_date":data["today"]}).status_code == 403
    payload = {"done":True, "day":data["today"]}
    assert client.put(f"{BASE}/{pet}/care/water", json=payload).status_code == 403
    assert client.put(f"{BASE}/{pet}/care/water", headers=headers, json=payload).status_code == (200 if role == "child" else 403)


def test_daily_checklist_idempotency_midnight_and_undo(client):
    headers = login(client, "adult")
    pet = create(client, headers)
    with patch("app.pets.today", return_value=date(2026,10,7)):
        for _ in range(2):
            assert client.put(f"{BASE}/{pet}/care/walk", headers=headers, json={"done":True,"day":"2026-10-07"}).status_code == 200
        assert list(client.get(BASE).json()["pets"][0]["care"]) == ["walk"]
    with patch("app.pets.today", return_value=date(2026,10,8)):
        assert client.get(BASE).json()["pets"][0]["care"] == {}
        assert client.put(f"{BASE}/{pet}/care/walk", headers=headers, json={"done":True,"day":"2026-10-07"}).status_code == 409
        for done in [True,False]:
            assert client.put(f"{BASE}/{pet}/care/walk", headers=headers, json={"done":done,"day":"2026-10-08"}).status_code == 200
        assert client.get(BASE).json()["pets"][0]["care"] == {}
        assert client.put(f"{BASE}/9999/care/walk", headers=headers, json={"done":True,"day":"2026-10-08"}).status_code == 404


def test_reminders_belong_to_pet_and_can_complete(client):
    headers = login(client, "owner")
    pet = create(client, headers)
    other = create(client, headers)
    response = client.post(f"{BASE}/{pet}/reminders", headers=headers, json={"title":"Medicin", "kind":"medicine", "due_date":"2026-10-08", "notes":"Aftalt med dyrlægen"})
    reminder = response.json()["id"]
    assert client.put(f"{BASE}/{other}/reminders/{reminder}", headers=headers, json={"completed":True}).status_code == 404
    assert client.put(f"{BASE}/{pet}/reminders/{reminder}", headers=headers, json={"completed":True}).status_code == 200
    assert client.get(BASE).json()["pets"][0]["reminders"][0]["completed"] == 1
    edited = {"title":"Ny tid", "kind":"vet", "due_date":"2026-11-10"}
    assert client.patch(f"{BASE}/{pet}/reminders/{reminder}", json=edited).status_code == 403
    assert client.patch(f"{BASE}/{pet}/reminders/{reminder}", headers=headers, json=edited).status_code == 200
    assert client.get(BASE).json()["pets"][0]["reminders"][0]["title"] == "Ny tid"
    assert client.delete(f"{BASE}/{pet}/reminders/{reminder}", headers=headers).status_code == 200
