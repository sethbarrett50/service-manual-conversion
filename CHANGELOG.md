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
- SVG images are rendered as vector drawings via svglib (new dependency).
- `manifest.json` records an `images` summary: placed count and skipped counts by reason
  (missing, remote, outside root, unreadable); one summary line is logged at the end of each
  run.
- `--temp-dir DIR` for the build's temporary files, and `--max-uncompressed-gib` (default 50)
  to cap the total uncompressed size of an input ZIP.
- Opt-in real-export test suite: `LEMON2PDF_SAMPLE_ZIP` accepts several paths
  (os.pathsep-separated).

### Fixed

- Contents links for documents whose `[source N]` heading wraps across lines now point to the
  right page (inherited from the original script).
- Corrupt or truncated ZIPs, symlink members, oversized archives, a full temp disk and invalid
  source/output paths now end with one `error: ...` line and exit 1 instead of a traceback.
- Pages without a `.main` element are skipped with a warning instead of silently.
- Unreadable images log one warning line instead of a full traceback.
