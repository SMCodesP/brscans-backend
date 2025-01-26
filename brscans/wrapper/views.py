from django.http import HttpResponseRedirect
from django.utils.decorators import method_decorator
from django.views.decorators.cache import cache_page

from rest_framework import viewsets
from rest_framework.decorators import action

from rest_framework.response import Response
from rest_framework.request import Request
from brscans import settings

from brscans.wrapper.sources.Nexo import Nexo
from brscans.wrapper.sources.Cerise import Cerise
from brscans.wrapper.sources.Gekkou import Gekkou


class WrapperViewSet(viewsets.ViewSet):
    """
    A simple ViewSet for listing or retrieving users.
    """

    @action(detail=False, methods=["get"])
    def homepage(self, request):
        gekkou = Gekkou()
        return Response(gekkou.homepage())

    @action(detail=False, methods=["get"])
    def search(self, request: Request):
        query = request.query_params.get("query")
        gekkou = Gekkou()
        return Response(gekkou.search(query))

    @action(detail=True, methods=["get"])
    def info(self, request: Request, pk=None):
        is_full = request.query_params.get("full", False) == "true"
        gekkou = Gekkou()
        return Response(gekkou.info(pk, capthers=is_full))

    @action(detail=True, methods=["get"])
    def chapters(self, request: Request, pk=None):
        gekkou = Gekkou()
        return Response(gekkou.chapters(pk))

    @action(detail=True, methods=["get"])
    def chapter(self, request: Request, pk=None):
        cap = request.query_params.get("cap")
        gekkou = Gekkou()
        return Response(gekkou.chapter(pk, cap))

    @action(detail=True, methods=["get"])
    @method_decorator(cache_page(60 * 60 * 2))
    def pages(self, request: Request, pk=None):
        cap = request.query_params.get("cap")
        upscale = request.query_params.get("upscale")

        gekkou = Gekkou()
        return Response(gekkou.pages(pk, cap, upscale == "true"))
