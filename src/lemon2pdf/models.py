"""Immutable data records passed between the discovery, rendering and assembly stages."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from lemon2pdf.errors import ConfigurationError


@dataclass(frozen=True, slots=True)
class Document:
    """One content page of the manual (``pages/<id>.html``)."""

    id: int
    title: str
    path: str
    """Breadcrumb trail, joined with ``" > "``."""


@dataclass(frozen=True, slots=True)
class Section:
    """A named group of documents that becomes one section PDF."""

    name: str
    documents: tuple[Document, ...]


@dataclass(frozen=True, slots=True)
class SectionResult:
    """What was written for one section."""

    section: str
    file: Path
    documents: int
    pages: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "section": self.section,
            "file": self.file.name,
            "documents": self.documents,
            "pages": self.pages,
        }


@dataclass(frozen=True, slots=True)
class Manifest:
    """Summary of a build, written to ``manifest.json``."""

    vehicle: str
    sections: tuple[SectionResult, ...] = ()
    complete_pdf: Path | None = None
    sections_zip: Path | None = None

    def to_dict(self) -> dict[str, Any]:
        return {"vehicle": self.vehicle, "sections": [s.to_dict() for s in self.sections]}

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2)


@dataclass(frozen=True, slots=True)
class BuildOptions:
    """Inputs to :func:`lemon2pdf.pipeline.build`."""

    source: Path
    out: Path = Path("lemon_pdfs")
    max_documents: int | None = None
    batch_size: int = 120
    section_filters: tuple[str, ...] = field(default=())
    complete: bool = True
    zip_sections: bool = True

    def __post_init__(self) -> None:
        if self.batch_size < 1:
            raise ConfigurationError("batch size must be positive")
        if self.max_documents is not None and self.max_documents < 1:
            raise ConfigurationError("max documents must be positive")
