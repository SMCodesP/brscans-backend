"""Fontes novas da migração, sem rede: fixtures capturados da Lambda dev.

Cada fixture é um recorte do HTML real devolvido de dentro da Lambda
(brscans-backend-dev, sa-east-1, 2026-11-02), com os seletores que o parser
usa: `.c-tabs-item__content` da busca, `li.wp-manga-chapter` da lista,
`img.wp-manga-chapter-img` do leitor.
"""

from __future__ import annotations

import unittest
from pathlib import Path
from unittest import mock

import django

django.setup()

from brscans.utils.image import get_referer_from_url  # noqa: E402
from brscans.wrapper.sources import (  # noqa: E402
    get_searchable_source,
    get_source_by_link,
    nsfw_sources,
    searchable_sources,
)
from brscans.wrapper.sources.Generic import Generic  # noqa: E402
from brscans.wrapper.sources.MadaraClone import MadaraClone  # noqa: E402
from brscans.wrapper.sources.ThreeHentai import ThreeHentai  # noqa: E402

FIXTURES = Path(__file__).parent / "fixtures" / "fontes"

MADARA_HOSTS = (
    "aquareader.org",
    "www.mangaread.org",
    "www.zazamanga.com",
    "mangatop.org",
    "manhwanex.com",
    "manhuanext.com",
)
CLONE_HOSTS = ("manga18fx.com", "manhwa18.cc", "mangadna.com")


def fixture(host: str, step: str) -> str:
    return (FIXTURES / f"{host}.{step}.html").read_text()


class FakeResponse:
    def __init__(self, text, url, status_code=200):
        self.text = text
        self.url = url
        self.status_code = status_code
        self.content = text.encode()

    def raise_for_status(self):
        return None


class FakeScraper:
    """CloudScraper falso: responde por URL, guarda a ordem das chamadas."""

    def __init__(self, pages):
        self.pages = pages
        self.calls = []

    def _response(self, url):
        self.calls.append(url)
        for suffix, html in self.pages.items():
            if url.endswith(suffix):
                return FakeResponse(html, url)
        return FakeResponse("", url, 404)

    def get(self, url, **kwargs):
        return self._response(url)

    def post(self, url, **kwargs):
        return self._response(url)


class MadaraSourcesTests(unittest.TestCase):
    def test_busca_devolve_card_com_url_e_capa(self) -> None:
        for host in MADARA_HOSTS:
            with self.subTest(host=host):
                source = Generic(f"https://{host}")
                self.assertIs(get_source_by_link(f"https://{host}/manga/x"), Generic)
                get = mock.Mock(
                    return_value=FakeResponse(
                        fixture(host, "search"), f"https://{host}/"
                    )
                )
                with mock.patch.object(source.client, "get", get):
                    results = source.search("obra")
                self.assertTrue(results, host)
                self.assertTrue(
                    all(r["url"].startswith(f"https://{host}/") for r in results)
                )
                self.assertTrue(all(r["title"] for r in results))
                # Sem `post_type=wp-manga` o Madara devolve o site inteiro.
                self.assertEqual(
                    get.call_args.kwargs["params"]["post_type"], "wp-manga"
                )

    def test_busca_aceita_fichas_em_series(self) -> None:
        # mangatop publica as fichas em `/series/`, não em `/manga/`.
        html = (
            '<div class="c-tabs-item__content"><div class="post-title"><h3>'
            '<a href="https://mangatop.org/series/lightning-degree/">Lightning Degree'
            "</a></h3></div></div>"
        )
        results = Generic.cards(html, "https://mangatop.org")
        self.assertEqual(
            [r["url"] for r in results],
            ["https://mangatop.org/series/lightning-degree/"],
        )

    def test_capitulos_saem_do_ajax_ou_da_ficha(self) -> None:
        for host in MADARA_HOSTS:
            with self.subTest(host=host):
                listing = fixture(host, "chapters")
                # aquareader lista no ajax; zazamanga só na ficha (ajax 404)
                scraper = FakeScraper(
                    {
                        f"https://{host}/manga/x/ajax/chapters/": listing,
                        f"https://{host}/manga/x/": listing,
                    }
                )
                with mock.patch.object(Generic, "scraper", scraper):
                    chapters = Generic.chapters(
                        mock.Mock(source=f"https://{host}/manga/x/")
                    )
                self.assertTrue(chapters, host)
                # id = último segmento da URL ("chapter-27"), igual ao slug
                # do banco: sem o prefixo, o cron criaria capítulo duplicado.
                self.assertEqual(
                    chapters[0]["id"],
                    chapters[0]["url"].rstrip("/").split("/")[-1],
                )
                self.assertTrue(chapters[0]["id"].startswith("chapter-"))
                self.assertTrue(chapters[0]["title"])

    def test_capitulos_caem_na_lista_inline_quando_ajax_nao_tem_a_lista(self) -> None:
        # zazamanga responde 404 no ajax; a lista está na página do mangá.
        listing = fixture("www.zazamanga.com", "chapters")
        scraper = FakeScraper({"https://www.zazamanga.com/manga/x/": listing})
        with mock.patch.object(Generic, "scraper", scraper):
            chapters = Generic.chapters(
                mock.Mock(source="https://www.zazamanga.com/manga/x/")
            )
        self.assertTrue(chapters)
        self.assertEqual(
            scraper.calls,
            [
                "https://www.zazamanga.com/manga/x/ajax/chapters/",
                "https://www.zazamanga.com/manga/x/",
            ],
        )

    def test_ajax_404_nao_confia_no_fallback_generico(self) -> None:
        # Sem lista estruturada, a página 404 devolve links de outra coisa com
        # ids novos — foi assim que o cron criou capítulo duplicado (02/11/2026).
        scraper = FakeScraper(
            {
                "https://x.com/manga/x/": '<li><a href="/x/chapter-1/">c</a></li>',
                "https://x.com/": "<html></html>",
            }
        )
        calls = []
        with mock.patch.object(Generic, "scraper", scraper):
            chapters = Generic.chapters(
                mock.Mock(source="https://x.com/manga/x/"),
                throttle=lambda: calls.append(1),
            )
        self.assertEqual(chapters, [])
        # a página é lida uma vez (sem lista, vazia) em vez de virar capítulo
        self.assertEqual(
            len([c for c in scraper.calls if c.endswith("/ajax/chapters/")]), 1
        )
        self.assertEqual(len(calls), 2)

    def test_ajax_fora_respeita_o_throttle_antes_da_pagina(self) -> None:
        listing = fixture("www.zazamanga.com", "chapters")
        scraper = FakeScraper({"https://www.zazamanga.com/manga/x/": listing})
        calls = []
        with mock.patch.object(Generic, "scraper", scraper):
            Generic.chapters(
                mock.Mock(source="https://www.zazamanga.com/manga/x/"),
                throttle=lambda: calls.append(1),
            )
        self.assertEqual(len(calls), 2)  # ajax e página

    def test_linha_que_nao_e_capitulo_fica_de_fora(self) -> None:
        # zazamanga põe banner/ícone no meio da lista de capítulos.
        listing = fixture("www.zazamanga.com", "chapters") + (
            '<div class="wp-manga-chapter"><span><a href="/banner/x.png">Banner</a>'
            "</span></div>"
        )
        scraper = FakeScraper({"https://x.com/manga/x/ajax/chapters/": listing})
        with mock.patch.object(Generic, "scraper", scraper):
            chapters = Generic.chapters(mock.Mock(source="https://x.com/manga/x/"))
        self.assertEqual(len(chapters), 3)
        self.assertTrue(all("/chapter-" in c["url"] for c in chapters))

    def test_capitulos_nao_precisam_de_ul_version_chap(self) -> None:
        # mangaread devolve os `<li>` soltos, sem `ul.version-chap`.
        listing = (
            fixture("www.mangaread.org", "chapters")
            .replace('<ul class="main version-chap">', "")
            .replace("</ul>", "")
        )
        self.assertIn("li", listing)
        self.assertNotIn("version-chap", listing)
        scraper = FakeScraper({"https://x.com/manga/x/ajax/chapters/": listing})
        with mock.patch.object(Generic, "scraper", scraper):
            chapters = Generic.chapters(mock.Mock(source="https://x.com/manga/x/"))
        self.assertEqual(len(chapters), 3)

    def test_leitor_ignora_banner_relativo(self) -> None:
        # zazamanga serve o banner de topo como `wp-manga-chapter-img`.
        html = (
            '<div class="reading-content">'
            '<img class="wp-manga-chapter-img" src="/banner/x.png">'
            '<img class="wp-manga-chapter-img" src="//cdn.x/1.webp">'
            "</div>"
        )
        pages = Generic.pages(mock.Mock(source="https://x.com/cap/"), html)
        self.assertEqual(pages, ["https://cdn.x/1.webp"])

    def test_leitor_devolve_paginas(self) -> None:
        for host in MADARA_HOSTS:
            with self.subTest(host=host):
                fixture_text = (
                    fixture(host, "chapter")
                    if (FIXTURES / f"{host}.chapter.html").exists()
                    else fixture("www.mangaread.org", "chapter")
                )
                scraper = FakeScraper({f"https://{host}/cap/": fixture_text})
                with mock.patch.object(Generic, "scraper", scraper):
                    result = Generic.chapter(mock.Mock(source=f"https://{host}/cap/"))
                self.assertEqual(len(result["pages"]), 3, host)
                self.assertTrue(result["pages"][0].startswith("https://"), host)

    def test_ficha_le_titulo_e_capa(self) -> None:
        for host in MADARA_HOSTS:
            with self.subTest(host=host):
                url = f"https://{host}/manga/x/"
                scraper = FakeScraper({url: fixture(host, "manga")})
                with mock.patch.object(Generic, "scraper", scraper):
                    info = Generic.info(url)
                self.assertTrue(info["title"], host)
                self.assertTrue(info["image"], host)
                self.assertTrue(info["id"], host)


class SlugDoBancoTests(unittest.TestCase):
    """Regressão: o que o banco já tem nesses hosts precisa continuar casando.

    A leitura em produção (02/11/2026) achou 0 manhwas e 0 capítulos nos 10
    hosts novos, então nenhum slug antigo depende do formato anterior
    (`27`): o id volta a ser o último segmento ("chapter-27"), como no resto
    do wrapper e como o capítulo gravado por `discover_new_chapters`.
    """

    def test_id_e_o_ultimo_segmento_como_no_banco(self) -> None:
        listing = (
            '<div class="wp-manga-chapter"><a '
            'href="https://aquareader.org/manga/x/x/chapter-27/">Chapter 27'
            "</a></div>"
        )
        with mock.patch.object(
            Generic, "scraper", FakeScraper({"https://x.com/m/ajax/chapters/": listing})
        ):
            item = Generic.chapters(mock.Mock(source="https://x.com/m/"))[0]
        self.assertEqual(item["id"], "chapter-27")
        self.assertEqual(item["id"], item["url"].rstrip("/").split("/")[-1])


class MadaraCloneTests(unittest.TestCase):
    def test_registro_aponta_para_o_clone(self) -> None:
        for host in CLONE_HOSTS:
            with self.subTest(host=host):
                self.assertIs(
                    get_source_by_link(f"https://{host}/manga/x"), MadaraClone
                )
                self.assertIn(host, nsfw_sources)

    def test_busca_usa_search_q_e_tira_apostrofo(self) -> None:
        for host in CLONE_HOSTS:
            with self.subTest(host=host):
                source = MadaraClone(f"https://{host}")
                get = mock.Mock(
                    return_value=FakeResponse(
                        fixture(host, "search"), f"https://{host}/search"
                    )
                )
                with mock.patch.object(source.client, "get", get):
                    results = source.search("A Spy's Survival")
                self.assertEqual(get.call_args.args[0], f"https://{host}/search")
                # apóstrofo derruba a busca dos clones (HTTP 500).
                self.assertEqual(
                    get.call_args.kwargs["params"], {"q": "A Spys Survival"}
                )
                self.assertTrue(results, host)
                self.assertTrue(results[0]["url"].startswith(f"https://{host}/"))

    def test_capitulos_vem_da_ficha(self) -> None:
        for host in CLONE_HOSTS:
            with self.subTest(host=host):
                url = f"https://{host}/manga/x"
                # os clones penduram a lista na ficha; não há ajax
                fixt = fixture(host, "manga") + fixture(host, "chapters")
                scraper = FakeScraper({url: fixt})
                with mock.patch.object(MadaraClone, "scraper", scraper):
                    chapters = MadaraClone.chapters(mock.Mock(source=url))
                self.assertEqual(len(chapters), 3, host)
                # URL relativa da fonte vira absoluta (vai para Chapter.source)
                self.assertTrue(chapters[0]["url"].startswith(f"https://{host}/"), host)

    def test_leitor_le_read_content(self) -> None:
        for host in CLONE_HOSTS:
            with self.subTest(host=host):
                url = f"https://{host}/manga/x/chapter-1"
                scraper = FakeScraper({url: fixture(host, "chapter")})
                with mock.patch.object(MadaraClone, "scraper", scraper):
                    pages = MadaraClone.pages(mock.Mock(source=url))
                self.assertEqual(len(pages), 3, host)
                self.assertTrue(pages[0].startswith("https://"), host)

    def test_ficha_tira_o_selo_18(self) -> None:
        url = "https://manhwa18.cc/webtoon/stop-smoking"
        scraper = FakeScraper({url: fixture("manhwa18.cc", "manga")})
        with mock.patch.object(MadaraClone, "scraper", scraper):
            info = MadaraClone.info(url)
        self.assertFalse(info["title"].startswith("18+"))


class ThreeHentaiSearchTests(unittest.TestCase):
    def test_busca_le_os_cards_doujin(self) -> None:
        html = """
        <div class="doujin flag flag-eng">
          <a class="cover" href="https://3hentai.net/d/684582">
            <img data-src="https://s1.3hentai.xyz/d2357568/thumb.jpg">
            <div class="title">[Momobird] Stop Smoking! 21-30</div></a>
        </div>
        """
        source = ThreeHentai("https://3hentai.net")
        get = mock.Mock(return_value=FakeResponse(html, "https://3hentai.net/search"))
        with mock.patch.object(source.client, "get", get):
            results = source.search("stop smoking")
        self.assertEqual(get.call_args.kwargs["params"], {"q": "stop smoking"})
        self.assertEqual(results[0]["url"], "https://3hentai.net/d/684582")
        self.assertEqual(
            results[0]["image"], "https://s1.3hentai.xyz/d2357568/thumb.jpg"
        )
        self.assertIn("Stop Smoking", results[0]["title"])


class RegistryAndRefererTests(unittest.TestCase):
    def test_hosts_novos_estao_na_busca_do_painel(self) -> None:
        for host in MADARA_HOSTS + CLONE_HOSTS + ("3hentai.net",):
            with self.subTest(host=host):
                self.assertIn(host, searchable_sources)
                self.assertIsNotNone(get_searchable_source(host))
                self.assertIsNotNone(get_searchable_source("www." + host))
                self.assertTrue(callable(searchable_sources[host].search))

    def test_referer_dos_cdns_novos_e_o_site(self) -> None:
        cases = {
            "https://img02.manga18fx.com/chapters/a.jpg": "https://manga18fx.com/",
            "https://img02.manhwa18.cc/uploads/a.jpg": "https://manhwa18.cc/",
            "https://cdn02.mangadna.com/chapters/a.jpg": "https://mangadna.com/",
            "https://u1.manhuatop.org/manga/a.webp": "https://mangatop.org/",
            "https://cdn.zinmanga1.com//zin/lightning-degree/1/0.webp": "https://www.zazamanga.com/",
        }
        for image, referer in cases.items():
            with self.subTest(image=image):
                self.assertEqual(get_referer_from_url(image), referer)


class CategoryTests(unittest.TestCase):
    def test_so_as_nsfw_estao_marcadas(self) -> None:
        self.assertIn("3hentai.net", nsfw_sources)
        for host in MADARA_HOSTS:
            self.assertNotIn(host, nsfw_sources, host)
        for host in CLONE_HOSTS:
            self.assertIn(host, nsfw_sources, host)


if __name__ == "__main__":
    unittest.main()
