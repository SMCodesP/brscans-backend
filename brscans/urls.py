from django.contrib import admin
from django.urls import path

from rest_framework import routers
from brscans.manhwa.views import ManhwaViewSet
from brscans.wrapper.views import WrapperViewSet


router = routers.DefaultRouter()
router.register(r"manhwa", ManhwaViewSet)
router.register(r"wrapper", WrapperViewSet, basename="wrapper")

urlpatterns = [
    path("admin/", admin.site.urls),
]

urlpatterns += router.urls
