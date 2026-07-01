#!/usr/bin/env python3
import json
import sys
from pathlib import Path

SUPPORTED_STATUSES = {
    "weather": {"ok", "stale", "not_configured", "unavailable"},
    "calendar": {"ok", "partial", "stale", "not_configured", "unavailable"},
}


def validate_status(kind, payload):
    if kind not in SUPPORTED_STATUSES:
        raise ValueError("unknown family status kind")
    if not isinstance(payload, dict):
        raise ValueError("response must be a JSON object")
    status = payload.get("status")
    if not isinstance(status, str) or status not in SUPPORTED_STATUSES[kind]:
        raise ValueError(f"unsupported {kind} status")
    return status


def load_payload(path):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError("response is not valid JSON") from exc


def main(argv=None):
    arguments = list(sys.argv[1:] if argv is None else argv)
    if len(arguments) != 2:
        print("Usage: validate_family_status.py <weather|calendar> <json-file>", file=sys.stderr)
        return 2
    kind, path = arguments
    try:
        status = validate_status(kind, load_payload(path))
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(f"OK: {kind} status {status}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
