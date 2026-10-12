# lemon2pdf

Convert [LEMON Manuals](https://lemon-manuals.la/) offline vehicle exports (a ZIP of HTML pages)
into navigable PDFs:

- one PDF per manual section, each with a clickable contents page and bookmarks,
- a combined manual with a master contents page and a nested outline,
- a ZIP of the section PDFs, and
- a `manifest.json` describing what was built.

Conversion is reflowed from the HTML, not an exact browser print.

## Install / run

```bash
# run without installing (once published to PyPI)
uvx lemon2pdf 'LEMON 2002 Buick LeSabre V6-3.8L VIN K.zip' --out buick_pdfs

# from a checkout
uvx --from . lemon2pdf --help

# or install as a tool
uv tool install lemon2pdf
```

## Usage

```text
lemon2pdf SOURCE [-o OUT] [--max-documents N] [--batch-size N]
                 [--section TERM ...] [--no-complete] [--no-zip]
                 [--max-uncompressed-gib GIB] [--temp-dir DIR] [-v | -q]
```

| Option | Meaning |
| --- | --- |
| `SOURCE` | LEMON ZIP export or an already-extracted vehicle directory |
| `-o, --out` | Output directory (default `lemon_pdfs`) |
| `--max-documents N` | Quick test run: stop after N content documents |
| `--batch-size N` | Documents per temporary PDF batch (default 120); lower uses less memory |
| `--section TERM` | Only build sections whose name contains TERM; repeatable |
| `--no-complete` | Skip `complete_navigable_manual.pdf` |
| `--no-zip` | Skip `sectioned_manuals.zip` |
| `--max-uncompressed-gib GIB` | Refuse ZIPs whose members total more than GIB GiB (default 50) |
| `--temp-dir DIR` | Where temporary files go (default: system temp); point at a large disk if it fills |
| `-v` / `-q` | Debug output / warnings only |

Output layout:

```text
OUT/
├── sections/01_<section>.pdf ...
├── complete_navigable_manual.pdf
├── sectioned_manuals.zip
└── manifest.json
```

`manifest.json` also has an `images` object: `placed` images, and `skipped` counts by reason
(`missing`, `remote`, `outside_root`, `unreadable`), summed over every section.

### As a library

```python
from pathlib import Path
from lemon2pdf.models import BuildOptions
from lemon2pdf.pipeline import build

manifest = build(BuildOptions(source=Path("manual.zip"), out=Path("pdfs"), max_documents=30))
print(manifest.to_json())
```

All errors raised deliberately derive from `lemon2pdf.errors.Lemon2PdfError`.

## Development

```bash
uv sync
uv run ruff check .
uv run ruff format --check .
uv run ty check
uv run pytest
```

Package layout (`src/lemon2pdf/`):

| Module | Responsibility |
| --- | --- |
| `cli.py` | argument parsing, logging setup, exit codes |
| `pipeline.py` | end-to-end build orchestration |
| `archive.py` | safe ZIP extraction, manual root detection, output ZIP |
| `discovery.py` | page indexing and breadcrumb-based sectioning |
| `render.py` | HTML → ReportLab flowables and batch PDFs |
| `assemble.py` | section PDFs, linked contents pages, combined manual (PyMuPDF) |
| `models.py` | dataclasses: `Document`, `Section`, `SectionResult`, `ImageStats`, `Manifest`, `BuildOptions` |
| `errors.py` | exception hierarchy |

## License

AGPL-3.0-or-later, matching [PyMuPDF](https://pymupdf.readthedocs.io/), which this project
depends on. See [LICENSE](LICENSE).
