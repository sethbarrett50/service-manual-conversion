# Contributing

Thanks for helping improve lemon2pdf.

## Setup

```bash
git clone https://github.com/sethbarrett50/service-manual-conversion.git
cd service-manual-conversion
uv sync
```

## Branches

- `main`: released code.
- `dev`: integration branch; open pull requests against `dev`.
- Feature branches: `feat/<topic>`, `fix/<topic>`, `ci/<topic>`, `chore/<topic>`, branched from `dev`.

## Checks

CI runs these on every pull request; run them locally first:

```bash
uv run ruff check .
uv run ruff format --check .
uv run ty check
uv run pytest
```

Changes to conversion output should also be tried on a real export:

```bash
LEMON2PDF_SAMPLE_ZIP='/path/to/LEMON ... .zip' uv run pytest tests/test_real_sample.py
```

Do not commit LEMON exports or generated PDFs.

## Releases

1. Bump `version` in `pyproject.toml` (`uv version --bump minor`) and update `CHANGELOG.md`.
2. Merge `dev` into `main`.
3. Tag `main` with `v<version>` and push the tag; the release workflow publishes to PyPI.
