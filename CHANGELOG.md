# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project uses
[Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added

- `lemon2pdf` package and CLI, converted from the original `lemon_manual_builder.py` script:
  section PDFs with linked contents pages, a combined manual with a master contents page and
  nested outline, a ZIP of section PDFs, and `manifest.json`.
- Typed dataclass models, a `Lemon2PdfError` exception hierarchy, and logging with `-v`/`-q`.
- CI (ruff, ty, pytest, build) and a trusted-publishing release workflow.
