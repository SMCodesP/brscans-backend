from debug_toolbar.toolbar import debug_toolbar_urls
from django.conf.urls import include
from django.contrib import admin
from django.urls import path

from django.conf.urls.static import static
from rest_framework.routers import DefaultRouter
from rest_framework_nested import routers
from django.conf import settings

from brscans.manhwa.views.chapter import ChapterViewSet
from brscans.manhwa.views.manhwa_chapter import ManhwaChapterViewSet
from brscans.manhwa.views.manhwa_vw import ManhwaViewSet

from brscans.wrapper.views import WrapperViewSet

router = DefaultRouter()
router.register(r"manhwas", ManhwaViewSet, basename="manhwas")
router.register(r"wrapper", WrapperViewSet, basename="wrapper")
router.register(r"chapters", ChapterViewSet, basename="chapters")

client_router = routers.NestedSimpleRouter(router, r"manhwas", lookup="manhwa")
client_router.register(r"chapters", ManhwaChapterViewSet, basename="chapters")


urlpatterns = (
    [
        path(r"", include(router.urls)),
        path(r"", include(client_router.urls)),
        path("admin/", admin.site.urls),
    ]
    + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    + debug_toolbar_urls()
)
