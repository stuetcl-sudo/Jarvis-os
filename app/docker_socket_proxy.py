import re

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response

DOCKER_SOCKET_PATH = "/var/run/docker.sock"
API_VERSION_PREFIX = re.compile(r"^/v\d+(?:\.\d+)?(?=/|$)")
CONTAINER_IDENTIFIER = r"[A-Za-z0-9][A-Za-z0-9_.-]*"
CONTAINER_INSPECT = re.compile(rf"^/containers/{CONTAINER_IDENTIFIER}/json$")
CONTAINER_START = re.compile(rf"^/containers/{CONTAINER_IDENTIFIER}/start$")
HOP_BY_HOP_HEADERS = {
    "connection",
    "content-encoding",
    "content-length",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailers",
    "transfer-encoding",
    "upgrade",
}

app = FastAPI(
    title="Jarvis restricted Docker socket proxy",
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
)


def normalize_docker_path(path):
    normalized = str(path or "")
    if not normalized.startswith("/"):
        normalized = f"/{normalized}"
    return API_VERSION_PREFIX.sub("", normalized, count=1) or "/"


def allowed_docker_request(method, path):
    verb = str(method or "").upper()
    normalized = normalize_docker_path(path)
    if verb in {"GET", "HEAD"} and normalized == "/_ping":
        return True
    if verb == "GET" and normalized in {"/version", "/containers/json"}:
        return True
    if verb == "GET" and CONTAINER_INSPECT.fullmatch(normalized):
        return True
    if verb == "POST" and CONTAINER_START.fullmatch(normalized):
        return True
    return False


def response_headers(headers):
    return {
        key: value
        for key, value in headers.items()
        if key.lower() not in HOP_BY_HOP_HEADERS
    }


def safe_nonnegative_int(value):
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return 0
    return max(0, parsed)


def sanitized_container_list(payload):
    if not isinstance(payload, list):
        return None
    result = []
    for item in payload:
        if not isinstance(item, dict) or not isinstance(item.get("Id"), str):
            continue
        result.append(
            {
                "Id": item["Id"],
                "Names": item.get("Names") if isinstance(item.get("Names"), list) else [],
                "Image": str(item.get("Image") or ""),
                "ImageID": str(item.get("ImageID") or ""),
                "Created": item.get("Created"),
                "State": str(item.get("State") or "unknown"),
                "Status": str(item.get("Status") or ""),
            }
        )
    return result


def sanitized_container_inspect(payload):
    if not isinstance(payload, dict) or not isinstance(payload.get("Id"), str):
        return None
    raw_state = payload.get("State") if isinstance(payload.get("State"), dict) else {}
    raw_health = raw_state.get("Health") if isinstance(raw_state.get("Health"), dict) else {}
    raw_config = payload.get("Config") if isinstance(payload.get("Config"), dict) else {}
    state = {
        "Status": str(raw_state.get("Status") or "unknown"),
        "RestartCount": safe_nonnegative_int(raw_state.get("RestartCount")),
    }
    if raw_health:
        state["Health"] = {"Status": str(raw_health.get("Status") or "unknown")}
    return {
        "Id": payload["Id"],
        "Name": str(payload.get("Name") or ""),
        "Created": payload.get("Created"),
        "Config": {"Image": str(raw_config.get("Image") or "")},
        "State": state,
    }


def sanitize_docker_payload(path, payload):
    normalized = normalize_docker_path(path)
    if normalized == "/containers/json":
        return sanitized_container_list(payload)
    if CONTAINER_INSPECT.fullmatch(normalized):
        return sanitized_container_inspect(payload)
    return None


async def docker_request(method, path, *, query=None, content=b""):
    transport = httpx.AsyncHTTPTransport(uds=DOCKER_SOCKET_PATH)
    try:
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://docker",
            timeout=10.0,
        ) as client:
            return await client.request(
                method,
                path,
                params=query,
                content=content,
                headers={
                    "Accept": "application/json",
                    "Accept-Encoding": "identity",
                },
            )
    except httpx.HTTPError as exc:
        raise RuntimeError("Docker Engine is unavailable") from exc


@app.get("/health")
async def health():
    try:
        response = await docker_request("GET", "/_ping")
    except RuntimeError:
        return JSONResponse({"status": "unavailable"}, status_code=503)
    if not response.is_success:
        return JSONResponse({"status": "unavailable"}, status_code=503)
    return {"status": "ok"}


@app.api_route("/{path:path}", methods=["GET", "HEAD", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"])
async def proxy_docker_request(path: str, request: Request):
    upstream_path = request.url.path
    if not allowed_docker_request(request.method, upstream_path):
        return JSONResponse(
            {"message": "Docker API operation is not allowed"},
            status_code=403,
        )

    body = await request.body()
    if len(body) > 1024:
        return JSONResponse({"message": "Request body is too large"}, status_code=413)

    try:
        upstream = await docker_request(
            request.method,
            upstream_path,
            query=list(request.query_params.multi_items()),
            content=body,
        )
    except RuntimeError:
        return JSONResponse({"message": "Docker Engine is unavailable"}, status_code=502)

    headers = response_headers(upstream.headers)
    if upstream.is_success and request.method == "GET":
        try:
            sanitized = sanitize_docker_payload(upstream_path, upstream.json())
        except (TypeError, ValueError):
            sanitized = None
        if sanitized is not None:
            headers.pop("content-type", None)
            return JSONResponse(sanitized, status_code=upstream.status_code, headers=headers)

    return Response(
        content=upstream.content,
        status_code=upstream.status_code,
        headers=headers,
        media_type=None,
    )
