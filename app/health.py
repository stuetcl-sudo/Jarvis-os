import psutil

from app import config


def get_health():
    disk = psutil.disk_usage("/")
    memory = psutil.virtual_memory()
    swap = psutil.swap_memory()
    cpu = psutil.cpu_percent(interval=0.2)
    warnings = []

    if cpu >= config.CPU_WARN_PERCENT:
        warnings.append("CPU er høj")
    if memory.percent >= config.MEMORY_WARN_PERCENT:
        warnings.append("RAM-forbrug er højt")
    if swap.percent >= config.SWAP_WARN_PERCENT:
        warnings.append("Swap-forbrug er højt")
    if disk.percent >= config.DISK_WARN_PERCENT:
        warnings.append("Diskforbrug er højt")

    return {
        "cpu_percent": cpu,
        "memory": {"percent": memory.percent, "used": memory.used, "total": memory.total},
        "swap": {"percent": swap.percent, "used": swap.used, "total": swap.total},
        "disk_root": {"percent": disk.percent, "used": disk.used, "total": disk.total},
        "boot_time": psutil.boot_time(),
        "warnings": warnings,
        "status": "warning" if warnings else "ok",
    }
