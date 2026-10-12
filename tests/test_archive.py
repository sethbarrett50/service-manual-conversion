import io
import stat
import sys
import uuid
import zipfile
from pathlib import Path

import pytest

from lemon2pdf.archive import find_root, safe_extract_zip, write_sections_zip
from lemon2pdf.cli import main
from lemon2pdf.errors import (
    ArchiveTooLargeError,
    CorruptArchiveError,
    ManualNotFoundError,
    UnsafeArchiveError,
)


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


def _run_cli(argv: list[str], capsys: pytest.CaptureFixture[str]) -> tuple[int, list[str], str]:
    code = main([*argv, "-q"])
    err = capsys.readouterr().err
    return code, err.splitlines(), err


def _assert_clean_error(code: int, lines: list[str], err: str) -> None:
    assert code == 1
    assert len(lines) == 1
    assert lines[0].startswith("error: ")
    assert "Traceback" not in err


def _valid_zip_bytes() -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("a.txt", "hello world " * 200)
    return buf.getvalue()


def _corrupt_cases() -> dict[str, bytes]:
    data = _valid_zip_bytes()
    bad_crc = bytearray(data)
    bad_crc[30 + len("a.txt") + 4] ^= 0xFF
    stored = io.BytesIO()
    with zipfile.ZipFile(stored, "w") as zf:
        zf.writestr("a.txt", "hello world " * 200)
    stored_bad = bytearray(stored.getvalue())
    stored_bad[30 + len("a.txt") + 4] ^= 0xFF
    return {
        "not_a_zip": b"this is not a zip file" * 10,
        "truncated": data[: len(data) // 2],
        "bad_crc_stored": bytes(stored_bad),
        "bad_deflate_stream": bytes(bad_crc),
    }


@pytest.mark.parametrize("case", list(_corrupt_cases()))
def test_corrupt_archive_is_clean_error(case: str, tmp_path: Path, capsys):
    archive = tmp_path / "bad.zip"
    archive.write_bytes(_corrupt_cases()[case])
    dest = tmp_path / "dest"
    dest.mkdir()
    with pytest.raises(CorruptArchiveError):
        safe_extract_zip(archive, dest)
    code, lines, err = _run_cli([str(archive), "-o", str(tmp_path / "out")], capsys)
    _assert_clean_error(code, lines, err)


def test_symlink_member_rejected(tmp_path: Path):
    archive = tmp_path / "link.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("ok.txt", "fine")
        link = zipfile.ZipInfo("link")
        link.create_system = 3
        link.external_attr = (stat.S_IFLNK | 0o777) << 16
        zf.writestr(link, "ok.txt")
    dest = tmp_path / "dest"
    dest.mkdir()
    with pytest.raises(UnsafeArchiveError, match="link"):
        safe_extract_zip(archive, dest)
    assert list(dest.iterdir()) == []


def test_oversized_archive_rejected_before_extraction(tmp_path: Path):
    archive = tmp_path / "big.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("a.txt", "x" * 100)
        zf.writestr("b.txt", "y" * 100)
    dest = tmp_path / "dest"
    dest.mkdir()
    with pytest.raises(ArchiveTooLargeError):
        safe_extract_zip(archive, dest, max_uncompressed_bytes=199)
    assert list(dest.iterdir()) == []
    safe_extract_zip(archive, dest, max_uncompressed_bytes=200)
    assert sorted(p.name for p in dest.iterdir()) == ["a.txt", "b.txt"]


def test_oversized_archive_via_cli(tmp_path: Path, capsys):
    archive = tmp_path / "big.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("a.txt", "x" * 2048)
    code, lines, err = _run_cli(
        [str(archive), "-o", str(tmp_path / "out"), "--max-uncompressed-gib", "0.000001"], capsys
    )
    _assert_clean_error(code, lines, err)


@pytest.mark.parametrize("name", ["../x", "/abs/x", "C:/x", "C:\\x", "..\\x"])
def test_hostile_member_names_stay_inside_destination(name: str, tmp_path: Path):
    base = f"x_{uuid.uuid4().hex}"
    member = name[:-1] + base
    archive = tmp_path / "evil.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr(member, "data")
    sandbox = tmp_path / "sandbox"
    dest = sandbox / "dest"
    dest.mkdir(parents=True)
    try:
        safe_extract_zip(archive, dest)
    except UnsafeArchiveError:
        assert list(dest.iterdir()) == []
    else:
        written = [p for p in dest.rglob("*") if p.is_file()]
        assert len(written) == 1
        assert written[0].resolve().is_relative_to(dest.resolve())
    escapes = [Path("/abs") / base, sandbox / base, tmp_path.parent / base]
    if sys.platform == "win32":
        escapes.append(Path("C:/") / base)
    assert [p for p in escapes if p.exists()] == []
