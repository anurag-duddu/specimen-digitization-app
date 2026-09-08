"""Bounded private configuration reads; no symlinks, devices, pipes or Git files."""

import os
from pathlib import Path
import stat


def read_private(path: Path, limit=65536):
    directory = path.parent.resolve()
    if any((parent / ".git").exists() for parent in (directory, *directory.parents)):
        raise ValueError("private configuration must be outside Git")
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(descriptor, "rb") as stream:
        details = os.fstat(stream.fileno())
        if (
            not stat.S_ISREG(details.st_mode)
            or details.st_mode & 0o077
            or details.st_uid != os.geteuid()
        ):
            raise ValueError("private regular configuration file required")
        raw = stream.read(limit + 1)
    if len(raw) > limit:
        raise ValueError("private configuration byte limit")
    return raw
