"""Parser MangaThemesia (arenascan, asterscans, akazascans, rokaricomics,
rackusreads) sobre HTML fixo, sem rede.

O HTML reproduz o que cada site devolve de dentro da Lambda, não o layout
que o navegador mostra.
"""

from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest import mock

import django

django.setup()

from brscans.wrapper.sources import (  # noqa: E402
    get_searchable_source,
    get_source_by_link,
)
from brscans.wrapper.sources.MangaThemesia import MangaThemesia  # noqa: E402

HOSTS = (
    "arenascan.com",
    "asterscans.com",
    "akazascans.org",
    "rokaricomics.com",
    "rackusreads.com",
)

SEARCH = """
<div class="listupd">
  <div class="bsx">
    <a href="https://arenascan.com/manga/sss-grade-saint-knight/"
       title="SSS Grade Saint Knight">
      <div class="limit">
        <img alt="SSS Grade Saint Knight"
             src="https://arenascan.com/wp-content/uploads/2025/08/capa-285x375.jpg">
      </div>
      <div class="bigor"><div class="tt">SSS Grade Saint Knight</div></div>
    </a>
  </div>
</div>
"""

MANGA = """
<h1 class="entry-title">SSS Grade Saint Knight</h1>
<div class="thumb"><img src="https://arenascan.com/wp-content/uploads/capa.jpg"></div>
<div class="entry-content"><p>Um cavaleiro santo.</p></div>
<div class="bxcl"><ul>
  <li data-num="232"><div class="chbox"><div class="eph-num">
    <a href="https://arenascan.com/sss-grade-saint-knight-chapter-232/">
      <span class="chapternum">Chapter 232</span>
      <span class="chapterdate">November 1, 2026</span>
    </a>
  </div></div></li>
  <li data-num="231"><div class="chbox"><div class="eph-num">
    <a href="https://arenascan.com/sss-grade-saint-knight-chapter-231/">
      <span class="chapternum">Chapter\t\t231</span>
      <span class="chapterdate">October 25, 2026</span>
    </a>
  </div></div></li>
</ul></div>
"""

CHAPTER = """
<h1 class="entry-title">SSS Grade Saint Knight Chapter 232</h1>
<div id="readerarea">
  <img data-src="https://cdn.arenascan.com/arena-bucket/1/232/a.webp" src="">
  <img src="https://cdn.arenascan.com/arena-bucket/1/232/b.webp">
</div>
"""


class FakeResponse:
    def __init__(self, text, url):
        self.text = text
        self.url = url


def patched(html):
    return mock.patch.object(
        MangaThemesia, "_get", return_value=FakeResponse(html, "x")
    )


class MangaThemesiaTests(unittest.TestCase):
    def test_busca_sai_do_listupd_e_nao_do_catalogo(self) -> None:
        # `?title=` devolve o catálogo inteiro; a busca real é `/?s=`.
        source = MangaThemesia("https://arenascan.com")
        with mock.patch.object(
            MangaThemesia, "_get", return_value=FakeResponse(SEARCH, "x")
        ) as get:
            results = source.search("sss")
        self.assertEqual(get.call_args.kwargs["params"], {"s": "sss"})
        self.assertEqual(get.call_args.args[0], "https://arenascan.com")
        self.assertEqual(len(results), 1)
        self.assertEqual(
            results[0]["url"],
            "https://arenascan.com/manga/sss-grade-saint-knight/",
        )
        self.assertEqual(results[0]["title"], "SSS Grade Saint Knight")
        # capa do card vem em 285x375; a URL do banco é a original
        self.assertEqual(
            results[0]["image"],
            "https://arenascan.com/wp-content/uploads/2025/08/capa.jpg",
        )

    def test_busca_nao_duplica_o_card_bs_dentro_do_bsx(self) -> None:
        # O layout novo embrulha o `.bsx` num `.bs`: o mesmo link aparece
        # duas vezes no HTML e uma vez só no resultado.
        html = """
        <div class="listupd">
          <div class="bs"><div class="bsx">
            <a href="https://arenascan.com/manga/obra/" title="Obra">
              <img src="https://arenascan.com/c.webp">
            </a>
          </div></div>
        </div>
        """
        source = MangaThemesia("https://arenascan.com")
        with mock.patch.object(
            MangaThemesia, "_get", return_value=FakeResponse(html, "x")
        ):
            results = source.search("obra")
        self.assertEqual(
            [r["url"] for r in results], ["https://arenascan.com/manga/obra/"]
        )

    def test_busca_sem_resultado_devolve_lista_vazia(self) -> None:
        source = MangaThemesia("https://arenascan.com")
        with mock.patch.object(
            MangaThemesia, "_get", return_value=FakeResponse("<html></html>", "x")
        ):
            self.assertEqual(source.search("nada"), [])

    def test_info_le_titulo_resumo_e_capa(self) -> None:
        with mock.patch.object(
            MangaThemesia,
            "_get",
            return_value=FakeResponse(
                MANGA, "https://arenascan.com/manga/sss-grade-saint-knight/"
            ),
        ):
            info = MangaThemesia.info(
                "https://arenascan.com/manga/sss-grade-saint-knight/"
            )
        self.assertEqual(info["id"], "sss-grade-saint-knight")
        self.assertEqual(info["title"], "SSS Grade Saint Knight")
        self.assertEqual(info["summary"], "Um cavaleiro santo.")
        self.assertEqual(
            info["image"],
            "https://arenascan.com/wp-content/uploads/capa.jpg",
        )

    def test_capitulos_saem_do_bxcl_com_numero_e_data(self) -> None:
        with patched(MANGA):
            chapters = MangaThemesia.chapters(
                SimpleNamespace(
                    source="https://arenascan.com/manga/sss-grade-saint-knight/"
                )
            )
        self.assertEqual(len(chapters), 2)
        self.assertEqual(chapters[0]["id"], "sss-grade-saint-knight-chapter-232")
        self.assertEqual(chapters[0]["title"], "Chapter 232")
        self.assertEqual(chapters[0]["release_date"], "November 1, 2026")
        # espaços/tabs do markup não podem vazar para o título
        self.assertEqual(chapters[1]["title"], "Chapter 231")

    def test_paginas_saem_do_readerarea(self) -> None:
        pages = MangaThemesia.pages(
            "https://arenascan.com/sss-grade-saint-knight-chapter-232/",
            CHAPTER,
        )
        self.assertEqual(
            pages,
            [
                "https://cdn.arenascan.com/arena-bucket/1/232/a.webp",
                "https://cdn.arenascan.com/arena-bucket/1/232/b.webp",
            ],
        )

    def test_chapter_devolve_titulo_e_paginas(self) -> None:
        with patched(CHAPTER):
            data = MangaThemesia.chapter(
                SimpleNamespace(
                    source="https://arenascan.com/sss-grade-saint-knight-chapter-232/"
                )
            )
        self.assertEqual(data["title"], "SSS Grade Saint Knight Chapter 232")
        self.assertEqual(len(data["pages"]), 2)

    def test_pagina_sem_readerarea_devolve_vazio(self) -> None:
        # Página de challenge/bloqueio não vira lista com uma imagem falsa.
        self.assertEqual(MangaThemesia.pages("https://x/cap/", "<html></html>"), [])


class RegistroTests(unittest.TestCase):
    def test_os_cinco_hosts_usam_o_parser_base(self) -> None:
        for host in HOSTS:
            self.assertIs(get_source_by_link(f"https://{host}/manga/x"), MangaThemesia)
            self.assertIs(get_searchable_source(f"www.{host}"), MangaThemesia, host)

    def test_parser_base_herda_do_generic_sem_copiar_scraper(self) -> None:
        from brscans.wrapper.sources.Generic import Generic

        self.assertTrue(issubclass(MangaThemesia, Generic))
        self.assertIs(MangaThemesia.scraper, Generic.scraper)


if __name__ == "__main__":
    unittest.main()
