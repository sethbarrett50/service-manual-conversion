"""End-to-end build: source ZIP or directory in, section PDFs, combined PDF and manifest out."""

from __future__ import annotations

import errno
import logging
import re
import tempfile
from pathlib import Path

from lemon2pdf.archive import GIB, find_root, safe_extract_zip, write_sections_zip
from lemon2pdf.assemble import build_section, combine_section_pdfs
from lemon2pdf.discovery import discover, filter_sections
from lemon2pdf.errors import ConversionError, ManualNotFoundError
from lemon2pdf.models import BuildOptions, Manifest, SectionResult

logger = logging.getLogger(__name__)

COMPLETE_PDF_NAME = "complete_navigable_manual.pdf"
SECTIONS_ZIP_NAME = "sectioned_manuals.zip"
MANIFEST_NAME = "manifest.json"
MAX_FILENAME_STEM = 90
MIB = 1024 * 1024


def clean_name(value: str) -> str:
    """Filesystem-safe lowercase slug for a section name."""
    name = re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")
    return name[:MAX_FILENAME_STEM] or "general"


def _mib(path: Path) -> int:
    return path.stat().st_size // MIB


def _resolve_source(source: Path, scratch: Path, max_uncompressed_gib: float) -> Path:
    if source.is_file() and source.suffix.lower() == ".zip":
        logger.info("Extracting ZIP...")
        extracted = scratch / "extracted"
        extracted.mkdir()
        safe_extract_zip(source, extracted, int(max_uncompressed_gib * GIB))
        return extracted
    if not source.exists():
        raise ManualNotFoundError(f"Source does not exist: {source}")
    if not source.is_dir():
        raise ManualNotFoundError(f"Source is neither a .zip file nor a directory: {source}")
    return source


def build(options: BuildOptions) -> Manifest:
    """Run a full conversion and return the manifest that was written."""
    try:
        return _build(options)
    except OSError as exc:
        if exc.errno == errno.ENOSPC:
            temp = options.temp_dir or Path(tempfile.gettempdir())
            raise ConversionError(
                f"Out of disk space (temporary files are in {temp}); "
                "free space or point --temp-dir at a larger disk"
            ) from exc
        raise ConversionError(f"File system error: {exc}") from exc


def _build(options: BuildOptions) -> Manifest:
    out = options.out
    out.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="lemon_build_", dir=options.temp_dir) as tmp:
        scratch = Path(tmp)
        root = find_root(_resolve_source(options.source, scratch, options.max_uncompressed_gib))
        vehicle = root.name
        logger.info("Indexing: %s", vehicle)
        sections = filter_sections(discover(root, options.max_documents), options.section_filters)
        total = sum(len(s.documents) for s in sections)
        logger.info("%d documents in %d sections", total, len(sections))

        section_dir = out / "sections"
        section_dir.mkdir(exist_ok=True)
        results: list[SectionResult] = []
        for i, section in enumerate(sections, 1):
            target = section_dir / f"{i:02}_{clean_name(section.name)}.pdf"
            logger.info(
                "[%d/%d] %s: %d documents", i, len(sections), section.name, len(section.documents)
            )
            pages = build_section(root, vehicle, section, target, scratch, options.batch_size)
            results.append(SectionResult(section.name, target, len(section.documents), pages))
            logger.info("    => %d PDF pages, %d MiB", pages, _mib(target))

        complete_pdf: Path | None = None
        sections_zip: Path | None = None
        if results and options.complete:
            complete_pdf = out / COMPLETE_PDF_NAME
            logger.info("Merging complete manual...")
            pages = combine_section_pdfs(
                [(r.section, r.file) for r in results], complete_pdf, vehicle
            )
            logger.info("Combined: %d pages, %d MiB", pages, _mib(complete_pdf))
        if results and options.zip_sections:
            sections_zip = out / SECTIONS_ZIP_NAME
            logger.info("Packaging section PDFs...")
            write_sections_zip((r.file for r in results), sections_zip)

    manifest = Manifest(vehicle, tuple(results), complete_pdf, sections_zip)
    (out / MANIFEST_NAME).write_text(manifest.to_json(), encoding="utf-8")
    logger.info("Done: %s", out.resolve())
    return manifest
