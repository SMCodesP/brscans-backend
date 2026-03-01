from rest_framework import mixins, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from brscans.manhwa.models import Notification
from brscans.manhwa.serializers import NotificationSerializer


class NotificationViewSet(
    mixins.ListModelMixin, mixins.DestroyModelMixin, viewsets.GenericViewSet
):
    permission_classes = [IsAuthenticated]
    serializer_class = NotificationSerializer

    def get_queryset(self):
        return Notification.objects.filter(user=self.request.user)

    @action(detail=True, methods=["post"])
    def read(self, request, pk=None):
        notification = self.get_object()
        notification.read = True
        notification.save()
        return Response({"status": "Notificação marcada como lida."})

    @action(detail=False, methods=["post"], url_path="read-all")
    def read_all(self, request):
        notifications = self.get_queryset().filter(read=False)
        updated = notifications.update(read=True)
        return Response(
            {"status": f"{updated} notificações marcadas como lidas."}
        )
