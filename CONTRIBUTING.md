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

Changes to conversion output should also be tried on real exports. Set `LEMON2PDF_SAMPLE_ZIP` to one or more export ZIP paths:

```bash
LEMON2PDF_SAMPLE_ZIP='/path/to/LEMON A.zip' uv run pytest tests/test_real_sample.py
```

To check several ZIPs in one run, separate the paths with `os.pathsep`: `:` on Linux and macOS, `;` on Windows.

```bash
# Linux / macOS
LEMON2PDF_SAMPLE_ZIP='/path/to/LEMON A.zip:/path/to/LEMON B.zip' uv run pytest tests/test_real_sample.py
```

```powershell
# Windows
$env:LEMON2PDF_SAMPLE_ZIP = 'C:\exports\LEMON A.zip;C:\exports\LEMON B.zip'
uv run pytest tests/test_real_sample.py
```

Each ZIP is its own test case, named after the file stem (for example `test_...[LEMON A]`), so a failure points at the export that caused it. Each case builds 60 documents from its ZIP. Without the variable set, the tests are skipped.

Do not commit LEMON exports or generated PDFs.

## Releases

1. Bump `version` in `pyproject.toml` (`uv version --bump minor`) and update `CHANGELOG.md`.
2. Merge `dev` into `main`.
3. Tag `main` with `v<version>` and push the tag; the release workflow publishes to PyPI.
