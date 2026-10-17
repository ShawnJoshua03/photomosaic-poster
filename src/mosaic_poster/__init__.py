"""Make printable photo mosaic posters from a folder of photos."""
__version__ = "0.2.1"

from .render import PosterOptions, PreflightError, RenderResult, make_poster, preflight  # noqa: E402

__all__ = ["PosterOptions", "PreflightError", "RenderResult", "make_poster", "preflight",
           "__version__"]
