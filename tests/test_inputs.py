"""Input shapes: unusual but valid layouts convert, non-LEMON input fails cleanly."""

import json
import logging
import shutil
import zipfile
from pathlib import Path

import pytest

from lemon2pdf.cli import main
from lemon2pdf.discovery import discover

PLAIN_COUNTS = {"Brakes": 2, "Engine": 1, "Parts and Labor - Cooling": 1}
LONG_NAME = "LEMON 2014 Nissan-Datsun Frontier PRO-4X, 4D Pickup, Automatic Trans"
UNICODE_NAME = "LEMON 2006 Škoda Octavia Kombi \u2013 Größe"


def zip_tree(tree: Path, archive: Path, base: Path) -> Path:
    with zipfile.ZipFile(archive, "w") as zf:
        for path in tree.rglob("*"):
            zf.write(path, arcname=path.relative_to(base))
    return archive


def convert(source: Path, out: Path, capsys: pytest.CaptureFixture[str]) -> dict:
    assert main([str(source), "--out", str(out), "-q"]) == 0
    capsys.readouterr()
    return json.loads((out / "manifest.json").read_text(encoding="utf-8"))


def counts(manifest: dict) -> dict[str, int]:
    return {s["section"]: s["documents"] for s in manifest["sections"]}


def test_zip_without_manual_fails_cleanly(tmp_path: Path, capsys: pytest.CaptureFixture[str]):
    archive = tmp_path / "other.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("readme.txt", "not a manual")
    assert main([str(archive), "--out", str(tmp_path / "o"), "-q"]) == 1
    lines = capsys.readouterr().err.splitlines()
    assert len(lines) == 1
    assert lines[0].startswith("error: No recognizable LEMON manual")


def test_plain_fixture_counts(manual_zip: Path, tmp_path: Path, capsys):
    manifest = convert(manual_zip, tmp_path / "out", capsys)
    assert counts(manifest) == PLAIN_COUNTS


def test_zip_nested_under_extra_folders(manual_dir: Path, tmp_path: Path, capsys):
    archive = tmp_path / "nested.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        for path in manual_dir.rglob("*"):
            arcname = Path("outer") / "inner" / path.relative_to(manual_dir.parent)
            zf.write(path, arcname=arcname)
    assert counts(convert(archive, tmp_path / "out", capsys)) == PLAIN_COUNTS


def test_zip_with_vehicle_at_root(manual_dir: Path, tmp_path: Path, capsys):
    archive = zip_tree(manual_dir, tmp_path / "root.zip", manual_dir)
    manifest = convert(archive, tmp_path / "out", capsys)
    assert counts(manifest) == PLAIN_COUNTS


def test_directory_at_vehicle_level(manual_dir: Path, tmp_path: Path, capsys):
    manifest = convert(manual_dir, tmp_path / "out", capsys)
    assert manifest["vehicle"] == manual_dir.name
    assert counts(manifest) == PLAIN_COUNTS


def test_directory_above_vehicle_level(manual_dir: Path, tmp_path: Path, capsys):
    manifest = convert(manual_dir.parent, tmp_path / "out", capsys)
    assert manifest["vehicle"] == manual_dir.name
    assert counts(manifest) == PLAIN_COUNTS


@pytest.mark.parametrize("name", [LONG_NAME, UNICODE_NAME])
@pytest.mark.parametrize("as_zip", [True, False])
def test_vehicle_folder_names(manual_dir: Path, tmp_path: Path, capsys, name: str, as_zip: bool):
    holder = tmp_path / "holder"
    holder.mkdir()
    renamed = holder / name
    shutil.copytree(manual_dir, renamed)
    source = zip_tree(renamed, tmp_path / "named.zip", holder) if as_zip else renamed
    manifest = convert(source, tmp_path / "out", capsys)
    assert manifest["vehicle"] == name
    assert counts(manifest) == PLAIN_COUNTS


@pytest.fixture
def propagate_logs(monkeypatch: pytest.MonkeyPatch):
    """cli.main turns off propagation on the package logger; caplog needs it on."""
    monkeypatch.setattr(logging.getLogger("lemon2pdf"), "propagate", True)


def test_page_without_main_is_skipped_with_warning(
    manual_dir: Path, tmp_path: Path, capsys, caplog, propagate_logs
):
    (manual_dir / "pages" / "3.html").write_text("<html><body>x</body></html>", encoding="utf-8")
    with caplog.at_level(logging.WARNING, logger="lemon2pdf.discovery"):
        sections = discover(manual_dir)
    assert {s.name: len(s.documents) for s in sections} == {
        "Brakes": 1,
        "Engine": 1,
        "Parts and Labor - Cooling": 1,
    }
    warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert len(warnings) == 1
    assert "3.html" in warnings[0].getMessage()

    manifest = convert(manual_dir, tmp_path / "out", capsys)
    assert sum(counts(manifest).values()) == 3


def test_missing_page_is_left_out(manual_dir: Path, tmp_path: Path, capsys):
    (manual_dir / "pages" / "3.html").unlink()
    manifest = convert(manual_dir, tmp_path / "out", capsys)
    assert counts(manifest) == {"Brakes": 1, "Engine": 1, "Parts and Labor - Cooling": 1}
