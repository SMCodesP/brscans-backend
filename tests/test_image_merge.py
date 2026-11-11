"""Junção de imagens: mesma divisão de páginas, sem apagar antes de baixar."""

from unittest import mock

from django.core.files.base import ContentFile
from django.test import TestCase, override_settings
from PIL import Image

from brscans.manhwa.models import Chapter, ImageVariants, Manhwa, Page
from brscans.manhwa.tasks import images_variants as tasks
from brscans.utils import image as img


def sizes_to_images(sizes):
    return [Image.new("RGB", size) for size in sizes]


def image_bytes():
    """ContentFile com content_type, como process_merge_images devolve."""
    content = ContentFile(b"webp", name="merged_image.webp")
    content.content_type = "image/webp"
    return content


def old_division(images):
    """Divisão anterior (split_large_image + batch_urls), só como referência."""
    all_images = []
    for image in images:
        if image.height <= 16383:
            all_images.append(image)
            continue
        for top in range(0, image.height, 16383):
            all_images.append(image.crop(
                (0, top, image.width, min(top + 16383, image.height))
            ))
    # o merge (o de antes e o novo) ignora grupo vazio; a referência não
    return [len(group) for group in img.batch_urls(all_images) if group]


class PageDivisionTests(TestCase):
    def division(self, sizes):
        # side_effect fecha cada imagem: a referência exige cópias novas. Só o
        # cabeçalho é lido na divisão; é ele que devolve o tamanho aqui.
        with mock.patch.object(
            img, "download_head", side_effect=sizes_to_images(sizes)
        ):
            groups = img.merge_page_groups(list(range(len(sizes))))
        self.assertEqual(
            [len(group) for group in groups], old_division(sizes_to_images(sizes))
        )
        return [len(group) for group in groups]

    def test_mesma_divisao_do_algoritmo_anterior(self):
        self.assertEqual(self.division([(800, 3000)] * 4), [2, 2])
        # largura muda: fecha o grupo
        self.assertEqual(
            self.division([(800, 1000), (900, 1000), (900, 2000)]), [1, 2]
        )
        # passa de 8191 px: abre grupo novo
        self.assertEqual(self.division([(800, 5000), (800, 5000)]), [1, 1])
        # imagem única acima de 16383 px: é partida antes de agrupar (16383
        # não cabe em 8191, então viram duas páginas)
        self.assertEqual(self.division([(800, 20000)]), [1, 1])

    def test_imagem_partida_e_recortada_antes_do_webp(self):
        """Colar a imagem inteira em cada pedaço passava de 16383 px."""
        from io import BytesIO

        def tall():
            image = Image.new("RGB", (64, 20000))
            image.paste((255, 0, 0), (0, 16383, 64, 20000))
            return image

        sizes = [(64, 20000), (64, 1000)]
        with mock.patch.object(
            img, "download_head", side_effect=sizes_to_images(sizes)
        ):
            groups = img.merge_page_groups(["alta", "curta"])
        # o resto da imagem partida agrupa com a próxima
        self.assertEqual(
            groups,
            [[("alta", 0, 16383)], [("alta", 16383, 3617), ("curta", 0, 1000)]],
        )

        source = {"alta": tall, "curta": lambda: Image.new("RGB", (64, 1000))}
        with mock.patch.object(
            img, "download_image", side_effect=lambda url: source[url]()
        ):
            merged = [
                Image.open(BytesIO(tasks.merge_group(group).read()))
                for group in groups
            ]
        self.assertEqual([m.size for m in merged], [(64, 16383), (64, 4617)])
        # o segundo pedaço começa no trecho de baixo (vermelho), não no topo
        self.assertGreater(merged[1].getpixel((5, 5))[0], 200)
        self.assertLess(merged[0].getpixel((5, 5))[0], 50)

    def test_download_falhando_nao_recorta_a_lista(self):
        with mock.patch.object(img, "download_head", return_value=None), (
            mock.patch.object(img, "download_image", return_value=None)
        ):
            with self.assertRaises(RuntimeError):
                img.merge_page_groups(["a"])

    def test_medicao_nao_baixa_a_imagem_inteira(self):
        """O merge baixa em seguida: medir com o arquivo todo era download duplo."""
        with mock.patch.object(
            img, "download_head", return_value=Image.new("RGB", (800, 800))
        ) as head, mock.patch.object(img, "download_image") as full:
            img.merge_page_groups(["https://x/1.webp"])
        head.assert_called_once()
        full.assert_not_called()


@override_settings(PUBLIC_MEDIA_LOCATION="media/")
class MergePagesOriginalTests(TestCase):
    def setUp(self):
        manhwa = Manhwa.objects.create(
            title="m", status="ongoing", description="d"
        )
        self.chapter = Chapter.objects.create(
            title="c", slug="c", manhwa=manhwa
        )
        for _ in range(3):
            Page.objects.create(
                chapter=self.chapter,
                images=ImageVariants.objects.create(original="o.webp"),
                quantity_merged=1,
            )
        self.merge = mock.patch.object(
            tasks, "process_image_translate", return_value={}
        )
        self.merge.start()
        self.addCleanup(self.merge.stop)
        # Referência guarda o storage do campo: troca antes de criar a instance
        self.storage = mock.Mock()
        self.storage._save.side_effect = lambda name, content: name
        patcher = mock.patch.object(
            ImageVariants._meta.get_field("original"), "storage", self.storage
        )
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_falha_no_download_mantem_as_paginas_antigas(self):
        with mock.patch.object(
            tasks, "merge_page_groups", return_value=[["a"], ["b"]]
        ), mock.patch.object(
            tasks, "download_pieces", side_effect=RuntimeError("fonte caiu")
        ):
            with self.assertRaises(RuntimeError):
                tasks.merge_pages_original.sync([], self.chapter.pk, ["c"])

        self.assertEqual(self.chapter.pages.count(), 3)
        self.assertEqual(
            list(self.chapter.pages.values_list("images__original", flat=True)),
            ["o.webp", "o.webp", "o.webp"],
        )

    def test_merge_substitui_as_paginas_com_a_mesma_divisao(self):
        def download(urls):
            return sizes_to_images([(800, 1000)] * len(urls))

        with mock.patch.object(
            tasks, "merge_page_groups", return_value=[["a", "b"], ["c"]]
        ), mock.patch.object(tasks, "download_pieces", side_effect=download):
            tasks.merge_pages_original.sync([], self.chapter.pk, ["c"])

        pages = list(self.chapter.pages.order_by("order"))
        self.assertEqual([p.quantity_merged for p in pages], [2, 1])
        self.assertEqual([p.order for p in pages], [0, 1])
        self.assertTrue(all(p.images.original for p in pages))
        self.assertEqual(len({p.images_id for p in pages}), 2)

    def test_redisparo_nao_baixa_nem_recria_capitulo_completo(self):
        """A fila do Modal pode passar da trava; o disparo repetido sai cedo."""
        with mock.patch.object(
            tasks, "merge_page_groups", return_value=[["a"], ["b"], ["c"]]
        ), mock.patch.object(tasks, "download_pieces") as download:
            result = tasks.merge_pages_original.sync(
                [], self.chapter.pk, ["c"]
            )

        self.assertIn("skipping", result["Message"])
        download.assert_not_called()
        self.assertEqual(self.chapter.pages.count(), 3)

    def test_original_fica_no_path_do_id_e_retry_sobrescreve(self):
        """UUID por tentativa deixava o original anterior órfão no S3."""
        saved = []
        self.storage._save.side_effect = lambda name, content: saved.append(
            name
        ) or name
        self.storage.get_available_name.side_effect = (
            lambda name, max_length=None: f"{name}_renomeado"
        )
        variant = ImageVariants.objects.create()

        tasks._save_original(variant, image_bytes(), ["chapters", "7"])
        tasks._save_original(variant, image_bytes(), ["chapters", "7"])

        path = f"chapters/7/original/{variant.pk}.webp"
        # mesmo path nas duas tentativas, sem o rename do storage
        self.assertEqual(saved, [path, path])
        variant.refresh_from_db()
        self.assertEqual(variant.original.name, path)

    def test_redisparo_refaz_quando_a_divisao_mudou(self):
        with mock.patch.object(
            tasks, "merge_page_groups", return_value=[["a"], ["b"]]
        ), mock.patch.object(
            tasks, "download_pieces",
            side_effect=lambda urls: sizes_to_images([(800, 1000)] * len(urls)),
        ) as download:
            tasks.merge_pages_original.sync([], self.chapter.pk, ["c"])

        download.assert_called()
        self.assertEqual(self.chapter.pages.count(), 2)


class WebpSizeTests(TestCase):
    def test_reads_every_webp_variant_from_header(self):
        from io import BytesIO

        from PIL import Image

        from brscans.utils.image import _webp_size

        rgba = Image.new("RGBA", (321, 1234), (9, 9, 9, 128))
        for image, kwargs in (
            (rgba.convert("RGB"), {"lossless": False}),
            (rgba.convert("RGB"), {"lossless": True}),
            (rgba, {"lossless": False, "exif": b"Exif\x00\x00x"}),
        ):
            data = BytesIO()
            image.save(data, "WEBP", **kwargs)
            self.assertEqual(_webp_size(data.getvalue()[:30]), (321, 1234))

    def test_other_formats_are_not_webp(self):
        from brscans.utils.image import _webp_size

        self.assertIsNone(_webp_size(b"\x89PNG" + b"0" * 40))
