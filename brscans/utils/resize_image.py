from PIL import Image


def resize_image(path_image, max_height=1080, max_width=1920) -> Image:
    try:
        img = Image.open(path_image)

        width, height = img.size
        if height > max_height or width > max_width:
            if width > max_width:
                ratio = max_width / width
                width = max_width
                height = int(height * ratio)

            if height > max_height:
                ratio = max_height / height
                width = int(width * ratio)
                height = max_height

            return img.resize((width, height), Image.LANCZOS)
        else:
            return None
    except FileNotFoundError:
        # should probably have a log here
        pass
