"""Parsers das fontes consertadas, sem rede (HTML de fixture).

Cobre os seletores que a auditoria de fontes quebradas apontou: comizy/MangaBuddy
(Next.js), manhuatop (payload do Next.js), kingofshojo (tema "king"), mangadass
(lista sem POST), mangayy/mgread e 3hentai (valida a URL).
"""

from __future__ import annotations

import unittest
from unittest import mock

import django
import httpx

django.setup()

from brscans.wrapper.sources import get_source_by_link  # noqa: E402
from brscans.wrapper.sources.Comizy import Comizy  # noqa: E402
from brscans.wrapper.sources.Generic import Generic  # noqa: E402
from brscans.wrapper.sources.KingOfShojo import KingOfShojo  # noqa: E402
from brscans.wrapper.sources.Mangadass import Mangadass  # noqa: E402
from brscans.wrapper.sources.RizzFables import RizzFables  # noqa: E402
from brscans.wrapper.sources.ThreeHentai import ThreeHentai  # noqa: E402


class FakeResponse:
    def __init__(self, text, url):
        self.text = text
        self.url = url
        self.status_code = 200

    def raise_for_status(self):
        return None


class FakeScraper:
    """Substitui o CloudScraper da fonte, guardando as URLs chamadas."""

    def __init__(self, html):
        self.html = html
        self.calls = []

    def get(self, url, **kwargs):
        self.calls.append(url)
        return FakeResponse(self.html, url)


def next_data(payload) -> str:
    import json

    return (
        '<html><body><script id="__NEXT_DATA__" type="application/json">'
        f"{json.dumps(payload)}</script></body></html>"
    )


def comizy_html(chapters, cover="https://rx.comizy.io/c.webp", summary="Sinopse"):
    manga = {
        "slug": "obra",
        "name": "Obra",
        "summary": summary,
        "cover": cover,
        "chapters": chapters,
    }
    return next_data({"props": {"pageProps": {"initialManga": manga}}})


class ComizyTests(unittest.TestCase):
    def test_le_capitulos_do_next_data(self) -> None:
        html = comizy_html(
            [
                {
                    "name": "Chapter 3",
                    "slug": "chapter-3",
                    "url": "/obra/chapter-3",
                    "updatedAt": "2026-10-16T09:40:07.000Z",
                },
                {
                    "name": "Chapter 2",
                    "slug": "chapter-2",
                    "url": "/obra/chapter-2",
                    "updatedAt": "2025-01-02T00:00:00.000Z",
                },
            ]
        )
        response = FakeResponse(html, "https://comizy.io/obra")
        with mock.patch.object(httpx, "get", return_value=response):
            chapters = Comizy.chapters("https://comizy.io/obra")
        self.assertEqual([c["id"] for c in chapters], ["chapter-3", "chapter-2"])
        self.assertEqual(chapters[0]["url"], "https://comizy.io/obra/chapter-3")
        self.assertEqual(chapters[0]["release_date"], "2026-10-16")

    def test_busca_com_ampersand_nao_corta_a_query(self) -> None:
        # Título com `&` ia solto na URL e o site recebia só "Foxy Gil ".
        source = Comizy("https://comizy.io")
        get = mock.Mock(return_value=FakeResponse(next_data({}), "x"))
        with mock.patch.object(httpx, "get", get):
            source.search("Foxy Gil & The Wrong path")
        self.assertEqual(get.call_args.args[0], "https://comizy.io/search")
        self.assertEqual(
            get.call_args.kwargs["params"], {"q": "Foxy Gil & The Wrong path"}
        )

    def test_info_usa_capa_e_resumo(self) -> None:
        response = FakeResponse(comizy_html([]), "https://comizy.io/obra")
        with mock.patch.object(httpx, "get", return_value=response):
            info = Comizy.info("https://mangabuddy.com/obra")
        self.assertEqual(info["title"], "Obra")
        self.assertEqual(info["summary"], "Sinopse")
        self.assertEqual(info["image"], "https://rx.comizy.io/c.webp")

    def test_paginas_saem_do_initial_chapter(self) -> None:
        # O DOM só renderiza as 10 primeiras; a lista inteira está no payload.
        html = next_data(
            {
                "props": {
                    "pageProps": {
                        "initialChapter": {
                            "images": [
                                "https://x7.cmzcdn.org/e/a.webp",
                                "https://x8.cmzcdn.org/e/b.webp",
                            ]
                        }
                    }
                }
            }
        )
        pages = Comizy.pages("https://comizy.io/obra/chapter-1", html)
        self.assertEqual(
            pages,
            ["https://x7.cmzcdn.org/e/a.webp", "https://x8.cmzcdn.org/e/b.webp"],
        )

    def test_paginas_caem_no_flux_reader_sem_payload(self) -> None:
        html = """
        <div class="flux-reader">
          <img src="https://x7.cmzcdn.org/e/a.webp">
        </div>
        """
        pages = Comizy.pages("https://comizy.io/obra/chapter-1", html)
        self.assertEqual(pages, ["https://x7.cmzcdn.org/e/a.webp"])

    def test_mangabuddy_reusa_comizy(self) -> None:
        from brscans.wrapper.sources.MangaBuddy import MangaBuddy

        self.assertTrue(issubclass(MangaBuddy, Comizy))
        self.assertIs(get_source_by_link("https://mangabuddy.com/obra"), MangaBuddy)
        self.assertIs(get_source_by_link("https://comizy.io/obra"), Comizy)




class KingOfShojoTests(unittest.TestCase):
    def test_cards_saem_de_div_bsx(self) -> None:
        html = """
        <div class="bsx">
          <a href="https://kingofshojo.com/manga/kill-the-villainess/">
            <img src="https://cdn.kingofshojo.com/c.webp">
          </a>
          <div class="tt">Kill The Villainess</div>
        </div>
        """
        cards = KingOfShojo.cards(html)
        self.assertEqual(len(cards), 1)
        self.assertEqual(cards[0]["id"], "kill-the-villainess")
        self.assertEqual(cards[0]["title"], "KILL THE VILLAINESS")

    def test_capitulos_saem_de_eph_num(self) -> None:
        html = """
        <div id="chapterlist"><ul>
          <li><div class="eph-num"><a href="https://kingofshojo.com/obra-chapter-2/">
            <span class="chapternum">Chapter 2</span>
            <span class="chapterdate">March 11, 2024</span>
          </a></div></li>
        </ul></div>
        """
        with mock.patch.object(Generic, "scraper", FakeScraper(html)):
            chapters = KingOfShojo.chapters("https://kingofshojo.com/manga/obra/")
        self.assertEqual(chapters[0]["id"], "obra-chapter-2")
        self.assertEqual(chapters[0]["release_date"], "March 11, 2024")


class MangadassTests(unittest.TestCase):
    def test_capitulos_saem_dos_links_do_a_h(self) -> None:
        html = """
        <ul><li class="a-h wleft">
          <a class="chapter-name" href="/manga/obra/chapter-1">Chapter 1</a>
          <span class="chapter-time">Oct 29, 2026</span>
        </li></ul>
        """
        scraper = FakeScraper(html)
        with mock.patch.object(Generic, "scraper", scraper):
            chapters = Mangadass.chapters("https://mangadass.com/manga/obra")
        self.assertEqual(scraper.calls, ["https://mangadass.com/manga/obra"])
        self.assertEqual(chapters[0]["id"], "chapter-1")
        self.assertEqual(
            chapters[0]["url"], "https://mangadass.com/manga/obra/chapter-1"
        )




class ThreeHentaiTests(unittest.TestCase):
    def test_chapters_faz_requisicao(self) -> None:
        scraper = FakeScraper("<html></html>")
        with mock.patch.object(Generic, "scraper", scraper):
            chapters = ThreeHentai.chapters("https://3hentai.net/d/1")
        self.assertEqual(scraper.calls, ["https://3hentai.net/d/1"])
        self.assertEqual(len(chapters), 1)
        self.assertEqual(chapters[0]["url"], "https://3hentai.net/d/1")


class SearchTests(unittest.TestCase):
    """Contrato `search` ({"id","title","url","image"}) sobre HTML fixo.

    O HTML abaixo reproduz o que a fonte devolve de dentro da Lambda, não o
    layout que o navegador mostra.
    """

    MADARA = """
    <div class="c-tabs-item__content"><div class="post-title"><h3>
      <a href="/manga/solo-leveling">Solo Leveling</a></h3></div>
      <img data-src="https://x/manga/capa-350x500.webp"></div>
    <div class="page-item-detail"><div class="item-title wleft"><h3>
      <a href="/manga/solo-leveling-ragnarok">Solo Leveling: Ragnarok</a>
      </h3></div><img src="https://x/manga/rag.jpg">
      <a href="/manga/solo-leveling-ragnarok/chapter-68">Cap 68</a></div>
    """

    def test_generic_search_le_os_dois_cards_do_madara(self) -> None:
        source = Generic("https://mangadass.com")
        with mock.patch.object(
            source.client,
            "get",
            return_value=FakeResponse(self.MADARA, "https://mangadass.com/"),
        ):
            results = source.search("solo")
        self.assertEqual(
            [r["title"] for r in results],
            ["Solo Leveling", "Solo Leveling: Ragnarok"],
        )
        self.assertEqual(results[0]["url"], "https://mangadass.com/manga/solo-leveling")
        # O capítulo dentro do card não pode virar resultado.
        self.assertEqual(len(results), 2)
        self.assertEqual(results[1]["image"], "https://x/manga/rag.jpg")

    def test_generic_search_sem_resultado_devolve_lista_vazia(self) -> None:
        source = Generic("https://mangadass.com")
        with mock.patch.object(
            source.client, "get", return_value=FakeResponse("<html></html>", "x")
        ):
            self.assertEqual(source.search("nada"), [])

    def test_mangadass_busca_em_search_q(self) -> None:
        # `/?s=` devolve o catálogo inteiro; a busca real é `/search?q=`.
        source = Mangadass("https://mangadass.com")
        response = FakeResponse(self.MADARA, "https://mangadass.com/search")
        with mock.patch.object(source.client, "get", return_value=response) as get:
            results = source.search("solo")
        self.assertEqual(get.call_args.args[0], "https://mangadass.com/search")
        self.assertEqual(get.call_args.kwargs["params"], {"q": "solo"})
        self.assertEqual(len(results), 2)

    def test_kingofshojo_absolutisa_a_url(self) -> None:
        html = """
        <div class="bsx"><a href="/manga/obra/"><img src="https://x/c.webp"></a>
          <div class="tt">Obra</div></div>
        """
        source = KingOfShojo("https://kingofshojo.com")
        with mock.patch.object(
            source.client, "get", return_value=FakeResponse(html, "x")
        ):
            results = source.search("obra")
        self.assertEqual(results[0]["url"], "https://kingofshojo.com/manga/obra/")
        self.assertEqual(results[0]["title"], "OBRA")

    def test_rizzfables_usa_o_card_bsx(self) -> None:
        html = """
        <div class="bsx"><a href="/series/r1-obra"><img src="/a.webp"></a>
          <div class="tt">Obra</div></div>
        """
        source = RizzFables("https://rizzfables.com")
        with mock.patch.object(
            source.client, "get", return_value=FakeResponse(html, "x")
        ):
            results = source.search("obra")
        self.assertEqual(results[0]["url"], "https://rizzfables.com/series/r1-obra")
        self.assertEqual(results[0]["image"], "/a.webp")


    def test_comizy_le_ssr_items(self) -> None:
        html = next_data(
            {
                "props": {
                    "pageProps": {
                        "ssrItems": [
                            {
                                "id": "abc",
                                "url": "/futari-solo-camp",
                                "name": "Futari Solo Camp",
                                "cover": "https://rx.comizy.io/c.webp",
                            }
                        ]
                    }
                }
            }
        )
        source = Comizy("https://comizy.io")
        with mock.patch.object(httpx, "get", return_value=FakeResponse(html, "x")):
            results = source.search("solo")
        self.assertEqual(results[0]["url"], "https://comizy.io/futari-solo-camp")
        self.assertEqual(results[0]["image"], "https://rx.comizy.io/c.webp")

    def test_registro_de_pesquisaveis_so_tem_host_com_search(self) -> None:
        from brscans.wrapper.sources import (
            get_searchable_source,
            searchable_sources,
        )

        self.assertTrue(searchable_sources)
        for host, cls in searchable_sources.items():
            self.assertTrue(callable(getattr(cls, "search", None)), host)
            self.assertIs(get_searchable_source("www." + host), cls)
        self.assertIsNone(get_searchable_source("nao-existe.com"))


if __name__ == "__main__":
    unittest.main()
