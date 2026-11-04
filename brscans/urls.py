from debug_toolbar.toolbar import debug_toolbar_urls
from django.conf import settings
from django.conf.urls import include
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import path
from drf_spectacular.views import (
    SpectacularAPIView,
    SpectacularRedocView,
    SpectacularSwaggerView,
)
from rest_framework.routers import DefaultRouter
from rest_framework_nested import routers

from brscans.manhwa.views.chapter import ChapterViewSet
from brscans.manhwa.views.comment_vw import CommentViewSet
from brscans.manhwa.views.image import ImageVariantViewSet
from brscans.manhwa.views.manhwa_chapter import ManhwaChapterViewSet
from brscans.manhwa.views.manhwa_vw import ManhwaViewSet
from brscans.manhwa.views.notification_vw import NotificationViewSet
from brscans.manhwa.views.panel import (
    PanelChapterViewSet,
    PanelManhwaViewSet,
    PanelProblemViewSet,
    PanelSourceView,
)

router = DefaultRouter()
router.register(r"manhwas", ManhwaViewSet, basename="manhwas")
router.register(r"chapters", ChapterViewSet, basename="chapters")
router.register(r"images", ImageVariantViewSet, basename="image-variants")
router.register(r"comments", CommentViewSet, basename="comments")
router.register(r"notifications", NotificationViewSet, basename="notifications")

# Painel (/panel): rotas de admin, staff only. Fora do router principal para
# não misturar com as rotas públicas.
panel_router = DefaultRouter()
panel_router.register(r"manhwas", PanelManhwaViewSet, basename="panel-manhwas")
panel_router.register(
    r"chapters", PanelChapterViewSet, basename="panel-chapters"
)
panel_router.register(
    r"problems", PanelProblemViewSet, basename="panel-problems"
)

client_router = routers.NestedSimpleRouter(router, r"manhwas", lookup="manhwa")
client_router.register(r"chapters", ManhwaChapterViewSet, basename="chapters")


urlpatterns = (
    [
        path(r"", include(router.urls)),
        path(r"", include(client_router.urls)),
        path("panel/", include(panel_router.urls)),
        path("panel/sources/", PanelSourceView.as_view()),
        path("panel/sources/<str:name>/search/", PanelSourceView.as_view()),
        path(r"", include("brscans.authentication.urls")),
        path("admin/", admin.site.urls),
        path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
        path(
            "api/swagger/",
            SpectacularSwaggerView.as_view(url_name="schema"),
            name="swagger-ui",
        ),
        path(
            "api/redoc/",
            SpectacularRedocView.as_view(url_name="schema"),
            name="redoc",
        ),
    ]
    + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    + debug_toolbar_urls()
)
