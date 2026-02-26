"""CLI command history helpers."""

from __future__ import annotations

import shlex
from collections.abc import Iterable

HISTORY_MAX_ENTRIES = 2000

_SENSITIVE_MARKERS = (
    "token",
    "secret",
    "password",
    "passphrase",
    "key",
    "cert",
    "auth",
    "header",
    "cookie",
    "signature",
    "private",
    "jwt",
)

_REDACTED = "<redacted>"


def _is_sensitive_flag(flag: str) -> bool:
    lowered = flag.lower().lstrip("-")
    return any(marker in lowered for marker in _SENSITIVE_MARKERS)


def _looks_sensitive_value(value: str) -> bool:
    lowered = value.lower()
    if any(marker in lowered for marker in _SENSITIVE_MARKERS):
        return True

    if lowered.startswith("bearer "):
        return True

    if len(value) >= 48 and " " not in value and "/" not in value and "\\" not in value:
        return True

    return False


def redact_argv(argv: Iterable[str]) -> list[str]:
    tokens = list(argv)
    redacted: list[str] = []
    i = 0

    while i < len(tokens):
        arg = tokens[i]

        if arg.startswith("--"):
            if "=" in arg:
                flag, value = arg.split("=", 1)
                if _is_sensitive_flag(flag) or _looks_sensitive_value(value):
                    redacted.append(f"{flag}={_REDACTED}")
                else:
                    redacted.append(arg)
                i += 1
                continue

            redacted.append(arg)
            if _is_sensitive_flag(arg) and i + 1 < len(tokens):
                nxt = tokens[i + 1]
                if not nxt.startswith("-"):
                    redacted.append(_REDACTED)
                    i += 2
                    continue
            i += 1
            continue

        if "=" in arg:
            key, value = arg.split("=", 1)
            if _is_sensitive_flag(key) or _looks_sensitive_value(value):
                redacted.append(f"{key}={_REDACTED}")
            else:
                redacted.append(arg)
            i += 1
            continue

        if _looks_sensitive_value(arg):
            redacted.append(_REDACTED)
        else:
            redacted.append(arg)
        i += 1

    return redacted


def redacted_command(argv: Iterable[str]) -> str:
    return " ".join(shlex.quote(token) for token in redact_argv(argv))
