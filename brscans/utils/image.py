from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from io import BytesIO
from types import SimpleNamespace

import requests
from django.core.files.base import ContentFile
from PIL import Image

# 12 é o mesmo teto do reparo por página (REPAIR_PAGE_WORKERS); mais que isso
# só aumenta o pico de RAM da Lambda para cada imagem em voo (~1,2 MB a 1,3 MB).
# O passe de medição (`merge_page_groups`) usa o mesmo teto.
DOWNLOAD_WORKERS = 12
# Sem timeout, uma fonte pendurada segurava a invocação até os 900 s do teto.
DOWNLOAD_TIMEOUT = (10, 60)


def normalize_url(url: str) -> str:
    """Remove barras extras ou corrige URLs malformadas."""
    if url.startswith("https:///"):
        url = url.replace("https:///", "https://", 1)
    elif url.startswith("http:///"):
        url = url.replace("http:///", "http://", 1)
    return url


def get_referer_from_url(url: str) -> str:
    """Extrai o referer a partir do domínio da URL."""
    from urllib.parse import urlparse

    parsed = urlparse(url)
    # Para CDNs do MangaBuddy, usar mangabuddy.com como referer
    if "mbcdn" in parsed.netloc or "mangabuddy" in parsed.netloc:
        return "https://mangabuddy.com/"
    if "2xstorage" in parsed.netloc:  # CDN do zazamanga
        return "https://www.zazamanga.com/"
    if "cmzcdn" in parsed.netloc:  # CDN do comizy.io devolve 403 sem referer
        return "https://comizy.io/"
    if "mgread" in parsed.netloc or "mgread.io" in parsed.netloc:
        return "https://mangayy.org/"
    if "madaradex" in parsed.netloc or "madaradex.org" in parsed.netloc:
        return "https://madaradex.org/"
    # CDN dos clones do Madara (manga18fx/manhwa18/mangadna), da mangatop
    # (manhuatop) e do zazamanga (zinmanga1): o referer é o site, não o CDN.
    for cdn, site in (
        ("manga18fx.com", "https://manga18fx.com/"),
        ("manhwa18.cc", "https://manhwa18.cc/"),
        ("mangadna.com", "https://mangadna.com/"),
        ("manhuatop.org", "https://mangatop.org/"),
        ("zinmanga", "https://www.zazamanga.com/"),
    ):
        if cdn in parsed.netloc:
            return site
    return f"{parsed.scheme}://{parsed.netloc}/"


_madaradex_cookies = None


def get_madaradex_cookies():
    global _madaradex_cookies
    if _madaradex_cookies is not None:
        return _madaradex_cookies

    try:
        import secrets
        fp_value = secrets.token_hex(16)
        session = requests.Session()
        session.cookies.set("mdx_fp", fp_value, domain=".madaradex.org", path="/")

        headers_post = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Referer": "https://madaradex.org/",
            "Origin": "https://madaradex.org",
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
        }

        r_post = session.post(
            "https://madaradex.org/wp-admin/admin-ajax.php",
            data={"action": "mdx_auth_refresh"},
            headers=headers_post,
            timeout=10,
        )
        if r_post.status_code == 200:
            cookies = session.cookies.get_dict()
            if "mdx_auth" in cookies:
                _madaradex_cookies = "; ".join(
                    [f"{k}={v}" for k, v in cookies.items()]
                )
                return _madaradex_cookies
    except Exception as e:
        print(f"Erro ao buscar cookies do madaradex: {e}")

    return None


def _headers(url, headers=None):
    default_headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Referer": get_referer_from_url(url),
        "Accept": "image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8",
    }
    if "madaradex.org" in url:
        cookies_str = get_madaradex_cookies()
        if cookies_str:
            default_headers["Cookie"] = cookies_str
    if headers:
        default_headers.update(headers)
    return default_headers


def download_image(url, headers=None):
    try:
        normalized_url = normalize_url(url)
        response = requests.get(
            normalized_url,
            headers=_headers(normalized_url, headers),
            timeout=DOWNLOAD_TIMEOUT,
        )
        if response.status_code != 200:
            print(f"Erro ao baixar imagem: {normalized_url}")
        response.raise_for_status()
        return Image.open(BytesIO(response.content))
    except Exception as e:
        print(f"Erro ao baixar imagem: {url}")
        print(e)
        return None


_HEAD_MAGIC = 65536  # cabeçalho de JPEG/PNG cabe folgado em 64 KB


def _webp_size(head):
    """Dimensões do cabeçalho RIFF; o Pillow só decodifica WebP inteiro."""
    if head[:4] != b"RIFF" or head[8:12] != b"WEBP" or len(head) < 30:
        return None
    chunk = head[12:16]
    if chunk == b"VP8X":
        return (
            int.from_bytes(head[24:27], "little") + 1,
            int.from_bytes(head[27:30], "little") + 1,
        )
    if chunk == b"VP8L":
        bits = int.from_bytes(head[21:25], "little")
        return (bits & 0x3FFF) + 1, ((bits >> 14) & 0x3FFF) + 1
    if chunk == b"VP8 ":
        return (
            int.from_bytes(head[26:28], "little") & 0x3FFF,
            int.from_bytes(head[28:30], "little") & 0x3FFF,
        )
    return None


def download_head(url):
    """Abre a imagem lendo só o começo do corpo, para pegar `size`.

    A página inteira não é baixada duas vezes: o merge logo depois busca o
    mesmo arquivo. Se a codificação não fechar com o pedaço, o chamador
    recai em `download_image` (caro, mas correto).
    """
    try:
        normalized_url = normalize_url(url)
        with requests.get(
            normalized_url,
            headers=_headers(normalized_url),
            stream=True,
            timeout=DOWNLOAD_TIMEOUT,
        ) as response:
            response.raise_for_status()
            data = BytesIO()
            # 64 KB serve PNG/JPEG e WebP (lido do cabeçalho); AVIF só abre com
            # o arquivo inteiro e recai em `download_image` (_url_and_size).
            for chunk in response.iter_content(8192):
                data.write(chunk)
                if data.tell() >= _HEAD_MAGIC:
                    break
            size = _webp_size(data.getvalue()[:30])
            if size:
                return SimpleNamespace(size=size, close=lambda: None)
            data.seek(0)
            return Image.open(data)
    except Exception as e:
        print(f"Erro ao baixar imagem: {url}")
        print(e)
        return None


# Função para fazer merge vertical de imagens
def merge_images(images):
    widths, heights = zip(*(i.size for i in images))
    total_height = sum(heights)
    max_width = max(widths)

    new_image = Image.new("RGB", (max_width, total_height))
    y_offset = 0
    for im in images:
        new_image.paste(im, (0, y_offset))
        y_offset += im.height

    return new_image


def download_images(urls):
    """Baixa todas ou nenhuma: capítulo com falha fica com o que já tinha."""
    with ThreadPoolExecutor(max_workers=DOWNLOAD_WORKERS) as executor:
        images = list(executor.map(download_image, urls))
    if any(img is None for img in images):
        raise RuntimeError(f"Algumas imagens falharam ao baixar: {urls}")
    return images


def download_pieces(group):
    """Baixa um grupo de `merge_page_groups`, recortando imagem partida.

    Sem o recorte a imagem inteira (> 16383 px) ia para o WebP e o encode
    falhava ("encoding error 5"). URL solta (painel) é a imagem inteira.
    """
    pieces = [(p, 0, None) if isinstance(p, str) else p for p in group]
    images = download_images([url for url, _, _ in pieces])
    return [
        image.crop((0, top, image.width, top + height))
        if height and image.height > height
        else image
        for image, (_, top, height) in zip(images, pieces)
    ]


def merge_page_groups(urls):
    """Pedaços (url, top, height) agrupados, sem as imagens na memória.

    Mesma divisão de `batch_urls`: largura diferente ou grupo passando de
    8191 px fecham o grupo; imagem acima de 16383 px é partida antes. Cada
    imagem é fechada assim que se lê o tamanho.

    Lê só o cabeçalho (`download_head`): `download_image` baixa a página
    inteira, e o merge logo depois baixaria de novo as mesmas URLs.
    """

    with ThreadPoolExecutor(max_workers=DOWNLOAD_WORKERS) as executor:
        # map devolve na ordem das URLs: a divisão não muda com o download
        sizes = list(executor.map(_url_and_size, urls))

    pieces = []
    for url, (width, height) in sizes:
        # imagem acima de 16383 px é partida antes de agrupar
        for top in range(0, height, 16383):
            pieces.append(IMG(width, min(top + 16383, height) - top, url, top))
    # A divisão é do `batch_urls`; o grupo vazio que ele deixa na troca de
    # largura não vira página. O pedaço leva o intervalo (top, height): a
    # imagem partida repete a URL e quem baixa precisa recortar.
    return [
        [(piece.url, piece.top, piece.height) for piece in group]
        for group in batch_urls(pieces)
        if group
    ]


class IMG:
    """O que `batch_urls` lê de uma imagem, com a URL no lugar dos pixels."""

    __slots__ = ("width", "height", "url", "top")

    def __init__(self, width, height, url, top=0):
        self.width, self.height, self.url, self.top = width, height, url, top


def _url_and_size(url):
    # Cabeçalho primeiro; se a codificação precisar do arquivo todo, baixa.
    image = download_head(url) or download_image(url)
    if image is None:
        raise RuntimeError(f"Falha ao ler o tamanho de {url}")
    try:
        return url, image.size
    finally:
        image.close()


def images_height(images):
    return [{"height": image.height, "width": image.width} for image in images]


# Função principal para processar URLs e retornar lista de ContentFile
def batch_urls(images):
    time = datetime.now()
    sizes = images_height(images)

    max_height = 8191
    grouped_images = []
    current_group = []
    current_height = 0
    current_width = None

    for image, size in zip(images, sizes):
        if current_width is None:
            current_width = size.get("width")

        if current_width == size.get("width"):
            if current_height + size.get("height") <= max_height:
                current_group.append(image)
                current_height += size.get("height")
            else:
                grouped_images.append(current_group)
                current_group = [image]
                current_height = size.get("height")
                current_width = size.get("width")
        else:
            grouped_images.append(current_group)
            current_group = [image]
            current_height = size.get("height")
            current_width = size.get("width")

    if current_group:
        grouped_images.append(current_group)

    print(
        f"Divide {len(images)} imagens em {len(grouped_images)} grupos em "
        f"{(datetime.now() - time).total_seconds():.2f} segundos"
    )
    return grouped_images


def process_merge_images(images):
    merged_image = merge_images(images)  # já é RGB e guarda no máximo 8191 px
    buffer = BytesIO()
    merged_image.save(buffer, format="WEBP")  # convert() copiaria o quadro todo
    return ContentFile(buffer.getvalue(), name="merged_image.webp")


