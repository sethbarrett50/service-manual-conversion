import zipfile
from pathlib import Path

import pytest

from lemon2pdf.archive import find_root, safe_extract_zip, write_sections_zip
from lemon2pdf.errors import ManualNotFoundError, UnsafeArchiveError


def test_safe_extract_rejects_traversal(tmp_path: Path):
    archive = tmp_path / "evil.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("../escape.txt", "nope")
    dest = tmp_path / "dest"
    dest.mkdir()
    with pytest.raises(UnsafeArchiveError, match=r"escape\.txt"):
        safe_extract_zip(archive, dest)
    assert not (tmp_path / "escape.txt").exists()


def test_find_root_in_extracted_zip(manual_zip: Path, manual_dir: Path, tmp_path: Path):
    dest = tmp_path / "out"
    dest.mkdir()
    safe_extract_zip(manual_zip, dest)
    assert find_root(dest).name == manual_dir.name


def test_find_root_missing(tmp_path: Path):
    with pytest.raises(ManualNotFoundError):
        find_root(tmp_path)


def test_write_sections_zip(tmp_path: Path):
    files = []
    for name in ("a.pdf", "b.pdf"):
        f = tmp_path / name
        f.write_bytes(b"%PDF-1.4")
        files.append(f)
    archive = tmp_path / "s.zip"
    write_sections_zip(files, archive)
    with zipfile.ZipFile(archive) as zf:
        assert sorted(zf.namelist()) == ["a.pdf", "b.pdf"]
