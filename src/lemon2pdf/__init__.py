"""Convert LEMON offline service-manual exports into navigable PDFs."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("lemon2pdf")
except PackageNotFoundError:  # pragma: no cover - running from an uninstalled tree
    __version__ = "0.0.0"

__all__ = ["__version__"]
