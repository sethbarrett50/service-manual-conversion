"""Index a LEMON manual: find content pages and group them into sections by breadcrumb."""

from __future__ import annotations

import logging
from collections.abc import Iterable, Sequence
from pathlib import Path

from bs4 import BeautifulSoup, Tag

from lemon2pdf.models import Document, Section

logger = logging.getLogger(__name__)

DEFAULT_SECTION = "General Information"
CRUMB_SKIP = 4
"""Leading breadcrumb parts (site / make / model / vehicle) that are the same on every page."""

NAV_MIN_ANCHORS = 25
NAV_LINK_RATIO = 0.55
MIN_EXTRA_TEXT = 15


def _page_number(path: Path) -> int:
    return int(path.stem) if path.stem.isdigit() else 10**12


def crumb_parts(soup: BeautifulSoup) -> list[str]:
    """Breadcrumb labels below the vehicle level."""
    crumbs = soup.select(".header a.breadcrumb-part")
    return [a.get_text(" ", strip=True) for a in crumbs][CRUMB_SKIP:]


def get_section(parts: Sequence[str]) -> str:
    """Map a breadcrumb trail to the section it belongs in."""
    if not parts:
        return DEFAULT_SECTION
    first = parts[0]
    if first.startswith("Repair and Diagnosis"):
        return parts[1] if len(parts) > 1 else DEFAULT_SECTION
    if first in ("Labor Times", "Parts and Labor"):
        idx = 2 if len(parts) > 2 and parts[1] == "Other Variant" else 1
        return f"Parts and Labor - {parts[idx]}" if len(parts) > idx else "Parts and Labor"
    return first


def is_navigation_page(main: Tag, title: str) -> bool:
    """True for pages that are only menus or link trees, with no procedure content.

    Their hierarchy is rebuilt as native PDF contents and bookmarks instead.
    """
    full_text = main.get_text(" ", strip=True)
    if "split tree" in full_text[:350].lower():
        return True
    anchors = main.select("a[href]")
    if len(anchors) > NAV_MIN_ANCHORS:
        link_chars = sum(len(a.get_text(" ", strip=True)) for a in anchors)
        if full_text and link_chars / len(full_text) > NAV_LINK_RATIO:
            return True
    stripped = BeautifulSoup(str(main), "html.parser")
    for tag in stripped.select("ul, button, script, nav"):
        tag.decompose()
    text = stripped.get_text(" ", strip=True)
    return len(text) <= len(title) + MIN_EXTRA_TEXT and not stripped.select("img, table")


def discover(root: Path, limit: int | None = None) -> list[Section]:
    """Group the numbered content pages under ``root/pages`` into ordered sections.

    Breadcrumbs on each page are used rather than the shallow navigation tree.
    ``limit`` caps the total number of documents (for quick test runs).
    """
    groups: dict[str, list[Document]] = {}
    total = 0
    pages = sorted((root / "pages").glob("*.html"), key=_page_number)
    for page in pages:
        if not page.stem.isdigit():
            continue
        soup = BeautifulSoup(page.read_bytes(), "html.parser")
        main = soup.select_one(".main")
        if main is None:
            logger.warning("Skipping page %s: no .main content element", page.name)
            continue
        heading = main.select_one("h1")
        title = heading.get_text(" ", strip=True) if heading else f"Page {page.stem}"
        if is_navigation_page(main, title):
            logger.debug("Skipping navigation page %s", page.name)
            continue
        parts = crumb_parts(soup)
        doc = Document(id=int(page.stem), title=title, path=" > ".join(parts))
        groups.setdefault(get_section(parts), []).append(doc)
        total += 1
        if limit and total >= limit:
            break
    return [Section(name, tuple(docs)) for name, docs in groups.items()]


def filter_sections(sections: Iterable[Section], terms: Sequence[str]) -> list[Section]:
    """Keep sections whose name contains any of ``terms`` (case-insensitive)."""
    if not terms:
        return list(sections)
    folded = [t.casefold() for t in terms]
    return [s for s in sections if any(t in s.name.casefold() for t in folded)]
