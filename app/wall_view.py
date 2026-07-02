from app.family_view import render_family_page

WALL_ROLES = {"owner", "adult", "child", "wall_display"}


def wall_actions_for(role):
    links = [
        '<button type="button" id="wallFullscreen">Fuld skærm</button>',
        '<a href="/">Familie</a>',
    ]
    if role == "owner":
        links.append('<a href="/admin">Administration</a>')
    return '<nav class="wall-display-actions" aria-label="Vægskærm">' + "".join(links) + "</nav>"


def render_wall_page(current_user):
    role = current_user.get("role") if isinstance(current_user, dict) else None
    if role not in WALL_ROLES:
        raise ValueError("wall role required")

    shared_display = {"role": "wall_display", "display_name": ""}
    page = render_family_page(shared_display, wall_actions=wall_actions_for(role))
    page = page.replace("<title>Jarvis – Hjem</title>", "<title>Jarvis – Vægskærm</title>", 1)
    page = page.replace("<body ", f'<body data-wall-dashboard="true" data-wall-actor-role="{role}" ', 1)
    return page
