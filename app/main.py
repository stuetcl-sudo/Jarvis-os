import asyncio

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app import config
from app.db import init_db, list_actions, list_incidents, log_action
from app.docker_monitor import list_containers, restart_container
from app.health import get_health
from app.safety import can_restart_container
from app.worker import run_check_once, worker_loop, worker_status

app = FastAPI(title=config.APP_NAME, version=config.VERSION)
app.mount("/static", StaticFiles(directory="app/static"), name="static")


@app.on_event("startup")
def startup():
    init_db()
    log_action("startup", "jarvis-os", "ok", f"Jarvis-os v{config.VERSION} startet")
    if config.WORKER_ENABLED:
        asyncio.create_task(worker_loop())


@app.get("/")
def ui():
    return FileResponse("app/static/index.html")


@app.get("/api/health")
def health():
    data = get_health()
    data.update({"app": config.APP_NAME, "version": config.VERSION, "safe_mode": config.SAFE_MODE})
    return data


@app.get("/api/containers")
def containers():
    items, error = list_containers()
    if error:
        log_action("list_containers", "docker", "error", error)
        raise HTTPException(status_code=503, detail=error)
    return {"containers": items}


@app.post("/api/containers/{name}/restart")
def restart(name: str):
    items, error = list_containers()
    if error:
        log_action("restart_container", name, "error", error)
        raise HTTPException(status_code=503, detail=error)

    match = next((item for item in items if item["name"] == name), None)
    if not match:
        log_action("restart_container", name, "denied", "Container not found")
        raise HTTPException(status_code=404, detail="Container not found")

    allowed, reason = can_restart_container(match["name"], match["status"])
    if not allowed:
        log_action("restart_container", name, "denied", reason)
        raise HTTPException(status_code=403, detail=reason)

    ok, result = restart_container(name)
    log_action("restart_container", name, "ok" if ok else "error", result)
    if not ok:
        raise HTTPException(status_code=500, detail=result)
    return {"status": "ok", "reason": result}


@app.get("/api/actions")
def actions(limit: int = 100):
    return {"actions": list_actions(limit)}


@app.get("/api/incidents")
def incidents(active_only: bool = True, limit: int = 100):
    return {"incidents": list_incidents(active_only, limit)}


@app.get("/api/worker/status")
def get_worker_status():
    return worker_status()


@app.post("/api/worker/run-once")
def worker_run_once():
    if worker_status()["running"]:
        raise HTTPException(status_code=409, detail="Jarvis worker kører allerede")
    return run_check_once()


@app.get("/api/mission")
def mission():
    items, error = list_containers()
    health_data = get_health()
    active_incidents = list_incidents(True, 50)
    actions = list_actions(1)
    if error:
        log_action("mission", "docker", "error", error)
        raise HTTPException(status_code=503, detail=error)

    critical = [c for c in items if c["classification"] == "critical"]
    optional = [c for c in items if c["classification"] == "optional"]
    stopped_by_design = [c for c in items if c["classification"] == "stopped_by_design"]
    running_count = len([c for c in items if c["status"] == "running"])
    stopped_count = len([c for c in items if c["status"] == "exited"])
    critical_ok = all(c["status"] == "running" for c in critical)
    overall = "critical" if any(i["severity"] == "critical" for i in active_incidents) else "warning" if active_incidents or health_data["warnings"] else "ok"

    return {
        "app": config.APP_NAME,
        "version": config.VERSION,
        "overall_status": overall,
        "safe_mode": config.SAFE_MODE,
        "critical_ok": critical_ok,
        "critical_services": critical,
        "optional_services": optional,
        "stopped_by_design": stopped_by_design,
        "docker": {"total": len(items), "running": running_count, "stopped": stopped_count},
        "health": health_data,
        "latest_action": actions[0] if actions else None,
        "active_incidents": active_incidents,
        "worker": worker_status(),
        "what_jarvis_is_doing_now": worker_status()["current_task"],
    }
