"""Opt-in integration test against real LEMON exports.

Set ``LEMON2PDF_SAMPLE_ZIP`` to one or more export ZIP paths, separated by ``os.pathsep``, to run
it once per ZIP; it is skipped otherwise (real exports are large and not redistributable in this
repository).
"""

import os
import zipfile
from pathlib import Path

import pymupdf
import pytest

from lemon2pdf.archive import find_root, safe_extract_zip
from lemon2pdf.assemble import MASTER_ROWS_PER_PAGE, TOC_ROWS_PER_PAGE
from lemon2pdf.discovery import discover
from lemon2pdf.models import BuildOptions
from lemon2pdf.pipeline import build
from lemon2pdf.render import SOURCE_TAG

MAX_DOCUMENTS = 60
SAMPLES = [Path(p) for p in os.environ.get("LEMON2PDF_SAMPLE_ZIP", "").split(os.pathsep) if p]


def _contents_links(pdf: pymupdf.Document, rows: int) -> list[dict]:
    """Contents-page links of a section PDF in row order."""
    pages = max(1, -(-rows // TOC_ROWS_PER_PAGE))
    links = []
    for p in range(pages):
        links.extend(sorted(pdf[p].get_links(), key=lambda link: link["from"].y0))
    return links


@pytest.mark.skipif(not SAMPLES, reason="LEMON2PDF_SAMPLE_ZIP not set")
@pytest.mark.parametrize("sample", SAMPLES, ids=[p.stem for p in SAMPLES])
def test_real_export_sample(sample: Path, tmp_path: Path):
    out = tmp_path / "out"
    manifest = build(BuildOptions(source=sample, out=out, max_documents=MAX_DOCUMENTS))
    assert manifest.sections
    assert sum(s.documents for s in manifest.sections) == MAX_DOCUMENTS
    assert manifest.complete_pdf is not None
    assert manifest.sections_zip is not None

    extracted = tmp_path / "extracted"
    extracted.mkdir()
    safe_extract_zip(sample, extracted)
    sections = discover(find_root(extracted), MAX_DOCUMENTS)
    assert [s.name for s in sections] == [r.section for r in manifest.sections]

    for section, result in zip(sections, manifest.sections, strict=True):
        with pymupdf.open(result.file) as pdf:
            links = _contents_links(pdf, len(section.documents))
            assert len(links) == len(section.documents)
            for doc, link in zip(section.documents, links, strict=True):
                tag = SOURCE_TAG.format(id=doc.id)
                text = " ".join(pdf[link["page"]].get_text("text").split())
                assert tag in text, (result.section, doc.id)

    with pymupdf.open(manifest.complete_pdf) as pdf:
        master_pages = -(-len(manifest.sections) // MASTER_ROWS_PER_PAGE)
        assert len(pdf) == master_pages + sum(s.pages for s in manifest.sections)
        for link in pdf[0].get_links():
            assert 0 <= link["page"] < len(pdf)
        toc_pages = [page for _, _, page in pdf.get_toc()]
        assert toc_pages == sorted(toc_pages)

    with zipfile.ZipFile(manifest.sections_zip) as archive:
        assert archive.testzip() is None
