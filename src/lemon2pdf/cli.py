"""Command-line interface: ``lemon2pdf SOURCE [--out DIR] ...``."""

from __future__ import annotations

import argparse
import logging
import sys
from collections.abc import Sequence
from pathlib import Path

from lemon2pdf import __version__
from lemon2pdf.errors import Lemon2PdfError
from lemon2pdf.models import BuildOptions
from lemon2pdf.pipeline import build

logger = logging.getLogger("lemon2pdf")

DESCRIPTION = """\
Convert a LEMON offline vehicle ZIP into navigable, sectioned and combined PDFs.

Outputs: sections/*.pdf, complete_navigable_manual.pdf, sectioned_manuals.zip,
manifest.json. Conversion is reflowed, not an exact browser print.
"""

EPILOG = """\
examples:
  lemon2pdf 'LEMON 2002 Buick LeSabre V6-3.8L VIN K.zip' --out buick_pdfs
  lemon2pdf 'LEMON ...zip' --out test_pdfs --max-documents 30
  lemon2pdf extracted_manual/ --section brakes --section engine --no-zip
"""


def _positive_int(value: str) -> int:
    number = int(value)
    if number < 1:
        raise argparse.ArgumentTypeError("must be a positive integer")
    return number


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="lemon2pdf",
        description=DESCRIPTION,
        epilog=EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("source", type=Path, help="LEMON ZIP or extracted vehicle directory")
    parser.add_argument(
        "-o", "--out", type=Path, default=Path("lemon_pdfs"), help="output directory"
    )
    parser.add_argument(
        "--max-documents",
        type=_positive_int,
        help="small test run; limit total procedure documents",
    )
    parser.add_argument(
        "--batch-size",
        type=_positive_int,
        default=120,
        help="documents per temporary PDF batch (default: %(default)s)",
    )
    parser.add_argument(
        "--section",
        action="append",
        default=[],
        metavar="TERM",
        help="only build sections whose name contains TERM; can repeat",
    )
    parser.add_argument("--no-complete", action="store_true", help="skip the combined PDF")
    parser.add_argument("--no-zip", action="store_true", help="skip the sectioned ZIP")
    verbosity = parser.add_mutually_exclusive_group()
    verbosity.add_argument("-v", "--verbose", action="store_true", help="show debug output")
    verbosity.add_argument("-q", "--quiet", action="store_true", help="only show warnings")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    return parser


def configure_logging(*, verbose: bool = False, quiet: bool = False) -> None:
    level = logging.DEBUG if verbose else logging.WARNING if quiet else logging.INFO
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(logging.Formatter("%(message)s"))
    logger.handlers[:] = [handler]
    logger.setLevel(level)
    logger.propagate = False


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    configure_logging(verbose=args.verbose, quiet=args.quiet)
    try:
        options = BuildOptions(
            source=args.source,
            out=args.out,
            max_documents=args.max_documents,
            batch_size=args.batch_size,
            section_filters=tuple(args.section),
            complete=not args.no_complete,
            zip_sections=not args.no_zip,
        )
        build(options)
    except Lemon2PdfError as exc:
        logger.error("error: %s", exc)
        return 1
    except KeyboardInterrupt:
        logger.error("interrupted")
        return 130
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
