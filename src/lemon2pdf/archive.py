"""ZIP handling: safe extraction of LEMON exports and packaging of section PDFs."""

from __future__ import annotations

import logging
import zipfile
from collections.abc import Iterable
from pathlib import Path

from lemon2pdf.errors import ArchiveValidationError, ManualNotFoundError, UnsafeArchiveError

logger = logging.getLogger(__name__)

MARKER_PAGE = Path("pages") / "2.html"
"""Every LEMON export has numbered pages; page 2 is used to recognize the manual root."""


def safe_extract_zip(archive: Path, destination: Path) -> None:
    """Extract ``archive`` into ``destination``, refusing members that escape it."""
    base = destination.resolve()
    with zipfile.ZipFile(archive) as zf:
        for info in zf.infolist():
            target = (destination / info.filename).resolve()
            if not target.is_relative_to(base):
                raise UnsafeArchiveError(info.filename)
        zf.extractall(destination)


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
