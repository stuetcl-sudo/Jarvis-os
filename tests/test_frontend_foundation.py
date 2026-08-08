from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "app" / "static"
CSS = STATIC / "css"


def read(path):
    return path.read_text(encoding="utf-8")


def test_shared_frontend_foundation_files_exist_and_define_primitives():
    tokens = read(CSS / "tokens.css")
    base = read(CSS / "base.css")
    components = read(CSS / "components.css")
    layout = read(CSS / "layout.css")

    for expected in [
        "--jarvis-color-bg",
        "--jarvis-color-surface",
        "--jarvis-color-border",
        "--jarvis-color-text",
        "--jarvis-color-muted",
        "--jarvis-color-accent",
        "--jarvis-status-ok",
        "--jarvis-status-warning",
        "--jarvis-status-critical",
        "--jarvis-touch-target",
    ]:
        assert expected in tokens

    assert "button:focus-visible" in base
    assert "textarea:focus-visible" in base
    assert ".jarvis-card" in components
    assert ".jarvis-button" in components
    assert ".jarvis-badge" in components
    assert ".jarvis-grid" in layout
    assert "@media (max-width: 860px)" in layout
    assert "@media (max-width: 680px)" in layout


def test_core_pages_load_foundation_before_page_specific_styles():
    pages = [
        ROOT / "app" / "admin.html",
        STATIC / "index.html",
        STATIC / "login.html",
        STATIC / "wall.html",
    ]
    foundation = [
        "/static/css/tokens.css",
        "/static/css/base.css",
        "/static/css/components.css",
        "/static/css/layout.css",
    ]

    for page in pages:
        html = read(page)
        positions = [html.index(path) for path in foundation]
        assert positions == sorted(positions), page
        first_page_specific = min(
            html.index(path)
            for path in [
                "/static/css/admin.css",
                "/static/css/family.css",
                "/static/css/login.css",
                "/static/css/wall.css",
            ]
            if path in html
        )
        assert max(positions) < first_page_specific, page


def test_foundation_does_not_introduce_unsafe_frontend_patterns():
    combined = "\n".join(
        read(CSS / name)
        for name in ["tokens.css", "base.css", "components.css", "layout.css"]
    )
    for forbidden in [
        "innerHTML",
        "insertAdjacentHTML",
        "outerHTML",
        "document.write",
        "eval(",
        "new Function(",
        "localStorage",
        "sessionStorage",
        "Authorization",
    ]:
        assert forbidden not in combined


if __name__ == "__main__":
    for test in [
        test_shared_frontend_foundation_files_exist_and_define_primitives,
        test_core_pages_load_foundation_before_page_specific_styles,
        test_foundation_does_not_introduce_unsafe_frontend_patterns,
    ]:
        test()
    print("Frontend foundation tests OK")
