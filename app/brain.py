from datetime import datetime, timedelta, timezone

from app import config
from app.db import connect, now_iso


def _rows(query, params=()):
    conn = connect()
    rows = conn.execute(query, params).fetchall()
    conn.close()
    return [dict(row) for row in rows]


def _one(query, params=()):
    conn = connect()
    row = conn.execute(query, params).fetchone()
    conn.close()
    return dict(row) if row else None


def _active_recommendation_exists(title, service):
    row = _one(
        "SELECT id FROM recommendations WHERE title = ? AND service IS ? AND status = 'active' LIMIT 1",
        (title, service),
    )
    return row is not None


def add_observation(severity, category, service, title, detail):
    conn = connect()
    conn.execute(
        "INSERT INTO observations (created_at, severity, category, service, title, detail) VALUES (?, ?, ?, ?, ?, ?)",
        (now_iso(), severity, category, service, title, detail),
    )
    conn.commit()
    conn.close()


def add_recommendation(severity, category, service, title, detail):
    if _active_recommendation_exists(title, service):
        return
    conn = connect()
    conn.execute(
        "INSERT INTO recommendations (created_at, status, severity, category, service, title, detail, dismissed_at) VALUES (?, 'active', ?, ?, ?, ?, ?, NULL)",
        (now_iso(), severity, category, service, title, detail),
    )
    conn.commit()
    conn.close()


def list_observations(limit=100):
    safe_limit = max(1, min(int(limit), 500))
    return _rows("SELECT * FROM observations ORDER BY id DESC LIMIT ?", (safe_limit,))


def list_recommendations(active_only=True, limit=100):
    safe_limit = max(1, min(int(limit), 500))
    if active_only:
        return _rows("SELECT * FROM recommendations WHERE status = 'active' ORDER BY id DESC LIMIT ?", (safe_limit,))
    return _rows("SELECT * FROM recommendations ORDER BY id DESC LIMIT ?", (safe_limit,))


def dismiss_recommendation(recommendation_id):
    conn = connect()
    cur = conn.execute(
        "UPDATE recommendations SET status = 'dismissed', dismissed_at = ? WHERE id = ? AND status = 'active'",
        (now_iso(), int(recommendation_id)),
    )
    conn.commit()
    changed = cur.rowcount
    conn.close()
    return changed > 0


def update_system_baseline(health):
    now = now_iso()
    cpu = float(health["cpu_percent"])
    memory = float(health["memory"]["percent"])
    swap = float(health["swap"]["percent"])
    disk = float(health["disk_root"]["percent"])
    conn = connect()
    row = conn.execute("SELECT * FROM system_baselines WHERE id = 1").fetchone()
    if not row:
        conn.execute(
            "INSERT INTO system_baselines (id, sample_count, avg_cpu_percent, avg_memory_percent, avg_swap_percent, min_swap_percent, max_swap_percent, avg_disk_percent, first_seen_at, last_seen_at) VALUES (1, 1, ?, ?, ?, ?, ?, ?, ?, ?)",
            (cpu, memory, swap, swap, swap, disk, now, now),
        )
    else:
        sample_count = int(row["sample_count"]) + 1
        previous = int(row["sample_count"])
        conn.execute(
            "UPDATE system_baselines SET sample_count = ?, avg_cpu_percent = ?, avg_memory_percent = ?, avg_swap_percent = ?, min_swap_percent = ?, max_swap_percent = ?, avg_disk_percent = ?, last_seen_at = ? WHERE id = 1",
            (
                sample_count,
                ((float(row["avg_cpu_percent"]) * previous) + cpu) / sample_count,
                ((float(row["avg_memory_percent"]) * previous) + memory) / sample_count,
                ((float(row["avg_swap_percent"]) * previous) + swap) / sample_count,
                min(float(row["min_swap_percent"]), swap),
                max(float(row["max_swap_percent"]), swap),
                ((float(row["avg_disk_percent"]) * previous) + disk) / sample_count,
                now,
            ),
        )
    conn.commit()
    conn.close()


def update_service_baselines(containers):
    now = now_iso()
    conn = connect()
    for item in containers:
        name = item["name"]
        classification = item["classification"]
        status = item["status"]
        row = conn.execute("SELECT * FROM service_baselines WHERE service = ?", (name,)).fetchone()
        if not row:
            running_count = 1 if status == "running" else 0
            stopped_count = 1 if status == "exited" else 0
            unknown_seen_count = 1 if classification == "unknown" else 0
            normal_status = "running" if running_count >= stopped_count else "exited"
            conn.execute(
                "INSERT INTO service_baselines (service, classification, normal_status, running_count, stopped_count, unknown_seen_count, sample_count, first_seen_at, last_seen_at) VALUES (?, ?, ?, ?, ?, ?, 1, ?, ?)",
                (name, classification, normal_status, running_count, stopped_count, unknown_seen_count, now, now),
            )
        else:
            running_count = int(row["running_count"]) + (1 if status == "running" else 0)
            stopped_count = int(row["stopped_count"]) + (1 if status == "exited" else 0)
            unknown_seen_count = int(row["unknown_seen_count"]) + (1 if classification == "unknown" else 0)
            sample_count = int(row["sample_count"]) + 1
            normal_status = "running" if running_count >= stopped_count else "exited"
            conn.execute(
                "UPDATE service_baselines SET classification = ?, normal_status = ?, running_count = ?, stopped_count = ?, unknown_seen_count = ?, sample_count = ?, last_seen_at = ? WHERE service = ?",
                (classification, normal_status, running_count, stopped_count, unknown_seen_count, sample_count, now, name),
            )
    conn.commit()
    conn.close()


def recent_disk_trend():
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=6)).isoformat()
    rows = _rows("SELECT created_at, disk_percent FROM worker_checks WHERE created_at >= ? ORDER BY id ASC", (cutoff,))
    if len(rows) < 3:
        return None
    return float(rows[-1]["disk_percent"]) - float(rows[0]["disk_percent"])


def detect_anomalies(containers, health):
    system = _one("SELECT * FROM system_baselines WHERE id = 1")
    services = {row["service"]: row for row in _rows("SELECT * FROM service_baselines")}

    for item in containers:
        name = item["name"]
        status = item["status"]
        classification = item["classification"]
        baseline = services.get(name)

        if classification == "critical" and status != "running":
            add_observation("critical", "service", name, "Kritisk service stoppet", f"{name} har status {status}.")
            add_recommendation("critical", "service", name, "Undersøg kritisk service", f"{name} er kritisk og kører ikke. Jarvis auto-fixer ikke dette i v0.3.")

        if classification == "unknown":
            add_observation("info", "service", name, "Ukendt container fundet", f"{name} er ikke klassificeret som critical, optional eller stopped-by-design.")
            add_recommendation("info", "service", name, "Klassificér ukendt container", f"Tilføj {name} til CRITICAL_SERVICES, OPTIONAL_SERVICES eller IGNORED_SERVICES i .env.")

        if baseline and int(baseline["sample_count"]) >= config.BASELINE_MIN_SAMPLES:
            normal_status = baseline["normal_status"]
            if status != normal_status:
                add_observation("warning", "service", name, "Service afviger fra normal status", f"{name} er {status}, men er normalt {normal_status}.")
                if normal_status == "exited":
                    add_recommendation("info", "service", name, "Denne service er normalt stoppet", f"{name} ser ud til normalt at være stoppet. Overvej at tilføje den til IGNORED_SERVICES.")

        recent_failures = _one(
            "SELECT COUNT(*) AS total FROM action_log WHERE action = 'auto_start' AND target = ? AND status = 'error' AND created_at >= ?",
            (name, (datetime.now(timezone.utc) - timedelta(minutes=config.AUTO_START_FAILURE_WINDOW_MINUTES)).isoformat()),
        )
        if recent_failures and int(recent_failures["total"]) >= config.AUTO_START_FAILURE_LIMIT:
            add_observation("warning", "service", name, "Optional service fejler gentagne gange", f"{name} har {recent_failures['total']} auto-start fejl i fejlvinduet.")
            add_recommendation("warning", "service", name, "Undersøg service før auto-start", f"{name} bør undersøges manuelt før den sættes på auto-start igen.")

    if system and int(system["sample_count"]) >= config.BASELINE_MIN_SAMPLES:
        ram_now = float(health["memory"]["percent"])
        swap_now = float(health["swap"]["percent"])
        ram_avg = float(system["avg_memory_percent"])
        swap_avg = float(system["avg_swap_percent"])
        if ram_now >= ram_avg + config.ANOMALY_RAM_DELTA_PERCENT:
            add_observation("warning", "system", "system", "RAM højere end normalt", f"RAM er {ram_now:.1f}%, baseline er {ram_avg:.1f}%.")
            add_recommendation("warning", "system", "system", "RAM er højere end normal baseline", "Tjek om en container bruger mere RAM end normalt. Jarvis ændrer intet automatisk.")
        if swap_now >= swap_avg + config.ANOMALY_SWAP_DELTA_PERCENT:
            add_observation("warning", "system", "system", "Swap højere end normalt", f"Swap er {swap_now:.1f}%, baseline er {swap_avg:.1f}%.")
            add_recommendation("warning", "system", "system", "Swap er højere end normalt", "Overvej at undersøge RAM-forbrug og swap-pres. Jarvis ændrer ikke swap automatisk.")

    disk_delta = recent_disk_trend()
    if disk_delta is not None and disk_delta >= config.DISK_TREND_DELTA_PERCENT:
        add_observation("warning", "system", "system", "Diskforbrug stiger", f"Diskforbrug er steget {disk_delta:.1f}% inden for seneste målinger.")
        add_recommendation("warning", "system", "system", "Disk usage is trending upward", "Undersøg logs, downloads eller backupdata. Jarvis sletter intet automatisk.")


def learn_from_check(containers, health):
    update_system_baseline(health)
    update_service_baselines(containers)
    detect_anomalies(containers, health)


def brain_summary():
    system = _one("SELECT * FROM system_baselines WHERE id = 1")
    services = _rows("SELECT * FROM service_baselines ORDER BY service ASC")
    observations = list_observations(25)
    recommendations = list_recommendations(True, 25)
    return {
        "learning": True,
        "system_baseline": system,
        "service_baselines": services,
        "observations": observations,
        "recommendations": recommendations,
        "normal_behavior_summary": {
            "services_learned": len(services),
            "system_samples": system["sample_count"] if system else 0,
            "active_recommendations": len(recommendations),
        },
    }
