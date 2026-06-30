from app.brain import add_recommendation
from app.db import create_incident


def create_recommendation(severity: str, category: str, asset_id: str | None, title: str, detail: str) -> None:
    add_recommendation(severity, category, asset_id, title, detail)


def create_critical_incident(service: str | None, title: str, detail: str) -> None:
    create_incident("critical", service, title, detail)


def ignore() -> None:
    return None


def deny() -> None:
    return None
