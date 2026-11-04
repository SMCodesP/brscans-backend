"""Avisa no Discord os capítulos que chegaram a 100% traduzidos."""

import json
import mimetypes
import os
import re
from itertools import groupby

import httpx

from brscans.manhwa.models import Chapter
from brscans.manhwa.work import DONE

API = "https://discord.com/api/v10"
COLOR = 0x7C3AED
GROUP_FROM = 3  # a partir daqui vira uma mensagem só por manga
MAX_COVER_BYTES = 8 * 1024 * 1024


def chapter_number(chapter):
    match = re.search(r"\d+(?:\.\d+)?", chapter.title or "")
    return match.group() if match else chapter.title


def _sort_key(chapter):
    number = chapter_number(chapter)
    try:
        return (0, float(number))
    except (TypeError, ValueError):
        return (1, 0.0)


def build_embed(manhwa, chapters, cover_name=None):
    site = os.environ.get("FRONTEND_URL", "").rstrip("/")
    numbers = [chapter_number(chapter) for chapter in chapters]
    if len(chapters) == 1:
        title = f"📖 Novo capítulo de {manhwa.title}"
        description = (
            f"O **capítulo {numbers[0]}** acabou de sair, traduzido e "
            "pronto para você ler!"
        )
        path = f"/manga/{manhwa.pk}/chapter/{chapters[0].pk}"
    else:
        title = f"📚 Novos capítulos de {manhwa.title}"
        listed = ", ".join(str(number) for number in numbers)
        description = (
            f"**{len(chapters)} capítulos novos** acabaram de sair, "
            f"traduzidos e prontos para você ler!\n\n**Capítulos:** {listed}"
        )
        path = f"/manga/{manhwa.pk}"
    embed = {
        "title": title[:256],
        "description": description[:4096],
        "color": COLOR,
        "footer": {"text": "BRScans • Boa leitura!"},
    }
    if site:
        embed["url"] = f"{site}{path}"
    if cover_name:
        embed["image"] = {"url": f"attachment://{cover_name}"}
    return embed


def _download_cover(manhwa):
    """Sem capa a mensagem ainda sai: capa é enfeite, o aviso não."""
    thumbnail = manhwa.thumbnail
    if not thumbnail or not thumbnail.original:
        return None
    try:
        response = httpx.get(
            thumbnail.original.url, timeout=10, follow_redirects=True
        )
        response.raise_for_status()
    except httpx.HTTPError as exc:
        print(f"[discord] capa de {manhwa.pk}: {exc!r}")
        return None
    if len(response.content) > MAX_COVER_BYTES:
        return None
    extension = os.path.splitext(thumbnail.original.name)[1].lower() or ".jpg"
    return f"capa{extension}", response.content


def _send(token, channel_id, manhwa, chapters):
    cover = _download_cover(manhwa)
    embed = build_embed(manhwa, chapters, cover[0] if cover else None)
    payload = {"embeds": [embed], "allowed_mentions": {"parse": []}}
    files = None
    if cover:
        name, content = cover
        content_type = mimetypes.guess_type(name)[0] or "image/jpeg"
        files = {"files[0]": (name, content, content_type)}
    response = httpx.post(
        f"{API}/channels/{channel_id}/messages",
        headers={"Authorization": f"Bot {token}"},
        data={"payload_json": json.dumps(payload)},
        files=files,
        timeout=15,
    )
    response.raise_for_status()


def notify_finished_chapters():
    token = os.environ.get("DISCORD_BOT_TOKEN")
    channel_id = os.environ.get("DISCORD_CHANNEL_ID")
    if not token or not channel_id:
        print("[discord] desligado: DISCORD_BOT_TOKEN/CHANNEL_ID ausente")
        return {"disabled": True}

    pending = Chapter.objects.filter(
        work_status=DONE, discord_notified=False, manhwa__isnull=False
    )
    # NSFW nunca é avisado; marcar evita reavaliar a cada execução.
    skipped = pending.filter(manhwa__is_nsfw=True).update(discord_notified=True)
    chapters = (
        pending.filter(manhwa__is_nsfw=False)
        .select_related("manhwa", "manhwa__thumbnail")
        .order_by("manhwa_id")
    )

    sent = 0
    for _, group in groupby(chapters, key=lambda chapter: chapter.manhwa_id):
        group = sorted(group, key=_sort_key)
        manhwa = group[0].manhwa
        batches = (
            [group] if len(group) >= GROUP_FROM else [[item] for item in group]
        )
        for batch in batches:
            ids = [chapter.pk for chapter in batch]
            # Marca antes de enviar: duas Lambdas não avisam o mesmo capítulo.
            Chapter.objects.filter(pk__in=ids).update(discord_notified=True)
            try:
                _send(token, channel_id, manhwa, batch)
            except httpx.HTTPError as exc:
                # Rate limit ou queda: desfaz e tenta na próxima execução.
                Chapter.objects.filter(pk__in=ids).update(
                    discord_notified=False
                )
                print(f"[discord] falha em {manhwa.pk}: {exc!r}")
                return {"sent": sent, "skipped_nsfw": skipped, "error": True}
            sent += 1
    return {"sent": sent, "skipped_nsfw": skipped}
