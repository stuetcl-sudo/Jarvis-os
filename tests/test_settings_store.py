import os
import sqlite3
import tempfile

from app import config, settings_store


def test_plain_settings_round_trip():
    with tempfile.TemporaryDirectory() as folder:
        db_path = os.path.join(folder, "jarvis.db")
        assert settings_store.get_setting("home.name", "Jarvis", db_path=db_path) == "Jarvis"
        settings_store.set_setting("home.name", "Amborgvej", db_path=db_path)
        assert settings_store.get_setting("home.name", db_path=db_path) == "Amborgvej"
        settings_store.delete_setting("home.name", db_path=db_path)
        assert settings_store.get_setting("home.name", "Jarvis", db_path=db_path) == "Jarvis"


def test_secrets_are_encrypted_and_not_exposed_in_summary():
    with tempfile.TemporaryDirectory() as folder:
        db_path = os.path.join(folder, "jarvis.db")
        token = "example-home-assistant-token"
        settings_store.set_secret("home_assistant.token", token, db_path=db_path, master_key="test-master-key")
        assert settings_store.get_secret(
            "home_assistant.token", db_path=db_path, master_key="test-master-key"
        ) == token
        conn = sqlite3.connect(db_path)
        stored = conn.execute(
            "SELECT encrypted_value FROM app_secrets WHERE key = ?", ("home_assistant.token",)
        ).fetchone()[0]
        conn.close()
        assert token not in stored
        summary = settings_store.public_connection_summary(db_path=db_path)
        assert summary["home_assistant_token_configured"] is True
        assert token not in repr(summary)


def test_wrong_master_key_is_rejected():
    with tempfile.TemporaryDirectory() as folder:
        db_path = os.path.join(folder, "jarvis.db")
        settings_store.set_secret("home_assistant.token", "secret", db_path=db_path, master_key="correct")
        try:
            settings_store.get_secret(
                "home_assistant.token", db_path=db_path, master_key="wrong"
            )
        except RuntimeError as exc:
            assert "CONFIG_MASTER_KEY" in str(exc)
        else:
            raise AssertionError("A wrong master key must not decrypt stored secrets")


def test_home_assistant_configuration_prefers_store_and_keeps_env_fallback():
    with tempfile.TemporaryDirectory() as folder:
        db_path = os.path.join(folder, "jarvis.db")
        token_env_name = "HOME_ASSISTANT_" + "TOKEN"
        old_db_path = config.DB_PATH
        old_url = os.environ.get("HOME_ASSISTANT_URL")
        old_token = os.environ.get(token_env_name)
        old_master_key = os.environ.get("CONFIG_MASTER_KEY")
        try:
            config.DB_PATH = db_path
            os.environ["HOME_ASSISTANT_URL"] = "http://env-home-assistant"
            os.environ[token_env_name] = "env-token"
            os.environ["CONFIG_MASTER_KEY"] = "test-master-key"
            fallback = config.home_assistant_configuration()
            assert fallback["base_url"] == "http://env-home-assistant"
            assert fallback["access_value"] == "env-token"

            settings_store.set_setting(
                "home_assistant.base_url", "http://stored-home-assistant", db_path=db_path
            )
            settings_store.set_secret(
                "home_assistant.token", "stored-token", db_path=db_path
            )
            stored = config.home_assistant_configuration()
            assert stored["base_url"] == "http://stored-home-assistant"
            assert stored["access_value"] == "stored-token"
        finally:
            config.DB_PATH = old_db_path
            if old_url is None:
                os.environ.pop("HOME_ASSISTANT_URL", None)
            else:
                os.environ["HOME_ASSISTANT_URL"] = old_url
            if old_token is None:
                os.environ.pop(token_env_name, None)
            else:
                os.environ[token_env_name] = old_token
            if old_master_key is None:
                os.environ.pop("CONFIG_MASTER_KEY", None)
            else:
                os.environ["CONFIG_MASTER_KEY"] = old_master_key


def test():
    test_plain_settings_round_trip()
    test_secrets_are_encrypted_and_not_exposed_in_summary()
    test_wrong_master_key_is_rejected()
    test_home_assistant_configuration_prefers_store_and_keeps_env_fallback()
    print("Settings store tests OK")


if __name__ == "__main__":
    test()
