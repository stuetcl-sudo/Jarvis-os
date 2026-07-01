import tempfile
import warnings
from pathlib import Path

from fastapi.testclient import TestClient
from pydantic import ValidationError
from pydantic.warnings import UnsupportedFieldAttributeWarning

from app import config
from app.auth.routes import LoginPayload
from app.auth.service import auth_service, initialize_auth_tables
from app.db import init_db
from app.main_auth import app


def test_password_is_the_public_login_field():
    supplied = "".join(["Login", "Payload", "Pass", "-42!"])
    payload = LoginPayload.model_validate(
        {"username": "test-owner", "password": supplied}
    )

    assert payload.username == "test-owner"
    assert payload.password == supplied
    assert payload.credential_value == supplied
    assert payload.model_dump() == {
        "username": "test-owner",
        "password": supplied,
    }
    assert set(LoginPayload.model_json_schema()["properties"]) == {
        "username",
        "password",
    }

    try:
        LoginPayload.model_validate(
            {"username": "test-owner", "credential_value": supplied}
        )
        raise AssertionError("credential_value was accepted as the public input field")
    except ValidationError:
        pass


def test_fastapi_login_request_emits_no_unsupported_field_warning():
    supplied = "".join(["Login", "Route", "Pass", "-42!"])
    previous_db_path = config.DB_PATH

    with tempfile.TemporaryDirectory() as folder:
        config.DB_PATH = str(Path(folder) / "login-payload.db")
        init_db()
        initialize_auth_tables()
        auth_service.create_user("test-owner", "Test Owner", "owner", supplied)

        with warnings.catch_warnings():
            warnings.simplefilter("error", UnsupportedFieldAttributeWarning)
            with TestClient(app, follow_redirects=False) as client:
                response = client.post(
                    "/api/auth/login",
                    json={"username": "test-owner", "password": supplied},
                )

        assert response.status_code == 200, response.text

    config.DB_PATH = previous_db_path


if __name__ == "__main__":
    test_password_is_the_public_login_field()
    test_fastapi_login_request_emits_no_unsupported_field_warning()
    print("Login payload tests OK")
