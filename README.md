# lemon2pdf

Convert [LEMON Manuals](https://lemon-manuals.la/) offline vehicle exports (a ZIP of HTML pages)
into navigable PDFs:

- one PDF per manual section, each with a clickable contents page and bookmarks,
- a combined manual with a master contents page and a nested outline,
- a ZIP of the section PDFs, and
- a `manifest.json` describing what was built.

Conversion is reflowed from the HTML, not an exact browser print.

> **Status:** early development. The original single-file script lives in
> `lemon_manual_builder.py` while it is being turned into the `lemon2pdf` package.

## Usage (script)

```bash
uv run lemon_manual_builder.py 'LEMON 2002 Buick LeSabre V6-3.8L VIN K.zip' --out buick_pdfs
uv run lemon_manual_builder.py 'LEMON ...zip' --out test_pdfs --max-documents 30
```

## Development

```bash
uv sync
uv run ruff check .
uv run ruff format --check .
uv run ty check
uv run pytest
```

## License

AGPL-3.0-or-later, matching [PyMuPDF](https://pymupdf.readthedocs.io/), which this project
depends on. See [LICENSE](LICENSE).
