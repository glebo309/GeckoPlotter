"""Stage 1: extension-based file type detection.

Returns a normalized extension string (e.g. "csv", "txt", "cdf").
Does NOT attempt content inspection -- that is Stage 2's job.
"""

_KNOWN_EXTENSIONS = {
    "csv", "tsv", "txt", "asc", "log",
    "json", "xml",
    "cdf", "cdfx", "lcd",
    "xlsx", "xls",
    "png", "jpg", "jpeg", "svg",
}


def detect_by_extension(filename: str) -> str:
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ext in _KNOWN_EXTENSIONS:
        return ext
    return "unknown"
