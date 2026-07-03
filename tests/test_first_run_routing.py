from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_owner_login_checks_setup_completion():
    source = (ROOT / "app/static/js/login.js").read_text(encoding="utf-8")

    assert 'fetch("/api/admin/setup/summary"' in source
    assert 'credentials: "same-origin"' in source
    assert 'if (!summary.completed) return "/setup"' in source
    assert 'requestedPath === "/setup" ? "/admin" : requestedPath' in source
    assert 'result.user?.role === "owner"' in source


def test_non_owner_fallback_remains_family_view():
    source = (ROOT / "app/static/js/login.js").read_text(encoding="utf-8")
    assert 'result.user?.role === "owner" ? "/admin" : "/"' in source


def test():
    test_owner_login_checks_setup_completion()
    test_non_owner_fallback_remains_family_view()
    print("First-run routing tests OK")


if __name__ == "__main__":
    test()
