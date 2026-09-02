from __future__ import annotations

from collections.abc import Iterable
from os.path import join

IMAGE_SUFFIXES = {
    "image/jpeg": ".jpeg",
    "image/png": ".png",
    "image/webp": ".webp",
}


def image_destination(
    folder: str | Iterable[str],
    stage: str,
    identifier: str,
    content_type: str,
) -> tuple[str, str]:
    try:
        suffix = IMAGE_SUFFIXES[content_type]
    except KeyError as exc:
        raise ValueError(
            f"unsupported image content type: {content_type!r}"
        ) from exc
    parts = [folder] if isinstance(folder, str) else list(folder)
    return join(*parts, stage, f"{identifier}{suffix}"), content_type
