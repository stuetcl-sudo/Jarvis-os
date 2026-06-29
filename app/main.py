import asyncio

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from app import config
from app.brain import brain_summary, dismiss_recommendation, list_observations, list_recommendations
from app.db import (
    event_statistics,
    event_types,
    init_db,
    list_actions,
    list_events,
    list_incidents,
    list_service_classifications,
    log_action,
    store_event,
    upsert_service_classification,
)
from app.docker_monitor import list_containers, restart_container
from app.events.bus import event_bus
from app.events.dispatcher import publish
from app.events.types import EventTypes
from app.health import get_health
from app.safety import can_restart_container
from app.worker import run_check_once, worker_loop, worker_status

app = FastAPI(title=config.APP_NAME, version=config.VERSION)
app.mount("/static", StaticFiles(directory="app/static"), name="static")


class ServiceClassificationPayload(BaseModel):
    classification: str
    protected: bool = False
    auto_start_allowed: bool = False


def state_of(container):
    return container.get("docker_state") or container.get("status")


def docker_read_at(items):
    return items[0].get("read_at") if items else None


@app.on_event("startup")
async def startup():
    init_db()
    event_bus.subscribe("*", store_event)
    log_action("startup", "jarvis-os", "ok", f"Jarvis-os v{config.VERSION} startet")
    publish("core", "Core.Started", "info", "jarvis-os", {"version": config.VERSION})
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
    return {"docker_read_at": docker_read_at(items), "containers": items}


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
    if match.get("protected"):
        log_action("restart_container", name, "denied", "Containeren er beskyttet.")
        raise HTTPException(status_code=403, detail="Containeren er beskyttet.")

    allowed, reason = can_restart_container(match["name"], state_of(match))
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


@app.get("/api/brain")
def brain():
    return brain_summary()


@app.get("/api/observations")
def observations(limit: int = 100):
    return {"observations": list_observations(limit)}


@app.get("/api/recommendations")
def recommendations(active_only: bool = True, limit: int = 100):
    return {"recommendations": list_recommendations(active_only, limit)}


@app.post("/api/recommendations/{recommendation_id}/dismiss")
def dismiss_recommendation_route(recommendation_id: int):
    if not dismiss_recommendation(recommendation_id):
        raise HTTPException(status_code=404, detail="Recommendation not found or already dismissed")
    log_action("dismiss_recommendation", str(recommendation_id), "ok", "Recommendation dismissed by user")
    publish("core", EventTypes.RECOMMENDATION_DISMISSED, "info", str(recommendation_id), {"id": recommendation_id})
    return {"status": "ok"}


@app.get("/api/service-classifications")
def service_classifications():
    return {"service_classifications": list_service_classifications()}


@app.post("/api/service-classifications/{service}")
def set_service_classification(service: str, payload: ServiceClassificationPayload):
    try:
        saved = upsert_service_classification(
            service,
            payload.classification,
            payload.protected,
            payload.auto_start_allowed,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    log_action("classify_service", service, "ok", f"{saved['classification']}, protected={saved['protected']}, auto_start_allowed={saved['auto_start_allowed']}")
    publish("core", "Service.Classified", "info", service, saved)
    return {"service_classification": saved}


@app.get("/api/events")
def events(limit: int = 100):
    return {"events": list_events(limit)}


@app.get("/api/events/latest")
def latest_events(limit: int = 25):
    return {"events": list_events(limit)}


@app.get("/api/events/types")
def events_types():
    return {"types": event_types()}


@app.get("/api/events/statistics")
def events_statistics():
    return event_statistics()


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
    unknown = [c for c in items if c["classification"] == "unknown"]
    running_count = len([c for c in items if state_of(c) == "running"])
    stopped_count = len([c for c in items if state_of(c) == "exited"])
    critical_ok = all(state_of(c) == "running" for c in critical)
    overall = "critical" if any(i["severity"] == "critical" for i in active_incidents) else "warning" if active_incidents or health_data["warnings"] else "ok"
    current_worker = worker_status()

    return {
        "app": config.APP_NAME,
        "version": config.VERSION,
        "overall_status": overall,
        "safe_mode": config.SAFE_MODE,
        "critical_ok": critical_ok,
        "containers": items,
        "critical_services": critical,
        "optional_services": optional,
        "stopped_by_design": stopped_by_design,
        "unknown_containers": unknown,
        "docker": {"total": len(items), "running": running_count, "stopped": stopped_count, "docker_read_at": docker_read_at(items)},
        "health": health_data,
        "latest_action": actions[0] if actions else None,
        "active_incidents": active_incidents,
        "worker": current_worker,
        "brain": brain_summary()["normal_behavior_summary"],
        "events": list_events(10),
        "what_jarvis_is_doing_now": current_worker["current_task"],
    }
