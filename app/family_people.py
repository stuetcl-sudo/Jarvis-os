from app.auth.service import auth_service

FAMILY_PERSON_ROLES = {"owner", "adult", "child"}
ROLE_ORDER = {"child": 0, "adult": 1, "owner": 2}
SHARED_ROUTINE_ROLE = "shared"


def _public_person(user):
    user_id = str(user.get("user_id") or "").strip()
    display_name = str(user.get("display_name") or "").strip()
    role = user.get("role")
    if not user_id or not display_name:
        return None
    return {
        "user_id": user_id,
        "display_name": display_name,
        "role": role,
    }


def list_family_people():
    users = auth_service.list_users()
    people = []
    for user in users:
        role = user.get("role")
        if role not in FAMILY_PERSON_ROLES or user.get("disabled"):
            continue
        person = _public_person(user)
        if person is not None:
            people.append(person)
    people.sort(key=lambda item: (ROLE_ORDER[item["role"]], item["display_name"].casefold(), item["user_id"]))
    if people:
        return people

    # Keep a fresh wall-only installation compatible with the existing shared
    # routine experience without exposing wall_display as a family person.
    for user in users:
        if user.get("role") != "wall_display" or user.get("disabled"):
            continue
        user_id = str(user.get("user_id") or "").strip()
        if user_id:
            return [{
                "user_id": f"shared:{user_id}",
                "display_name": "Fælles",
                "role": SHARED_ROUTINE_ROLE,
            }]
    return []
