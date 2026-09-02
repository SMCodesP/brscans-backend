from __future__ import annotations

import unittest

from brscans.utils.image_contract import image_destination


class ImageContractTests(unittest.TestCase):
    def test_supported_formats_align_suffix_and_type(self) -> None:
        cases = {
            "image/jpeg": ".jpeg",
            "image/png": ".png",
            "image/webp": ".webp",
        }
        for content_type, suffix in cases.items():
            with self.subTest(content_type=content_type):
                path, actual_type = image_destination(
                    ["chapters", "42"], "raw", "page", content_type
                )
                self.assertEqual(path, f"chapters/42/raw/page{suffix}")
                self.assertEqual(actual_type, content_type)

    def test_string_folder_is_not_split_into_characters(self) -> None:
        path, _ = image_destination("chapters/42", "raw", "page", "image/webp")
        self.assertEqual(path, "chapters/42/raw/page.webp")

    def test_rejects_unsupported_type(self) -> None:
        with self.assertRaises(ValueError):
            image_destination("chapter", "raw", "page", "image/gif")


if __name__ == "__main__":
    unittest.main()
