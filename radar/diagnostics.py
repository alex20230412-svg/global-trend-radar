"""Extract a small, name-and-number-only diagnostic for the private run audit."""

import re


def diagnostic(error, *, source_id=None):
    module = line = None
    frame = error.__traceback__
    while frame is not None:
        name = frame.tb_frame.f_globals.get("__name__", "")
        if re.fullmatch(r"radar(?:\.[a-z_]+)+", name):
            module, line = name, frame.tb_lineno
        frame = frame.tb_next
    name = type(error).__name__
    http_status = getattr(error, "http_status", None)
    return {
        "exception_class": name if re.fullmatch(r"[A-Z][A-Za-z0-9_]{0,49}", name) else "Exception",
        "module": module,
        "line": line,
        "source_id": source_id,
        "http_status": http_status if type(http_status) is int and 100 <= http_status <= 599 else None,
    }
