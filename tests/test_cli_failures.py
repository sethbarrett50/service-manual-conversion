"""Environment and argument failures end with one clean error line and the right exit code."""

from __future__ import annotations

import errno
from pathlib import Path

import pytest

from lemon2pdf import assemble, pipeline
from lemon2pdf.cli import build_parser, main
from lemon2pdf.errors import Lemon2PdfError
from lemon2pdf.models import BuildOptions


def _run_cli(argv: list[str], capsys: pytest.CaptureFixture[str]) -> tuple[int, list[str], str]:
    code = main([*argv, "-q"])
    err = capsys.readouterr().err
    return code, err.splitlines(), err


def _assert_clean_error(code: int, lines: list[str], err: str) -> None:
    assert code == 1
    assert len(lines) == 1
    assert lines[0].startswith("error: ")
    assert "Traceback" not in err


def _build_dirs(temp: Path) -> list[Path]:
    return list(temp.glob("lemon_build_*"))


def test_help_lists_temp_dir():
    assert "--temp-dir DIR" in build_parser().format_help()


def test_build_dir_is_created_under_temp_dir_and_removed(
    manual_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    temp = tmp_path / "scratch"
    temp.mkdir()
    seen: list[list[Path]] = []
    real_discover = pipeline.discover

    def spy(*args, **kwargs):
        seen.append(_build_dirs(temp))
        return real_discover(*args, **kwargs)

    monkeypatch.setattr(pipeline, "discover", spy)
    options = BuildOptions(source=manual_dir, out=tmp_path / "out", temp_dir=temp)
    pipeline.build(options)
    assert len(seen) == 1
    assert len(seen[0]) == 1
    assert _build_dirs(temp) == []


def _no_space(*args, **kwargs):
    raise OSError(errno.ENOSPC, "No space left on device")


def test_disk_full_during_extraction(
    manual_zip: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys
):
    temp = tmp_path / "scratch"
    temp.mkdir()
    monkeypatch.setattr(pipeline, "safe_extract_zip", _no_space)
    code, lines, err = _run_cli(
        [str(manual_zip), "-o", str(tmp_path / "out"), "--temp-dir", str(temp)], capsys
    )
    _assert_clean_error(code, lines, err)
    assert str(temp) in err
    assert "--temp-dir" in err


def test_disk_full_during_rendering(
    manual_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys
):
    temp = tmp_path / "scratch"
    temp.mkdir()
    monkeypatch.setattr(assemble, "render_batch", _no_space)
    code, lines, err = _run_cli(
        [str(manual_dir), "-o", str(tmp_path / "out"), "--temp-dir", str(temp)], capsys
    )
    _assert_clean_error(code, lines, err)
    assert str(temp) in err
    assert "--temp-dir" in err
    assert _build_dirs(temp) == []


def test_disk_full_error_is_lemon2pdf_error(
    manual_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setattr(assemble, "render_batch", _no_space)
    with pytest.raises(Lemon2PdfError, match="--temp-dir"):
        pipeline.build(BuildOptions(source=manual_dir, out=tmp_path / "out"))


def test_missing_source(tmp_path: Path, capsys):
    code, lines, err = _run_cli([str(tmp_path / "nope"), "-o", str(tmp_path / "out")], capsys)
    _assert_clean_error(code, lines, err)


def test_source_is_regular_non_zip_file(tmp_path: Path, capsys):
    source = tmp_path / "notes.txt"
    source.write_text("not a manual", encoding="utf-8")
    code, lines, err = _run_cli([str(source), "-o", str(tmp_path / "out")], capsys)
    _assert_clean_error(code, lines, err)


def test_output_dir_not_writable(manual_dir: Path, tmp_path: Path, capsys):
    blocker = tmp_path / "blocker"
    blocker.write_text("a regular file", encoding="utf-8")
    code, lines, err = _run_cli([str(manual_dir), "-o", str(blocker / "out")], capsys)
    _assert_clean_error(code, lines, err)


def test_keyboard_interrupt_cleans_up(
    manual_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys
):
    temp = tmp_path / "scratch"
    temp.mkdir()
    seen: list[list[Path]] = []

    def interrupt(*args, **kwargs):
        seen.append(_build_dirs(temp))
        raise KeyboardInterrupt

    monkeypatch.setattr(pipeline, "discover", interrupt)
    code = main([str(manual_dir), "-o", str(tmp_path / "out"), "--temp-dir", str(temp), "-q"])
    assert code == 130
    assert len(seen[0]) == 1
    assert _build_dirs(temp) == []
