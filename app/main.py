from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
import psutil

from app import config
from app.db import init_db, list_actions, log_action
from app.docker_monitor import list_containers, restart_container
from app.safety import can_restart_container

app = FastAPI(title=config.APP_NAME, version="0.1.0")
app.mount("/static", StaticFiles(directory="app/static"), name="static")


@app.on_event("startup")
def startup():
    init_db()
    log_action("startup", "jarvis-os", "ok", "Jarvis-os v0.1 started")


@app.get("/")
def ui():
    return FileResponse("app/static/index.html")


@app.get("/api/health")
def health():
    disk = psutil.disk_usage("/")
    memory = psutil.virtual_memory()
    swap = psutil.swap_memory()
    return {
        "app": config.APP_NAME,
        "version": "0.1.0",
        "safe_mode": config.SAFE_MODE,
        "cpu_percent": psutil.cpu_percent(interval=0.2),
        "memory": {"percent": memory.percent, "used": memory.used, "total": memory.total},
        "swap": {"percent": swap.percent, "used": swap.used, "total": swap.total},
        "disk_root": {"percent": disk.percent, "used": disk.used, "total": disk.total},
        "boot_time": psutil.boot_time(),
    }


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
