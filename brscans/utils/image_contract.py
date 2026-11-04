from __future__ import annotations

import re
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


# ── painel: caminho/URL de imagem editados à mão ──────────────────────────
_IMAGE_SUFFIX = re.compile(r"\.(jpe?g|png|webp|avif)$", re.IGNORECASE)


def media_domain(media_url: str) -> str:
    """'https://cdn/media/' ou '/media/' -> 'https://cdn' (sem barra final)."""
    domain = (media_url or "").rstrip("/").removesuffix("/media")
    if domain and "://" not in domain:
        domain = f"https://{domain}"
    return domain


def normalize_image_path(value: str, media_url: str) -> str:
    """Valida um path do storage ('chapters/1/x.webp') ou URL do CDN e devolve
    o path. URL fora do domínio de mídia é recusada."""
    value = (value or "").strip()
    if not value:
        raise ValueError("Informe o caminho ou a URL da imagem.")

    domain = media_domain(media_url)
    if value.startswith(("http://", "https://")):
        if not domain:
            raise ValueError("Sem domínio de mídia configurado.")
        if not value.startswith(f"{domain}/"):
            raise ValueError(f"URL fora do storage ({domain}).")
        value = value[len(domain) + 1 :]

    value = value.split("?", 1)[0].lstrip("/").removeprefix("media/")
    if not value or ".." in value.split("/"):
        raise ValueError("Caminho inválido.")
    if not _IMAGE_SUFFIX.search(value):
        raise ValueError("Só imagens .jpg/.jpeg/.png/.webp/.avif.")
    return value
