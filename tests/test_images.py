from __future__ import annotations

import json
import logging
from pathlib import Path

import pymupdf
import pytest
from bs4 import BeautifulSoup
from PIL import Image
from reportlab.platypus import Image as RLImage

from lemon2pdf.models import BuildOptions, ImageStats
from lemon2pdf.pipeline import MANIFEST_NAME, build
from lemon2pdf.render import MAX_IMAGE_HEIGHT, MAX_IMAGE_WIDTH, image_flowables


def _tag(src: str):
    return BeautifulSoup(f'<img src="{src}">', "html.parser").img


def _manual(tmp_path: Path, images: dict[str, str]) -> Path:
    """A one-document manual whose page references ``images`` (file name -> src)."""
    root = tmp_path / "Manual"
    pages = root / "pages"
    pages.mkdir(parents=True)
    (root / "index.html").write_text("<html></html>", encoding="utf-8")
    body = "<p>Text.</p>" + "".join(f'<img src="{src}">' for src in images.values())
    (pages / "2.html").write_text(
        '<html><body><div class="header">'
        + "".join(
            f'<a class="breadcrumb-part" href="#">{c}</a>'
            for c in ["Home", "Make", "Model", "Vehicle", "Repair and Diagnosis", "Brakes"]
        )
        + f'</div><div class="main"><h1>Doc</h1>{body}</div></body></html>',
        encoding="utf-8",
    )
    return root


def _unreadable_manual(tmp_path: Path) -> Path:
    root = _manual(tmp_path, {"bad": "bad.png"})
    (root / "pages" / "bad.png").write_bytes(b"not an image")
    return root


def test_manifest_counts_each_kind(tmp_path: Path):
    root = _manual(
        tmp_path,
        {
            "ok": "ok.png",
            "missing": "nope.png",
            "remote": "https://example.com/a.png",
            "outside": "../../outside.png",
            "bad": "bad.png",
        },
    )
    Image.new("RGB", (10, 10)).save(root / "pages" / "ok.png")
    Image.new("RGB", (10, 10)).save(tmp_path / "outside.png")
    (root / "pages" / "bad.png").write_bytes(b"not an image")

    out = tmp_path / "out"
    manifest = build(BuildOptions(source=root, out=out))

    expected = {
        "placed": 1,
        "skipped": {"missing": 1, "remote": 1, "outside_root": 1, "unreadable": 1},
    }
    assert manifest.to_dict()["images"] == expected
    assert json.loads((out / MANIFEST_NAME).read_text(encoding="utf-8"))["images"] == expected


def test_summary_is_warning_when_skipped(tmp_path: Path, caplog: pytest.LogCaptureFixture):
    root = _unreadable_manual(tmp_path)
    with caplog.at_level(logging.INFO, logger="lemon2pdf"):
        build(BuildOptions(source=root, out=tmp_path / "out"))
    summaries = [r for r in caplog.records if r.getMessage().startswith("Images:")]
    assert len(summaries) == 1
    assert summaries[0].levelno == logging.WARNING


def test_summary_is_info_when_nothing_skipped(tmp_path: Path, caplog: pytest.LogCaptureFixture):
    root = _manual(tmp_path, {"ok": "ok.png"})
    Image.new("RGB", (10, 10)).save(root / "pages" / "ok.png")
    with caplog.at_level(logging.INFO, logger="lemon2pdf"):
        build(BuildOptions(source=root, out=tmp_path / "out"))
    summaries = [r for r in caplog.records if r.getMessage().startswith("Images:")]
    assert len(summaries) == 1
    assert summaries[0].levelno == logging.INFO


def test_unreadable_logs_one_line_without_traceback(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
):
    root = _unreadable_manual(tmp_path)
    with caplog.at_level(logging.WARNING, logger="lemon2pdf"):
        build(BuildOptions(source=root, out=tmp_path / "out"))
    skipping = [r for r in caplog.records if "unreadable image" in r.getMessage()]
    assert len(skipping) == 1
    assert "bad.png" in skipping[0].getMessage()
    assert "Traceback" not in caplog.text


def test_unreadable_traceback_goes_to_debug(tmp_path: Path, caplog: pytest.LogCaptureFixture):
    root = _unreadable_manual(tmp_path)
    with caplog.at_level(logging.DEBUG, logger="lemon2pdf"):
        build(BuildOptions(source=root, out=tmp_path / "out"))
    assert "Traceback" in caplog.text
    assert all(r.exc_info is None for r in caplog.records if r.levelno >= logging.WARNING)


def _save_cmyk_jpeg(path: Path) -> None:
    Image.new("CMYK", (30, 20), (0, 128, 128, 0)).save(path, "JPEG")


def _save_progressive_jpeg(path: Path) -> None:
    Image.new("RGB", (30, 20), "blue").save(path, "JPEG", progressive=True)


def _save_palette_png(path: Path) -> None:
    Image.new("P", (30, 20), 3).save(path, "PNG")


def _save_rgba_png(path: Path) -> None:
    Image.new("RGBA", (30, 20), (255, 0, 0, 100)).save(path, "PNG")


def _save_gif(path: Path) -> None:
    Image.new("P", (30, 20), 1).save(path, "GIF")


@pytest.mark.parametrize(
    ("name", "save"),
    [
        ("cmyk.jpg", _save_cmyk_jpeg),
        ("progressive.jpg", _save_progressive_jpeg),
        ("palette.png", _save_palette_png),
        ("rgba.png", _save_rgba_png),
        ("anim.gif", _save_gif),
    ],
)
def test_image_formats_are_placed(tmp_path: Path, name: str, save):
    root = _manual(tmp_path, {"img": name})
    save(root / "pages" / name)

    manifest = build(BuildOptions(source=root, out=tmp_path / "out"))

    assert manifest.images.placed == 1
    assert manifest.images.skipped == 0
    assert manifest.complete_pdf is not None
    with pymupdf.open(manifest.sections[0].file) as pdf:
        assert any(page.get_images() for page in pdf)


@pytest.mark.parametrize(
    ("size", "scaled"),
    [((4000, 100), True), ((100, 4000), True), ((10, 10), False)],
)
def test_scaling(tmp_path: Path, size: tuple[int, int], scaled: bool):
    root = tmp_path / "Manual"
    (root / "pages").mkdir(parents=True)
    Image.new("RGB", size).save(root / "pages" / "img.png")

    stats = ImageStats()
    image = image_flowables(_tag("img.png"), root, stats)[0]
    assert isinstance(image, RLImage)

    assert stats.placed == 1
    assert image.drawWidth <= MAX_IMAGE_WIDTH
    assert image.drawHeight <= MAX_IMAGE_HEIGHT
    assert image.drawWidth / image.drawHeight == pytest.approx(size[0] / size[1], rel=0.01)
    if not scaled:
        assert (image.drawWidth, image.drawHeight) == size


PX_TO_PT = 0.75  # svglib converts user units (px) to points

_SVG = (
    '<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}">'
    '<rect x="0" y="0" width="{w}" height="{h}" fill="red"/>'
    '<circle cx="50" cy="50" r="40" fill="blue"/></svg>'
)


def test_svg_is_placed_as_vector(tmp_path: Path):
    root = _manual(tmp_path, {"icon": "icons/wrench.svg"})
    (root / "pages" / "icons").mkdir()
    (root / "pages" / "icons" / "wrench.svg").write_text(_SVG.format(w=200, h=100))

    manifest = build(BuildOptions(source=root, out=tmp_path / "out"))

    assert manifest.images.placed == 1
    assert manifest.images.skipped == 0
    with pymupdf.open(manifest.sections[0].file) as pdf:
        assert any(page.get_drawings() or page.get_images() for page in pdf)


@pytest.mark.parametrize(
    ("size", "scaled"),
    [((4000, 100), True), ((100, 4000), True), ((200, 100), False)],
)
def test_svg_scaling(tmp_path: Path, size: tuple[int, int], scaled: bool):
    root = tmp_path / "Manual"
    (root / "pages").mkdir(parents=True)
    (root / "pages" / "img.svg").write_text(_SVG.format(w=size[0], h=size[1]))

    stats = ImageStats()
    drawing = image_flowables(_tag("img.svg"), root, stats)[0]

    assert stats.placed == 1
    assert drawing.width <= MAX_IMAGE_WIDTH + 1e-6
    assert drawing.height <= MAX_IMAGE_HEIGHT + 1e-6
    assert drawing.width / drawing.height == pytest.approx(size[0] / size[1], rel=0.01)
    if not scaled:
        assert (drawing.width, drawing.height) == (size[0] * PX_TO_PT, size[1] * PX_TO_PT)


def test_malformed_svg_is_unreadable(tmp_path: Path, caplog: pytest.LogCaptureFixture):
    root = _manual(tmp_path, {"bad": "bad.svg"})
    (root / "pages" / "bad.svg").write_text("<svg><rect")

    with caplog.at_level(logging.WARNING, logger="lemon2pdf"):
        manifest = build(BuildOptions(source=root, out=tmp_path / "out"))

    assert manifest.images.placed == 0
    assert manifest.to_dict()["images"]["skipped"]["unreadable"] == 1
    assert len([r for r in caplog.records if "unreadable image" in r.getMessage()]) == 1
    assert manifest.complete_pdf is not None
