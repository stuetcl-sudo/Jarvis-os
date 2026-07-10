from pathlib import Path

from fastapi.testclient import TestClient

from app.docker_socket_proxy import allowed_docker_request, app, normalize_docker_path

ROOT = Path(__file__).resolve().parents[1]


def test_versioned_docker_paths_are_normalized():
    assert normalize_docker_path("/v1.47/containers/json") == "/containers/json"
    assert normalize_docker_path("/containers/json") == "/containers/json"
    assert normalize_docker_path("") == "/"


def test_only_required_docker_operations_are_allowed():
    allowed = [
        ("GET", "/_ping"),
        ("HEAD", "/_ping"),
        ("GET", "/version"),
        ("GET", "/containers/json"),
        ("GET", "/v1.47/containers/json"),
        ("GET", "/v1.47/containers/abc123/json"),
        ("GET", "/containers/example-service/json"),
        ("POST", "/v1.47/containers/abc123/start"),
        ("POST", "/containers/example-service/start"),
    ]
    for method, path in allowed:
        assert allowed_docker_request(method, path), (method, path)


def test_destructive_and_general_docker_operations_are_denied():
    denied = [
        ("POST", "/containers/example-service/stop"),
        ("POST", "/containers/example-service/restart"),
        ("DELETE", "/containers/example-service"),
        ("POST", "/containers/create"),
        ("POST", "/containers/example-service/exec"),
        ("POST", "/exec/example/start"),
        ("GET", "/images/json"),
        ("POST", "/images/create"),
        ("GET", "/volumes"),
        ("DELETE", "/volumes/example"),
        ("GET", "/events"),
        ("GET", "/info"),
        ("POST", "/containers/example-service/start/extra"),
        ("POST", "/containers/example%2Fservice/start"),
    ]
    for method, path in denied:
        assert not allowed_docker_request(method, path), (method, path)


def test_proxy_rejects_forbidden_request_before_docker_socket_access():
    client = TestClient(app)
    try:
        response = client.post("/v1.47/containers/example-service/stop")
        assert response.status_code == 403
        assert response.json() == {"message": "Docker API operation is not allowed"}
    finally:
        client.close()


def test_main_application_has_no_direct_docker_socket_mount():
    compose = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    proxy_section, jarvis_section = compose.split("  jarvis-os:", 1)
    assert "/var/run/docker.sock:/var/run/docker.sock:ro" in proxy_section
    assert "/var/run/docker.sock" not in jarvis_section
    assert "DOCKER_HOST: http://docker-socket-proxy:2375" in jarvis_section
    assert "read_only: true" in proxy_section
    assert "read_only: true" in jarvis_section
    assert "cap_drop:" in proxy_section
    assert "cap_drop:" in jarvis_section


def test():
    test_versioned_docker_paths_are_normalized()
    test_only_required_docker_operations_are_allowed()
    test_destructive_and_general_docker_operations_are_denied()
    test_proxy_rejects_forbidden_request_before_docker_socket_access()
    test_main_application_has_no_direct_docker_socket_mount()
    print("Docker socket proxy tests OK")


if __name__ == "__main__":
    test()
