"""Copy externally pinned mounted inputs into ephemeral runtime-owned files.

``with materialize_inputs({"manifest": (mount, digest, MANIFEST_MAX_BYTES)})
as paths:`` yields files usable by the unchanged strict private-input readers.
Use ``POLICY_MAX_BYTES`` for launch/profile inputs. Mounts must be approved and
read-only at deployment; their owner may be root and their mode may be 0444.
This helper proves bytes and destination privacy, not mount authorization or
cloud configuration. No source paths, content, or pins are logged.
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from contextlib import contextmanager
import hashlib
import os
from pathlib import Path
import re
import shutil
import stat
import tempfile


MANIFEST_MAX_BYTES = 1024 * 1024
POLICY_MAX_BYTES = 64 * 1024


class RuntimeInputError(ValueError):
    """Sanitized materialization failure without private input details."""


def _outside_git(directory: Path) -> None:
    directory = directory.resolve()
    if any((ancestor / ".git").exists() for ancestor in (directory, *directory.parents)):
        raise RuntimeInputError("Runtime inputs must remain outside Git")


def _read_source(source: Path, expected: str, maximum: int) -> bytes:
    _outside_git(source.parent)
    fd = os.open(source, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, "rb") as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode):
            raise RuntimeInputError("Mounted input must be a regular file")
        if info.st_size > maximum:
            raise RuntimeInputError("Mounted input exceeds size bound")
        raw = stream.read(maximum + 1)
    if len(raw) > maximum:
        raise RuntimeInputError("Mounted input exceeds size bound")
    if hashlib.sha256(raw).hexdigest() != expected:
        raise RuntimeInputError("Mounted input digest mismatch")
    return raw


def _write_private(directory_fd: int, name: str, raw: bytes, expected: str) -> None:
    fd = os.open(
        name, os.O_RDWR | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
        0o600, dir_fd=directory_fd,
    )
    with os.fdopen(fd, "w+b") as stream:
        # Ensure exact privacy mode even under a more restrictive process umask.
        os.fchmod(stream.fileno(), 0o600)
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())
        info = os.fstat(stream.fileno())
        linked = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
        if (
            not stat.S_ISREG(info.st_mode)
            or stat.S_IMODE(info.st_mode) != 0o600
            or info.st_uid != os.getuid()
            or info.st_nlink != 1
            or (info.st_dev, info.st_ino) != (linked.st_dev, linked.st_ino)
        ):
            raise RuntimeInputError("Materialized input privacy validation failed")
        stream.seek(0)
        if hashlib.sha256(stream.read(len(raw) + 1)).hexdigest() != expected:
            raise RuntimeInputError("Materialized input digest validation failed")


@contextmanager
def materialize_inputs(
    inputs: Mapping[str, tuple[Path, str, int]],
    *,
    temp_parent: Path | None = None,
) -> Iterator[dict[str, Path]]:
    """Yield private copies, deleting them on normal exit and every failure.

    Each value is ``(source_path, externally_expected_sha256, max_bytes)``.
    Names must be safe filename components. Bounds must be positive integers
    no larger than 1 MiB; at most 16 inputs can be materialized per context.
    ``temp_parent`` optionally selects a writable parent outside Git (normally
    the OS temporary directory). No caller-selected destination is overwritten.
    Sources are opened with O_NOFOLLOW/O_NONBLOCK, permitting root-owned regular
    read-only mounts while rejecting final symlinks, devices, FIFOs and folders.
    Callers must keep all strict-reader use within the context's lifetime.
    """
    if not isinstance(inputs, Mapping) or not 1 <= len(inputs) <= 16:
        raise RuntimeInputError("Invalid runtime input mapping")
    entries = list(inputs.items())
    for name, spec in entries:
        if not isinstance(name, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,63}", name):
            raise RuntimeInputError("Invalid runtime input name")
        if not isinstance(spec, tuple) or len(spec) != 3:
            raise RuntimeInputError("Invalid runtime input specification")
        source, expected, maximum = spec
        if not isinstance(source, Path):
            raise RuntimeInputError("Invalid mounted input reference")
        if not isinstance(expected, str) or not re.fullmatch(r"[0-9a-f]{64}", expected):
            raise RuntimeInputError("External runtime input digest required")
        if type(maximum) is not int or not 1 <= maximum <= MANIFEST_MAX_BYTES:
            raise RuntimeInputError("Invalid runtime input size bound")

    directory: Path | None = None
    try:
        try:
            parent = Path(temp_parent if temp_parent is not None else tempfile.gettempdir()).resolve()
            _outside_git(parent)
            directory = Path(tempfile.mkdtemp(prefix="specimen-runtime-", dir=parent))
            os.chmod(directory, 0o700)
            directory_fd = os.open(directory, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
            try:
                info = os.fstat(directory_fd)
                if info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o700:
                    raise RuntimeInputError("Runtime input directory privacy validation failed")
                paths = {}
                for name, (source, expected, maximum) in entries:
                    raw = _read_source(source, expected, maximum)
                    _write_private(directory_fd, name, raw, expected)
                    paths[name] = directory / name
            finally:
                os.close(directory_fd)
        except OSError:
            raise RuntimeInputError("Runtime input materialization unavailable") from None
        yield paths
    finally:
        if directory is not None:
            try:
                shutil.rmtree(directory)
            except OSError:
                raise RuntimeInputError("Runtime input cleanup failed") from None
