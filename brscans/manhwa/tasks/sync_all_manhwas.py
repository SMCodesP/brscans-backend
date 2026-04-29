from brscans.manhwa.models import Manhwa
from brscans.manhwa.tasks.sync_chapters import sync_chapters


def sync_all_manhwas(limit_per_manhwa: int = 5):
    manhwas = list(Manhwa.objects.all())

    for manhwa in manhwas:
        sync_chapters(manhwa.pk, limit_per_manhwa)

    return {"total": len(manhwas)}


def sync_all_manhwas_handler(event, context):
    return sync_all_manhwas()
