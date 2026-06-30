from contextvars import ContextVar

_current_actor = ContextVar("jarvis_authenticated_actor", default=None)


def set_current_actor(username):
    return _current_actor.set(username)


def reset_current_actor(token):
    _current_actor.reset(token)


def current_actor():
    return _current_actor.get()
