"""Desktop backends, chosen by detection (detect.Env.backend)."""
from .base import Backend, Context
from .gnome import Gnome

BACKENDS = {"gnome": Gnome}


def get(env, run=None):
    cls = BACKENDS.get(env.backend, Backend)
    return cls(env, run) if run else cls(env)


__all__ = ["Backend", "Context", "get", "BACKENDS"]
