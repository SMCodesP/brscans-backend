from brscans.manhwa.models import Manhwa
from brscans.manhwa.tasks.sync_chapters import sync_chapters


def sync_manhwas():
    manhwas = Manhwa.objects.all()

    for manhwa in manhwas:
        sync_chapters(manhwa.pk)

    return True
