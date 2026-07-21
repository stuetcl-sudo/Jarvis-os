from app.auth.service import auth_service

FAMILY_PERSON_ROLES = {"owner", "adult", "child"}
ROLE_ORDER = {"child": 0, "adult": 1, "owner": 2}


def list_family_people():
    people = []
    for user in auth_service.list_users():
        role = user.get("role")
        if role not in FAMILY_PERSON_ROLES or user.get("disabled"):
            continue
        user_id = str(user.get("user_id") or "").strip()
        display_name = str(user.get("display_name") or "").strip()
        if not user_id or not display_name:
            continue
        people.append({
            "user_id": user_id,
            "display_name": display_name,
            "role": role,
        })
    people.sort(key=lambda item: (ROLE_ORDER[item["role"]], item["display_name"].casefold(), item["user_id"]))
    return people
