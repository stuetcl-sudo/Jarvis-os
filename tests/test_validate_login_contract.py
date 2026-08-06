import os
import subprocess
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def run_case(status, location=None, body=""):
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            assert self.path == "/login"
            self.send_response(status)
            if location is not None:
                self.send_header("Location", location)
            self.end_headers()
            self.wfile.write(body.encode("utf-8"))

        def log_message(self, _format, *_args):
            return

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        environment = {
            **os.environ,
            "APP_URL": f"http://127.0.0.1:{server.server_port}",
            "VALIDATE_LOGIN_ONLY": "true",
        }
        return subprocess.run(
            ["bash", "scripts/validate.sh"],
            cwd=ROOT,
            env=environment,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


def test_login_http_200_is_accepted_with_content():
    result = run_case(200, body="<h1>Log ind på Jarvis</h1>")
    assert result.returncode == 0, result.stdout


def test_approved_bootstrap_redirect_is_accepted():
    result = run_case(303, location="/bootstrap")
    assert result.returncode == 0, result.stdout


def test_unexpected_redirect_is_rejected():
    result = run_case(303, location="https://example.com/unapproved")
    assert result.returncode != 0
    assert "unapproved Location" in result.stdout


def test_wrong_status_is_rejected():
    result = run_case(302, location="/bootstrap")
    assert result.returncode != 0
    assert "expected 200 or approved 303" in result.stdout


def test():
    test_login_http_200_is_accepted_with_content()
    test_approved_bootstrap_redirect_is_accepted()
    test_unexpected_redirect_is_rejected()
    test_wrong_status_is_rejected()
    print("Validate login contract tests OK")


if __name__ == "__main__":
    test()
