from pathlib import Path

import pytest

from lemon2pdf.discovery import discover, filter_sections, get_section
from lemon2pdf.models import Document, Section


@pytest.mark.parametrize(
    ("parts", "expected"),
    [
        ([], "General Information"),
        (["Repair and Diagnosis"], "General Information"),
        (["Repair and Diagnosis", "Brakes", "Pads"], "Brakes"),
        (["Labor Times", "Engine"], "Parts and Labor - Engine"),
        (["Parts and Labor", "Other Variant", "Cooling"], "Parts and Labor - Cooling"),
        (["Labor Times"], "Parts and Labor"),
        (["Specifications", "Fluids"], "Specifications"),
    ],
)
def test_get_section(parts, expected):
    assert get_section(parts) == expected


def test_discover_groups_content_pages(manual_dir: Path):
    sections = discover(manual_dir)
    assert [s.name for s in sections] == ["Brakes", "Engine", "Parts and Labor - Cooling"]
    brakes = sections[0]
    assert [d.id for d in brakes.documents] == [2, 3]
    assert brakes.documents[0] == Document(
        id=2, title="Brake Pad Replacement", path="Repair and Diagnosis > Brakes > Pads"
    )
    # navigation (1) and menu-only (6) pages are skipped
    all_ids = {d.id for s in sections for d in s.documents}
    assert all_ids == {2, 3, 4, 5}


def test_discover_limit(manual_dir: Path):
    sections = discover(manual_dir, limit=2)
    assert sum(len(s.documents) for s in sections) == 2


def test_filter_sections_case_insensitive():
    sections = [Section("Brakes", ()), Section("Engine Cooling", ()), Section("Body", ())]
    assert [s.name for s in filter_sections(sections, ["brake", "COOL"])] == [
        "Brakes",
        "Engine Cooling",
    ]
    assert filter_sections(sections, []) == sections
