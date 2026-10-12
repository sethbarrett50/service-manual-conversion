"""ZIP handling: safe extraction of LEMON exports and packaging of section PDFs."""

from __future__ import annotations

import logging
import stat
import zipfile
import zlib
from collections.abc import Iterable
from pathlib import Path

from lemon2pdf.errors import (
    ArchiveTooLargeError,
    ArchiveValidationError,
    CorruptArchiveError,
    ManualNotFoundError,
    UnsafeArchiveError,
)

logger = logging.getLogger(__name__)

MARKER_PAGE = Path("pages") / "2.html"
"""Every LEMON export has numbered pages; page 2 is used to recognize the manual root."""


DEFAULT_MAX_UNCOMPRESSED_GIB = 50
GIB = 1024**3


def safe_extract_zip(
    archive: Path,
    destination: Path,
    max_uncompressed_bytes: int = DEFAULT_MAX_UNCOMPRESSED_GIB * GIB,
) -> None:
    """Extract ``archive`` into ``destination``.

    Refuses members that escape it, symlink members, and archives whose members total more than
    ``max_uncompressed_bytes``; all of these are checked before anything is written. Damaged
    archives raise :class:`CorruptArchiveError`.
    """
    base = destination.resolve()
    try:
        with zipfile.ZipFile(archive) as zf:
            infos = zf.infolist()
            for info in infos:
                target = (destination / info.filename).resolve()
                if not target.is_relative_to(base) or stat.S_ISLNK(info.external_attr >> 16):
                    raise UnsafeArchiveError(info.filename)
            total = sum(info.file_size for info in infos)
            if total > max_uncompressed_bytes:
                raise ArchiveTooLargeError(total, max_uncompressed_bytes)
            zf.extractall(destination)
    except (zipfile.BadZipFile, zlib.error, EOFError, NotImplementedError, RuntimeError) as exc:
        raise CorruptArchiveError(archive, exc) from exc


def find_root(path: Path) -> Path:
    """Return the manual root directory (the one containing ``pages/2.html``)."""
    candidates = [path, *(p.parent for p in path.rglob("index.html"))]
    for root in candidates:
        if (root / MARKER_PAGE).is_file():
            return root
    raise ManualNotFoundError(f"No recognizable LEMON manual in {path}: missing {MARKER_PAGE}")


def write_sections_zip(files: Iterable[Path], archive: Path) -> None:
    """Store ``files`` (flat, by name) in ``archive`` and verify the result."""
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_STORED, allowZip64=True) as zf:
        for f in files:
            zf.write(f, arcname=f.name)
    with zipfile.ZipFile(archive) as zf:
        bad = zf.testzip()
    if bad:
        raise ArchiveValidationError(bad)
    logger.debug("Validated %s", archive)
