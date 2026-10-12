"""Exception hierarchy for lemon2pdf.

Every error raised deliberately by this package derives from :class:`Lemon2PdfError`, so callers
(and the CLI) can catch one type and report a clean message instead of a traceback.
"""


class Lemon2PdfError(Exception):
    """Base class for all lemon2pdf errors."""


class ConfigurationError(Lemon2PdfError, ValueError):
    """Build options are invalid (for example a non-positive batch size)."""


class UnsafeArchiveError(Lemon2PdfError):
    """A ZIP member would extract outside the destination directory."""

    def __init__(self, member: str) -> None:
        super().__init__(f"Unsafe ZIP path: {member}")
        self.member = member


class CorruptArchiveError(Lemon2PdfError):
    """A ZIP is damaged, truncated or otherwise cannot be read."""

    def __init__(self, archive: object, reason: object) -> None:
        super().__init__(f"Corrupt ZIP {archive}: {reason}")
        self.archive = archive


class ArchiveTooLargeError(Lemon2PdfError):
    """A ZIP would extract to more than the allowed total size."""

    def __init__(self, total: int, limit: int) -> None:
        super().__init__(f"ZIP would extract to {total} bytes, above the {limit} byte limit")
        self.total = total
        self.limit = limit


class ManualNotFoundError(Lemon2PdfError):
    """The source does not contain a recognizable LEMON manual."""


class ArchiveValidationError(Lemon2PdfError):
    """A written ZIP archive failed its integrity check."""

    def __init__(self, member: str) -> None:
        super().__init__(f"ZIP failed validation at {member}")
        self.member = member


class ConversionError(Lemon2PdfError):
    """Rendering or assembling a PDF failed."""
