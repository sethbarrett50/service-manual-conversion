import json
import zipfile
from pathlib import Path

import pymupdf
import pytest

from lemon2pdf.cli import main
from lemon2pdf.errors import ConfigurationError
from lemon2pdf.models import BuildOptions
from lemon2pdf.pipeline import build, clean_name
from lemon2pdf.render import normalize_text


def test_clean_name():
    assert clean_name("Parts and Labor - Engine/Cooling") == "parts_and_labor_engine_cooling"
    assert clean_name("!!!") == "general"
    assert len(clean_name("x" * 200)) == 90


def test_normalize_text_escapes_markup():
    assert normalize_text("  a <b>\n & c ") == "a &lt;b&gt; &amp; c"


def test_options_validation(tmp_path: Path):
    with pytest.raises(ConfigurationError):
        BuildOptions(source=tmp_path, batch_size=0)
    with pytest.raises(ConfigurationError):
        BuildOptions(source=tmp_path, max_documents=0)


def test_build_from_zip(manual_zip: Path, tmp_path: Path):
    out = tmp_path / "pdfs"
    manifest = build(BuildOptions(source=manual_zip, out=out, batch_size=1))

    assert manifest.vehicle.startswith("LEMON")
    assert [r.section for r in manifest.sections] == [
        "Brakes",
        "Engine",
        "Parts and Labor - Cooling",
    ]
    brakes = manifest.sections[0]
    assert brakes.file == out / "sections" / "01_brakes.pdf"
    assert brakes.documents == 2

    with pymupdf.open(brakes.file) as pdf:
        assert len(pdf) == brakes.pages
        toc = pdf.get_toc()
        assert toc[0][:2] == [1, "Brakes"]
        assert [t[1] for t in toc[1:]] == ["Brake Pad Replacement", "Caliper Removal"]
        # contents page links land on the page whose heading carries the source tag
        links = [link["page"] for link in pdf[0].get_links()]
        assert len(links) == 2
        assert "[source 2]" in pdf[links[0]].get_text()
        assert "[source 3]" in pdf[links[1]].get_text()

    assert manifest.complete_pdf is not None
    with pymupdf.open(manifest.complete_pdf) as pdf:
        top = [t[1] for t in pdf.get_toc() if t[0] == 1]
        assert top == ["Master Contents", "Brakes", "Engine", "Parts and Labor - Cooling"]

    assert manifest.sections_zip is not None
    with zipfile.ZipFile(manifest.sections_zip) as zf:
        assert len(zf.namelist()) == 3

    on_disk = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
    assert on_disk == manifest.to_dict()


def test_cli_section_filter_and_skips(manual_dir: Path, tmp_path: Path):
    out = tmp_path / "cli"
    code = main([str(manual_dir), "--out", str(out), "--section", "engine", "--no-zip", "-q"])
    assert code == 0
    assert [p.name for p in (out / "sections").iterdir()] == ["01_engine.pdf"]
    assert not (out / "sectioned_manuals.zip").exists()
    assert (out / "complete_navigable_manual.pdf").exists()


def test_cli_reports_errors(tmp_path: Path, capsys):
    assert main([str(tmp_path / "missing"), "--out", str(tmp_path / "o")]) == 1
    assert "error:" in capsys.readouterr().err
