"""Make printable photo mosaic posters from a folder of photos."""
__version__ = "0.1.0"

from .render import PosterOptions, make_poster  # noqa: E402

__all__ = ["PosterOptions", "make_poster", "__version__"]
