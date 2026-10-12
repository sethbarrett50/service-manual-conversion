"""Opt-in integration test against a real LEMON export.

Set ``LEMON2PDF_SAMPLE_ZIP`` to the path of an export ZIP to run it; it is skipped otherwise
(real exports are large and not redistributable in this repository).
"""

import os
from pathlib import Path

import pymupdf
import pytest

from lemon2pdf.models import BuildOptions
from lemon2pdf.pipeline import build

SAMPLE = os.environ.get("LEMON2PDF_SAMPLE_ZIP")

pytestmark = pytest.mark.skipif(not SAMPLE, reason="LEMON2PDF_SAMPLE_ZIP not set")


def test_real_export_sample(tmp_path: Path):
    assert SAMPLE is not None
    manifest = build(BuildOptions(source=Path(SAMPLE), out=tmp_path, max_documents=60))
    assert manifest.sections
    assert sum(s.documents for s in manifest.sections) == 60
    assert manifest.complete_pdf is not None
    with pymupdf.open(manifest.complete_pdf) as pdf:
        assert len(pdf) == -(-len(manifest.sections) // 42) + sum(
            s.pages for s in manifest.sections
        )
        for link in pdf[0].get_links():
            assert 0 <= link["page"] < len(pdf)
