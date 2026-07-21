from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
COMPOSE = (ROOT / "compose.staging.yml").read_text(encoding="utf-8")


def test():
    assert '"127.0.0.1:8098:8088"' in COMPOSE
    assert "jarvis-os:staging" in COMPOSE
    assert 'DB_PATH: "/data/jarvis-staging.db"' in COMPOSE
    assert 'WORKER_ENABLED: "false"' in COMPOSE
    assert 'ALLOW_RESTART_STOPPED: "false"' in COMPOSE
    assert "jarvis_staging_data" in COMPOSE
    assert "jarvis_staging_network" in COMPOSE
    assert "docker.sock" not in COMPOSE
    assert "docker-socket-proxy" not in COMPOSE
    assert "env_file:" not in COMPOSE
    assert ".env" not in COMPOSE


if __name__ == "__main__":
    test()
    print("Staging compose tests OK")
