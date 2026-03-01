from rest_framework import viewsets
from rest_framework.response import Response

from brscans.manhwa.models import Comment
from brscans.manhwa.serializers import CommentSerializer


class CommentViewSet(viewsets.ModelViewSet):
    serializer_class = CommentSerializer

    def get_queryset(self):
        qs = (
            Comment.objects.all()
            .select_related("user", "user__profile")
            .prefetch_related(
                "replies", "replies__user", "replies__user__profile"
            )
        )
        chapter_id = self.request.query_params.get("chapter")
        if chapter_id:
            qs = qs.filter(chapter_id=chapter_id, parent__isnull=True)
        return qs

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)

    def destroy(self, request, *args, **kwargs):
        comment = self.get_object()
        if comment.user != request.user:
            return Response(
                {"error": "Sem permissão para deletar este comentário."},
                status=403,
            )
        return super().destroy(request, *args, **kwargs)
