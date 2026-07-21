import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXPECTED_VERSION = "0.17.3"

config = (ROOT / "app/config.py").read_text(encoding="utf-8")
readme = (ROOT / "README.md").read_text(encoding="utf-8")

match = re.search(r'^VERSION = "([^"]+)"$', config, re.MULTILINE)

assert match is not None
assert match.group(1) == EXPECTED_VERSION
assert f"# Jarvis-os v{EXPECTED_VERSION}" in readme
assert f"Current development version: `{EXPECTED_VERSION}`." in readme
assert "## What is new in v0.17.3" in readme

print("Release version tests OK")
