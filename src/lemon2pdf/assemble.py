"""Assemble rendered batches into section PDFs and the combined manual, with linked contents."""

from __future__ import annotations

import logging
import re
from collections.abc import Sequence
from pathlib import Path

import pymupdf

from lemon2pdf.models import Document, Section
from lemon2pdf.render import A4, render_batch

logger = logging.getLogger(__name__)

TOC_ROWS_PER_PAGE = 48
TOC_TITLE_CHARS = 77
OUTLINE_TITLE_CHARS = 110
MASTER_ROWS_PER_PAGE = 42
MASTER_TITLE_CHARS = 78
SOURCE_SCAN_CHARS = 1500

_SOURCE_RE = re.compile(r"\[source\s+(\d+)\]")


def _toc_row_y(row: int) -> float:
    return 66 + row * 15.5


def _master_row_y(row: int) -> float:
    return 75 + row * 17


def add_contents(
    pdf: pymupdf.Document,
    label: str,
    entries: Sequence[Document],
    target_pages: Sequence[int],
    contents_title: str = "Contents",
) -> int:
    """Prepend clickable contents pages to ``pdf``; return how many pages were added.

    ``target_pages`` are 0-based page indices in ``pdf`` before the contents are inserted.
    """
    count = max(1, -(-len(entries) // TOC_ROWS_PER_PAGE))
    index = pymupdf.open()
    for i in range(count):
        page = index.new_page(width=A4[0], height=A4[1])
        page.insert_text((38, 38), f"{label} — {contents_title} ({i + 1}/{count})", fontsize=13)
        chunk = entries[i * TOC_ROWS_PER_PAGE : (i + 1) * TOC_ROWS_PER_PAGE]
        for j, entry in enumerate(chunk):
            k = i * TOC_ROWS_PER_PAGE + j
            y = _toc_row_y(j)
            title = entry.title.replace("\n", " ")[:TOC_TITLE_CHARS]
            page.insert_text((40, y), title, fontsize=8)
            page.insert_text((548, y), str(target_pages[k] + count + 1), fontsize=8)
    # Links are added after insertion so their targets refer to the destination PDF.
    pdf.insert_pdf(index, start_at=0, links=False)
    index.close()
    for k, target in enumerate(target_pages):
        page = pdf[k // TOC_ROWS_PER_PAGE]
        y = _toc_row_y(k % TOC_ROWS_PER_PAGE)
        page.insert_link(
            {
                "kind": pymupdf.LINK_GOTO,
                "from": pymupdf.Rect(35, y - 12, 566, y + 3),
                "page": target + count,
            }
        )
    return count


def _document_start_pages(pdf: pymupdf.Document) -> dict[int, int]:
    """Map source document id to the 0-based page its heading appears on.

    Named destinations do not survive ``insert_pdf`` reliably, so the ``[source N]`` tag
    printed in each heading is located instead.
    """
    found: dict[int, int] = {}
    for p in range(len(pdf)):
        text = pdf[p].get_text("text")[:SOURCE_SCAN_CHARS]
        for match in _SOURCE_RE.finditer(text):
            found.setdefault(int(match.group(1)), p)
    return found


def build_section(
    root: Path,
    vehicle: str,
    section: Section,
    destination: Path,
    temp_root: Path,
    batch_size: int,
) -> int:
    """Render ``section`` to ``destination`` in batches; return its page count."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    docs = section.documents
    out = pymupdf.open()
    entries: list[Document] = []
    positions: list[int] = []
    for part_idx, offset in enumerate(range(0, len(docs), batch_size)):
        subset = docs[offset : offset + batch_size]
        part = temp_root / f"part_{part_idx:04}.pdf"
        logger.info("    batch %d: %d documents", part_idx + 1, len(subset))
        render_batch(root, vehicle, section.name, subset, part)
        batch = pymupdf.open(part)
        found = _document_start_pages(batch)
        for doc in subset:
            positions.append(len(out) + found.get(doc.id, 0))
            entries.append(doc)
        out.insert_pdf(batch)
        batch.close()
        part.unlink(missing_ok=True)
    shift = add_contents(out, section.name, entries, positions)
    toc: list[list[int | str]] = [[1, section.name, 1]]
    toc.extend(
        [2, e.title[:OUTLINE_TITLE_CHARS], p + shift + 1]
        for e, p in zip(entries, positions, strict=True)
    )
    out.set_toc(toc)
    out.save(destination, garbage=0, deflate=False)
    pages = len(out)
    out.close()
    return pages


def combine_section_pdfs(
    section_files: Sequence[tuple[str, Path]], destination: Path, vehicle: str
) -> int:
    """Merge section PDFs behind a linked master contents page; return the page count."""
    merged = pymupdf.open()
    start_pages: list[int] = []
    for _, path in section_files:
        with pymupdf.open(path) as part:
            start_pages.append(len(merged))
            merged.insert_pdf(part)

    master = pymupdf.open()
    for idx in range(0, len(section_files), MASTER_ROWS_PER_PAGE):
        page = master.new_page(width=A4[0], height=A4[1])
        page.insert_text((40, 40), f"{vehicle} — Master Contents", fontsize=16)
        for j, (name, _) in enumerate(section_files[idx : idx + MASTER_ROWS_PER_PAGE]):
            page.insert_text((44, _master_row_y(j)), name[:MASTER_TITLE_CHARS], fontsize=10)
    merged.insert_pdf(master, start_at=0, links=False)
    shift = len(master)
    master.close()

    for row, start in enumerate(start_pages):
        page = merged[row // MASTER_ROWS_PER_PAGE]
        y = _master_row_y(row % MASTER_ROWS_PER_PAGE)
        page.insert_link(
            {
                "kind": pymupdf.LINK_GOTO,
                "from": pymupdf.Rect(40, y - 12, 550, y + 3),
                "page": start + shift,
            }
        )

    outline: list[list[int | str]] = [[1, "Master Contents", 1]]
    for (name, path), start in zip(section_files, start_pages, strict=True):
        outline.append([1, name, start + shift + 1])
        with pymupdf.open(path) as part:
            outline.extend(
                [level, title, start + shift + page]
                for level, title, page in part.get_toc()
                if level > 1
            )
    merged.set_toc(outline)
    merged.save(destination, garbage=0, deflate=False)
    pages = len(merged)
    merged.close()
    return pages
