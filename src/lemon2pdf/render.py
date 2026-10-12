"""Render manual HTML pages into reflowed ReportLab PDFs."""

from __future__ import annotations

import html
import logging
from collections.abc import Sequence
from pathlib import Path
from urllib.parse import unquote, urlparse

from bs4 import BeautifulSoup, NavigableString, PageElement, Tag
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.styles import ParagraphStyle, PropertySet, StyleSheet1, getSampleStyleSheet
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen.canvas import Canvas
from reportlab.platypus import (
    BaseDocTemplate,
    Flowable,
    Frame,
    Image,
    PageBreak,
    PageTemplate,
    Paragraph,
    Spacer,
)

from lemon2pdf.models import Document, ImageStats

logger = logging.getLogger(__name__)

A4 = (595.28, 841.89)
MARGIN_X = 48
MAX_IMAGE_WIDTH = 485
MAX_IMAGE_HEIGHT = 670
FOOTER_LABEL_CHARS = 85

SOURCE_TAG = "[source {id}]"
"""Printed after each document title so its start page can be found after merging."""

_BLOCK_TAGS = ("h2", "h3", "h4", "p", "pre", "li")
_CONTAINER_TAGS = ("div", "section", "article", "ul", "ol", "blockquote")


def build_styles() -> StyleSheet1:
    s = getSampleStyleSheet()
    s.add(
        ParagraphStyle(
            name="LTitle",
            parent=s["Heading1"],
            fontSize=14,
            leading=17,
            spaceBefore=7,
            spaceAfter=7,
            keepWithNext=True,
        )
    )
    s.add(
        ParagraphStyle(
            name="LCrumb",
            parent=s["Normal"],
            fontSize=7,
            leading=10,
            textColor=colors.grey,
            spaceAfter=8,
        )
    )
    s.add(
        ParagraphStyle(name="LBody", parent=s["BodyText"], fontSize=9, leading=12.5, spaceAfter=5)
    )
    s.add(
        ParagraphStyle(
            name="LSubhead",
            parent=s["Heading3"],
            fontSize=10,
            leading=13,
            spaceBefore=7,
            spaceAfter=4,
            keepWithNext=True,
        )
    )
    s.add(
        ParagraphStyle(
            name="LFront", parent=s["Title"], fontSize=20, leading=25, alignment=TA_CENTER
        )
    )
    return s


def normalize_text(text: str) -> str:
    """Collapse whitespace and escape for ReportLab's paragraph markup."""
    return html.escape(" ".join(text.split()), quote=False)


def image_flowables(tag: Tag, root: Path, stats: ImageStats) -> list[Flowable]:
    """Flowables for a local ``<img>``; skipped images are counted in ``stats`` by reason."""
    src = tag.get("src")
    if not isinstance(src, str) or not src:
        stats.missing += 1
        return []
    parsed = urlparse(src)
    if parsed.scheme or parsed.netloc:
        stats.remote += 1
        return []
    path = (root / "pages" / unquote(parsed.path)).resolve()
    if not path.is_relative_to(root.resolve()):
        stats.outside_root += 1
        return []
    if not path.is_file():
        stats.missing += 1
        return []
    try:
        width, height = ImageReader(str(path)).getSize()
    except Exception as exc:  # ReportLab/Pillow raise many types for bad images
        stats.unreadable += 1
        logger.warning("Skipping unreadable image %s: %s", path, exc)
        logger.debug("Traceback for unreadable image %s", path, exc_info=True)
        return []
    stats.placed += 1
    ratio = min(MAX_IMAGE_WIDTH / width, MAX_IMAGE_HEIGHT / height, 1)
    return [Image(str(path), width=width * ratio, height=height * ratio), Spacer(1, 5)]


class _FlowableBuilder:
    """Walks an HTML subtree, buffering inline text into paragraphs."""

    def __init__(self, root: Path, styles: StyleSheet1, stats: ImageStats) -> None:
        self.root = root
        self.stats = stats
        self.styles = styles
        self.result: list[Flowable] = []
        self._buf: list[str] = []

    def flush(self, style: str = "LBody") -> None:
        value = "".join(self._buf).strip()
        self._buf.clear()
        if value:
            self.result.append(Paragraph(normalize_text(value), self.styles[style]))

    def walk(self, node: PageElement) -> None:
        if isinstance(node, NavigableString):
            self._buf.append(str(node))
            return
        if not isinstance(node, Tag):
            return
        kind = node.name
        if kind == "h1":
            return
        if kind == "br":
            self.flush()
        elif kind == "img":
            self.flush()
            self.result.extend(image_flowables(node, self.root, self.stats))
        elif kind == "table":
            self.flush()
            self._table(node)
        elif kind in _BLOCK_TAGS:
            self.flush()
            if kind == "li":
                self._buf.append("• ")
            self._children(node)
            self.flush("LSubhead" if kind.startswith("h") else "LBody")
        elif kind in _CONTAINER_TAGS:
            self.flush()
            self._children(node)
            self.flush()
        else:
            self._children(node)

    def _children(self, node: Tag) -> None:
        for child in node.children:
            self.walk(child)

    def _table(self, table: Tag) -> None:
        for tr in table.select("tr"):
            values = [td.get_text(" ", strip=True) for td in tr.find_all(["th", "td"])]
            if any(values):
                self.result.append(
                    Paragraph(normalize_text(" | ".join(values)), self.styles["LBody"])
                )


def html_to_flowables(
    main: Tag, root: Path, styles: StyleSheet1, stats: ImageStats
) -> list[Flowable]:
    """Convert a page's ``.main`` element into flowables. Mutates ``main``."""
    for tag in main.select("script, button, nav"):
        tag.decompose()
    builder = _FlowableBuilder(root, styles, stats)
    for child in main.children:
        builder.walk(child)
    builder.flush()
    return builder.result


class DocumentHeading(Paragraph):
    """Title paragraph that remembers which source document it starts."""

    def __init__(self, text: str, style: PropertySet, document_id: int) -> None:
        super().__init__(text, style)
        self.document_id = document_id


class TaggedDoc(BaseDocTemplate):
    """A4 document with a label/page-number footer and a bookmark per document heading."""

    def __init__(self, path: Path, label: str, *, page_compression: int = 1) -> None:
        super().__init__(
            str(path),
            pagesize=A4,
            leftMargin=MARGIN_X,
            rightMargin=MARGIN_X,
            topMargin=47,
            bottomMargin=43,
            pageCompression=page_compression,
        )
        self.label = label
        frame = Frame(
            MARGIN_X,
            43,
            A4[0] - 2 * MARGIN_X,
            A4[1] - 90,
            leftPadding=0,
            rightPadding=0,
            topPadding=0,
            bottomPadding=0,
        )
        self.addPageTemplates([PageTemplate(id="normal", frames=frame, onPage=self.footer)])

    def footer(self, canv: Canvas, doc: BaseDocTemplate) -> None:
        canv.saveState()
        canv.setFont("Helvetica", 7)
        canv.setFillColor(colors.grey)
        canv.drawString(MARGIN_X, 25, self.label[:FOOTER_LABEL_CHARS])
        canv.drawRightString(A4[0] - MARGIN_X, 25, str(doc.page))
        canv.restoreState()

    def afterFlowable(self, flowable: Flowable) -> None:
        if isinstance(flowable, DocumentHeading):
            self.canv.bookmarkPage(f"item_{flowable.document_id}")


def render_batch(
    root: Path,
    vehicle: str,
    section: str,
    documents: Sequence[Document],
    path: Path,
    stats: ImageStats,
) -> None:
    """Render ``documents`` into one PDF at ``path``, each starting on a new page."""
    styles = build_styles()
    flow: list[Flowable] = []
    for i, doc in enumerate(documents):
        if i:
            flow.append(PageBreak())
        title = f"{doc.title}  {SOURCE_TAG.format(id=doc.id)}"
        flow.append(DocumentHeading(normalize_text(title), styles["LTitle"], doc.id))
        flow.append(Paragraph(normalize_text(doc.path), styles["LCrumb"]))
        soup = BeautifulSoup((root / "pages" / f"{doc.id}.html").read_bytes(), "html.parser")
        main = soup.select_one(".main")
        if main is not None:
            flow.extend(html_to_flowables(main, root, styles, stats))
    TaggedDoc(path, f"{vehicle} — {section}").build(flow)
