"""A tiny synthetic LEMON export, shaped like the real ones the parser expects."""

from __future__ import annotations

import zipfile
from pathlib import Path

import pytest
from PIL import Image

VEHICLE = "LEMON 2002 Test Car V6"
SITE_CRUMBS = ["Home", "Make", "Model", "Vehicle"]


def page_html(title: str, crumbs: list[str], body: str) -> str:
    links = "".join(f'<a class="breadcrumb-part" href="#">{c}</a>' for c in [*SITE_CRUMBS, *crumbs])
    return (
        f'<html><body><div class="header">{links}</div>'
        f'<div class="main"><h1>{title}</h1>{body}</div></body></html>'
    )


@pytest.fixture
def manual_dir(tmp_path: Path) -> Path:
    root = tmp_path / VEHICLE
    pages = root / "pages"
    pages.mkdir(parents=True)
    (root / "index.html").write_text("<html></html>", encoding="utf-8")
    Image.new("RGB", (40, 20), "red").save(pages / "diagram.png")

    content = "<p>Remove the four bolts and lift the assembly clear of the bracket.</p>"
    pages_spec = {
        # 1: navigation tree page, skipped
        1: page_html("Index", [], "<p>split tree</p>" + "<ul><li>a</li></ul>"),
        2: page_html(
            "Brake Pad Replacement",
            ["Repair and Diagnosis", "Brakes", "Pads"],
            content
            + '<img src="diagram.png"><table><tr><td>Torque</td><td>30 Nm</td></tr></table>',
        ),
        3: page_html(
            "Caliper Removal",
            ["Repair and Diagnosis", "Brakes", "Caliper"],
            "<h2>Steps</h2><ol><li>Loosen.</li><li>Remove.</li></ol>" + content,
        ),
        4: page_html("Oil Change", ["Repair and Diagnosis", "Engine"], content),
        5: page_html("Water Pump", ["Labor Times", "Other Variant", "Cooling"], content),
        # 6: menu-only page, skipped
        6: page_html("Menu", ["Repair and Diagnosis", "Engine"], "<ul><li>x</li></ul>"),
    }
    for number, text in pages_spec.items():
        (pages / f"{number}.html").write_text(text, encoding="utf-8")
    (pages / "notes.html").write_text("<html></html>", encoding="utf-8")
    return root


@pytest.fixture
def manual_zip(manual_dir: Path, tmp_path: Path) -> Path:
    archive = tmp_path / "manual.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        for path in manual_dir.rglob("*"):
            zf.write(path, arcname=path.relative_to(manual_dir.parent))
    return archive
