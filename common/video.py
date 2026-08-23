"""Pure video-format and resolution helpers shared by local and cloud inspection."""


VIDEO_EXTS = {
    ".mp4", ".mov", ".m4v", ".mkv", ".avi", ".wmv", ".flv", ".webm",
    ".mpg", ".mpeg", ".mts", ".m2ts", ".ts", ".3gp",
}


def get_resolution(width: int, height: int) -> str:
    """Map pixel dimensions to the project's resolution category."""
    resolution_ranges = [
        ((320, 240), "vhs"),
        ((720, 480), "sd"),
        ((1280, 720), "hd"),
        ((1920, 1080), "fhd"),
        ((3840, 2160), "4k"),
        ((7680, 4320), "8k"),
    ]
    if min(width, height) == 0:
        return "xx"
    for (horizontal, vertical), resolution in reversed(resolution_ranges):
        if max(width, height) >= horizontal or min(width, height) >= vertical:
            return resolution
    return "vhs"
