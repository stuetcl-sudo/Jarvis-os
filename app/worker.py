import asyncio
from datetime import datetime, timedelta, timezone

from app import config
from app.brain import learn_from_check
from app.db import (
    count_recent_failed_actions,
    create_incident,
    latest_worker_check,
    list_actions,
    list_incidents,
    log_action,
    log_worker_check,
    resolve_incident,
    safe_cleanup_old_rows,
)
from app.docker_monitor import list_containers, start_container
from app.health import get_health
from app.safety import can_auto_start

worker_state = {
    "enabled": config.WORKER_ENABLED,
    "running": False,
    "last_started_at": None,
    "last_finished_at": None,
    "last_successful_check": None,
    "last_failed_check": None,
    "consecutive_failures": 0,
    "last_result": None,
    "last_error": None,
    "current_task": "Afventer næste check",
    "learning": True,
}

_last_throttled_logs = {}
THROTTLE_WINDOW = timedelta(hours=1)


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def log_throttled(action, target, status, reason):
    key = (action, target, status, reason)
    now = datetime.now(timezone.utc)
    last_logged = _last_throttled_logs.get(key)
    if last_logged and now - last_logged < THROTTLE_WINDOW:
        return False
    _last_throttled_logs[key] = now
    log_action(action, target, status, reason)
    return True


def summarize_containers(containers):
    return {
        "total": len(containers),
        "running": len([c for c in containers if c["status"] == "running"]),
        "stopped": len([c for c in containers if c["status"] == "exited"]),
        "critical": [c for c in containers if c["classification"] == "critical"],
        "optional": [c for c in containers if c["classification"] == "optional"],
        "stopped_by_design": [c for c in containers if c["classification"] == "stopped_by_design"],
    }


def evaluate_incidents(containers, health):
    for item in containers:
        title = "Service er stoppet"
        if item["classification"] == "critical" and item["status"] != "running":
            create_incident("critical", item["name"], title, f"Kritisk service har status {item['status']}.")
        elif item["status"] == "running":
            resolve_incident(item["name"], title)

    system_checks = [
        ("CPU høj", health["cpu_percent"], config.CPU_WARN_PERCENT),
        ("RAM høj", health["memory"]["percent"], config.MEMORY_WARN_PERCENT),
        ("Swap høj", health["swap"]["percent"], config.SWAP_WARN_PERCENT),
        ("Disk høj", health["disk_root"]["percent"], config.DISK_WARN_PERCENT),
    ]
    for title, value, threshold in system_checks:
        if value >= threshold:
            create_incident("warning", "system", title, f"Målt {value:.1f}% over grænse {threshold}%.")
        else:
            resolve_incident("system", title)


def auto_heal(containers):
    for item in containers:
        if item["status"] != "exited":
            continue
        if item["classification"] == "stopped_by_design":
            log_throttled("auto_start", item["name"], "skipped", "Service er stoppet med vilje.")
            continue
        recent_failures = count_recent_failed_actions(
            "auto_start",
            item["name"],
            config.AUTO_START_FAILURE_WINDOW_MINUTES,
        )
        allowed, reason = can_auto_start(item, containers, recent_failures)
        if not allowed:
            log_throttled("auto_start", item["name"], "denied", reason)
            continue
        ok, result = start_container(item["name"])
        log_action("auto_start", item["name"], "ok" if ok else "error", result)


def run_check_once():
    worker_state["running"] = True
    worker_state["last_started_at"] = utc_now()
    worker_state["current_task"] = "Tjekker Docker og system health"
    worker_state["last_error"] = None
    try:
        containers, docker_error = list_containers()
        health = get_health()
        if docker_error:
            create_incident("critical", "docker", "Docker kan ikke læses", docker_error)
            log_action("worker_check", "docker", "error", docker_error)
            raise RuntimeError(docker_error)

        summary = summarize_containers(containers)
        evaluate_incidents(containers, health)
        worker_state["current_task"] = "Jarvis lærer normal serveradfærd"
        learn_from_check(containers, health)
        worker_state["current_task"] = "Vurderer safe mode og self-healing"
        auto_heal(containers)
        worker_state["current_task"] = "Rydder gamle Jarvis database-rækker"
        cleanup_result = safe_cleanup_old_rows()

        status = "warning" if health["warnings"] or list_incidents(True, 1) else "ok"
        log_worker_check(
            status,
            summary["total"],
            summary["running"],
            summary["stopped"],
            health["cpu_percent"],
            health["memory"]["percent"],
            health["swap"]["percent"],
            health["disk_root"]["percent"],
            ", ".join(health["warnings"]),
        )
        log_action("worker_check", "jarvis-os", "ok", f"Docker: {summary['running']} kører, {summary['stopped']} stoppet. Cleanup: {cleanup_result}.")
        worker_state["last_result"] = status
        worker_state["last_successful_check"] = utc_now()
        worker_state["consecutive_failures"] = 0
        return {"status": status, "health": health, "docker": summary, "learning": True}
    except Exception as exc:
        worker_state["last_error"] = str(exc)
        worker_state["last_result"] = "error"
        worker_state["last_failed_check"] = utc_now()
        worker_state["consecutive_failures"] += 1
        log_action("worker_check", "jarvis-os", "error", str(exc))
        raise
    finally:
        worker_state["running"] = False
        worker_state["last_finished_at"] = utc_now()
        worker_state["current_task"] = "Afventer næste check"


async def worker_loop():
    if not config.WORKER_ENABLED:
        log_action("worker", "jarvis-os", "disabled", "Background worker er slået fra.")
        return
    while True:
        try:
            run_check_once()
        except Exception:
            pass
        await asyncio.sleep(config.WORKER_INTERVAL_SECONDS)


def worker_status():
    return {
        **worker_state,
        "interval_seconds": config.WORKER_INTERVAL_SECONDS,
        "latest_check": latest_worker_check(),
        "latest_action": list_actions(1)[0] if list_actions(1) else None,
    }
