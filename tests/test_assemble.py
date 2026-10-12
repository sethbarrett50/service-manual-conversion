import re
from pathlib import Path

import pymupdf

from lemon2pdf.models import BuildOptions
from lemon2pdf.pipeline import build

# Long enough that the heading wraps between "[source" and the id.
WRAPPING_TITLE = "B" * 43


def test_contents_link_survives_wrapped_source_tag(manual_dir: Path, tmp_path: Path):
    page = manual_dir / "pages" / "3.html"
    html = page.read_text(encoding="utf-8")
    page.write_text(html.replace("Caliper Removal", WRAPPING_TITLE), encoding="utf-8")

    manifest = build(BuildOptions(source=manual_dir, out=tmp_path / "out", batch_size=2))

    with pymupdf.open(manifest.sections[0].file) as pdf:
        links = sorted(pdf[0].get_links(), key=lambda link: link["from"].y0)
        assert len(links) == 2
        wrapped = [
            n for n, pg in enumerate(pdf) if re.search(r"\[source\s*\n\s*3\]", pg.get_text("text"))
        ]
        assert len(wrapped) == 1, "title no longer wraps the tag"
        assert links[1]["page"] == wrapped[0]
