#!/usr/bin/env bash
set -euo pipefail

case "${1:-}" in
  "") mode=current ;;
  --history) mode=history ;;
  *) echo "Usage: $0 [--history]" >&2; exit 2 ;;
esac

root=$(git rev-parse --show-toplevel 2>/dev/null) || {
  echo "privacy-check: not inside a Git repository" >&2
  exit 2
}
cd "$root"

python3 - "$mode" <<'PY'
import ipaddress
import os
import re
import subprocess
import sys
from pathlib import Path

MODE = sys.argv[1]
ROOT = Path.cwd()
EXCLUDED_DIRS = {
    ".git", ".mypy_cache", ".next", ".pytest_cache", ".ruff_cache", ".tox", ".venv",
    "__pycache__", "build", "cache", "coverage", "dist", "htmlcov", "node_modules", "venv",
}
EXCLUDED_SUFFIXES = {
    ".7z", ".avi", ".db", ".gif", ".gz", ".ico", ".jpeg", ".jpg", ".mov", ".mp3",
    ".mp4", ".pdf", ".png", ".pyc", ".sqlite", ".sqlite3", ".tar", ".webp", ".zip",
}
SOURCE_SUFFIXES = {
    "", ".cfg", ".conf", ".css", ".env", ".example", ".html", ".ini", ".js", ".json",
    ".md", ".properties", ".py", ".sh", ".sql", ".toml", ".ts", ".tsx", ".txt", ".xml",
    ".yaml", ".yml",
}
GENERIC_ASSETS = {"app", "database", "example-app", "example-database", "example-network", "example-service", "network", "reverse-proxy", "worker"}
GENERIC_HOSTS = {"0.0.0.0", "jarvis-os", "localhost"}
ALLOWED_DOMAINS = {"docker.io", "example.com", "example.net", "example.org", "github.com", "localhost", "pypi.org", "raw.githubusercontent.com"}
ALLOWED_SUFFIXES = (".example", ".example.com", ".example.net", ".example.org", ".github.com", ".python.org")
STANDARD_NAMESPACE_URLS = {
    "http://www.w3.org/2000/svg",
    "http://www.w3.org/1999/xlink",
    "http://www.w3.org/XML/1998/namespace",
}
DOC_NETS = (
    ipaddress.ip_network((3221225984, 24)), ipaddress.ip_network((3325256704, 24)),
    ipaddress.ip_network((3405803776, 24)), ipaddress.ip_network((42540766411282592856903984951653826560, 32)),
)
PRIVATE_NETS = (
    ipaddress.ip_network((167772160, 8)), ipaddress.ip_network((2886729728, 12)),
    ipaddress.ip_network((3232235520, 16)), ipaddress.ip_network((334965454937798799971759379190646833152, 7)),
)
CREDENTIAL_KEY_NAMES = {
    "api_key", "apikey", "client_secret", "credential", "credentials", "credential_value",
    "password", "passwd", "private_key", "secret", "token",
}
CREDENTIAL_KEY_SUFFIXES = (
    "_api_key", "_apikey", "_client_secret", "_password", "_passwd", "_private_key",
    "_secret", "_token",
)
SECURITY_HEADER_KEYS = {"authorization", "x_csrf_token"}
FETCH_CREDENTIAL_MODES = {"omit", "same-origin", "include"}
PLACEHOLDERS = ("${", "{{", "<", "changeme", "dummy", "example", "placeholder", "redacted", "replace")
KEY_HEADER_RE = re.compile("|".join(re.escape("-----BEGIN " + suffix) for suffix in ("OPENSSH PRIVATE KEY-----", "PRIVATE KEY-----", "RSA PRIVATE KEY-----", "EC PRIVATE KEY-----")))
SSH_PUBLIC_RE = re.compile(r"\bssh-" + r"(?:rsa|dss|ed25519)\s+[A-Za-z0-9+/]{24,}={0,3}(?:\s|$)")
ASSIGNMENT_RE = re.compile(r"^\s*(?:export\s+)?[\"']?([A-Za-z_][A-Za-z0-9_.-]*)[\"']?\s*[:=]\s*(.*?)\s*,?\s*$")
INDEXED_ASSIGNMENT_RE = re.compile(
    r"^\s*[A-Za-z_$][A-Za-z0-9_$]*(?:\.[A-Za-z_$][A-Za-z0-9_$]*)*"
    r"\s*\[\s*[\"']([A-Za-z_][A-Za-z0-9_.-]*)[\"']\s*\]\s*=\s*(.*?)\s*;?\s*$",
    re.I,
)
QUOTED_MAPPING_RE = re.compile(r"^\s*[\"'][A-Za-z_][A-Za-z0-9_.-]*[\"']\s*:")
DYNAMIC_REFERENCE_RE = re.compile(
    r"^(?:await\s+)?[A-Za-z_$][A-Za-z0-9_$]*"
    r"(?:\.[A-Za-z_$][A-Za-z0-9_$]*)*"
    r"(?:\(\s*\))?"
    r"(?:\s*(?:\|\||\?\?)\s*(?:null|undefined|None))?$",
    re.I,
)
PYTHON_INTERPOLATED_RE = re.compile(r"^(?:f|fr|rf)[\"'].*\{[^{}]+\}.*[\"']$", re.I)
NESTED_LITERAL_RE = re.compile(
    r"[\"'](?:api_key|apikey|client_secret|credential|credentials|password|passwd|private_key|secret|token)[\"']"
    r"\s*:\s*[\"'][^\"']+[\"']",
    re.I,
)
IPV4_RE = re.compile(r"(?<![\w.])(?:\d{1,3}\.){3}\d{1,3}(?![\w.])")
IPV6_RE = re.compile(r"(?<![\w:])(?:[A-Fa-f0-9]{0,4}:){2,7}[A-Fa-f0-9]{0,4}(?![\w:])")
DOMAIN_RE = re.compile(r"(?<![@\w-])(?:[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?\.)+[A-Za-z]{2,63}\b")
EMAIL_RE = re.compile(r"\b[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@([A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+)\b")
SERVICE_COMPARE_RE = re.compile(r"\b(?:container_name|name|service)(?:\.lower\(\))?\s*==\s*[\"']([a-z0-9][a-z0-9._-]+)[\"']", re.I)
ASSET_RE = re.compile(r"\bdocker:([a-z0-9][a-z0-9._-]+)\b", re.I)
PERSON_RE = re.compile(r"\b(?:contact|maintainer|owner|recommended install on)\s*[:=]?\s*[A-Z][a-z]{2,}(?:\s+[A-Z][a-z]{2,})+\b")
IP_CONTEXT_RE = re.compile(r"\b(?:address|domain|endpoint|gateway|host|hostname|ip|server|url)\b|https?://|--host\b", re.I)
INVENTORY_RE = re.compile(r"^(?:ALLOWED_[A-Z0-9_]*CONTAINERS|ASSET_DEPENDENCIES|CRITICAL_SERVICES|IGNORED_SERVICES|OPTIONAL_SERVICES|PROTECTED_CONTAINERS)$")


def git_bytes(*args):
    return subprocess.run(["git", *args], cwd=ROOT, check=True, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL).stdout


def excluded(path):
    clean = path.replace(os.sep, "/").lstrip("./")
    parts = Path(clean).parts
    return any(part in EXCLUDED_DIRS for part in parts[:-1]) or Path(clean).suffix.lower() in EXCLUDED_SUFFIXES


def decode(data):
    if b"\x00" in data:
        return None
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return None


def current_files():
    seen = set()
    groups = [
        (git_bytes("ls-files", "-z"), False),
        (git_bytes("ls-files", "--others", "--exclude-standard", "-z"), True),
    ]
    for raw, untracked in groups:
        for path in raw.decode("utf-8", "surrogateescape").split("\0"):
            if not path or path in seen or excluded(path):
                continue
            if untracked and Path(path).name not in {"Dockerfile", "Makefile"} and Path(path).suffix.lower() not in SOURCE_SUFFIXES:
                continue
            seen.add(path)
            item = ROOT / path
            if item.is_file():
                yield path, item.read_bytes()


def history_files():
    seen = set()
    for line in git_bytes("rev-list", "--objects", "--all").decode("utf-8", "surrogateescape").splitlines():
        object_id, separator, path = line.partition(" ")
        if not separator or not path or excluded(path) or (object_id, path) in seen:
            continue
        seen.add((object_id, path))
        object_type = subprocess.run(["git", "cat-file", "-t", object_id], cwd=ROOT, text=True, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL).stdout.strip()
        if object_type == "blob":
            data = subprocess.run(["git", "cat-file", "blob", object_id], cwd=ROOT, check=True, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL).stdout
            yield path, data


def allowed_domain(value):
    domain = value.lower().rstrip(".")
    return domain in ALLOWED_DOMAINS or domain.endswith(ALLOWED_SUFFIXES)


def generic_asset(value):
    name = value.lower()
    return name in GENERIC_ASSETS or name.startswith("example-")


def assignment(line):
    header_match = INDEXED_ASSIGNMENT_RE.match(line)
    if header_match:
        raw_value = header_match.group(2).strip().rstrip(",;").strip()
        value = raw_value.strip('"').strip("'").strip()
        return header_match.group(1), value, raw_value

    match = ASSIGNMENT_RE.match(line)
    if not match:
        return None, None, None
    raw_value = match.group(2).strip().rstrip(",;").strip()
    value = raw_value.strip('"').strip("'").strip()
    return match.group(1), value, raw_value


def credential_key(normalized):
    return (
        normalized in SECURITY_HEADER_KEYS
        or normalized in CREDENTIAL_KEY_NAMES
        or normalized.endswith(CREDENTIAL_KEY_SUFFIXES)
    )


def browser_fetch_credential_mode(normalized, raw_value, value, line):
    return (
        normalized == "credentials"
        and value.lower() in FETCH_CREDENTIAL_MODES
        and re.match(r"""^\s*(?:"credentials"|'credentials'|credentials)\s*:""", line, re.I)
        and re.fullmatch(r"""(?:"(?:omit|same-origin|include)"|'(?:omit|same-origin|include)')""", raw_value, re.I)
    )


def credential_literal(raw_value, value):
    lowered = value.lower()
    if lowered in {"none", "null"} or not value:
        return False
    if any(marker in lowered for marker in PLACEHOLDERS):
        return False
    if DYNAMIC_REFERENCE_RE.fullmatch(raw_value):
        return False
    if PYTHON_INTERPOLATED_RE.fullmatch(raw_value):
        return False
    if "${" in raw_value or "{{" in raw_value:
        return False
    if NESTED_LITERAL_RE.search(raw_value):
        return True
    if len(raw_value) >= 2 and raw_value[0] in {'"', "'", "`"} and raw_value[-1] == raw_value[0]:
        return True
    return bool(re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._/@:+-]*", raw_value))


def scan(path, text):
    findings = set()
    for number, line in enumerate(text.splitlines(), 1):
        if KEY_HEADER_RE.search(line):
            findings.add((number, "private-key"))
        if SSH_PUBLIC_RE.search(line):
            findings.add((number, "ssh-public-key"))

        key, value, raw_value = assignment(line)
        quoted_mapping = bool(QUOTED_MAPPING_RE.match(line))
        if key and value:
            normalized = key.lower().replace("-", "_").replace(".", "_")
            if (
                credential_key(normalized)
                and not browser_fetch_credential_mode(normalized, raw_value, value, line)
                and credential_literal(raw_value, value)
            ):
                findings.add((number, "credential-assignment"))

            upper = key.upper().replace("-", "_").replace(".", "_")
            if not quoted_mapping and INVENTORY_RE.match(upper) and re.fullmatch(r"[\[\]{}\"'A-Za-z0-9:.,_ >-]*", value):
                literal_value = re.sub(r"[\[\]{}\"']", "", value)
                if upper == "ASSET_DEPENDENCIES":
                    if any(not generic_asset(name) for name in ASSET_RE.findall(literal_value)):
                        findings.add((number, "service-specific-dependency"))
                else:
                    entries = [item.strip().lower() for item in literal_value.split(",") if item.strip()]
                    if any(item != "jarvis-os" and not item.startswith("example-") for item in entries):
                        findings.add((number, "deployment-inventory"))
            if upper in {"DOMAIN", "HOST", "HOSTNAME", "SERVER_NAME"}:
                simple = re.fullmatch(r"[\"']?([A-Za-z0-9._:-]+)[\"']?", value)
                if simple:
                    host = simple.group(1).lower().split(":", 1)[0]
                    if host not in GENERIC_HOSTS and not host.startswith("example-") and not allowed_domain(host):
                        findings.add((number, "personal-hostname"))
            if upper in {"DOMAIN", "ENDPOINT", "URL"} and value not in STANDARD_NAMESPACE_URLS and re.fullmatch(r"[\"']?[A-Za-z0-9:/._-]+[\"']?", value):
                for domain in DOMAIN_RE.findall(value):
                    if not allowed_domain(domain):
                        findings.add((number, "personal-domain"))

        for match in re.finditer(r"/home/([A-Za-z0-9._-]+)", line):
            if match.group(1).lower() not in {"example", "user", "username"}:
                findings.add((number, "personal-home-path"))

        addresses = []
        for raw_ip in IPV4_RE.findall(line) + IPV6_RE.findall(line):
            try:
                address = ipaddress.ip_address(raw_ip)
            except ValueError:
                continue
            if address not in addresses:
                addresses.append(address)
        for address in addresses:
            if any(address in network for network in DOC_NETS) or address.is_loopback or address.is_unspecified:
                continue
            if any(address in network for network in PRIVATE_NETS):
                findings.add((number, "private-lan-address"))
            elif address.is_global and IP_CONTEXT_RE.search(line):
                findings.add((number, "public-ip-configuration"))

        for match in EMAIL_RE.finditer(line):
            if not allowed_domain(match.group(1)):
                findings.add((number, "email-address"))
        domain_line = line
        for namespace_url in STANDARD_NAMESPACE_URLS:
            domain_line = domain_line.replace(namespace_url, "")
        for host in re.findall(r"https?://([^/\s:\"']+)", domain_line, re.I):
            if DOMAIN_RE.fullmatch(host) and not allowed_domain(host):
                findings.add((number, "personal-domain"))
        if PERSON_RE.search(line):
            findings.add((number, "personal-name"))
        comparison = SERVICE_COMPARE_RE.search(line)
        if comparison and comparison.group(1).lower() not in {"critical", "exited", "optional", "running", "stopped_by_design", "unknown"}:
            findings.add((number, "service-specific-dependency"))
        if re.search(r"\b(?:dependency|depends_on|required_state)\b", line, re.I):
            if any(not generic_asset(name) for name in ASSET_RE.findall(line)):
                findings.add((number, "service-specific-dependency"))

    return {(path.replace(os.sep, "/"), number, rule) for number, rule in findings}


source = history_files() if MODE == "history" else current_files()
findings = set()
for path, data in source:
    text = decode(data)
    if text is not None:
        findings.update(scan(path, text))
for path, number, rule in sorted(findings):
    print(f"{path}:{number}:{rule}")
if findings:
    raise SystemExit(1)
print(f"Privacy check OK ({MODE}).")
PY
