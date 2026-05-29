from rest_framework import viewsets

from brscans.manhwa.models import ImageVariants
from brscans.manhwa.serializers import VariantsSerializer, VariantsUpdateSerializer
from brscans.pagination import TotalPagination


class ImageVariantViewSet(viewsets.ModelViewSet):
    serializer_class = VariantsSerializer
    queryset = ImageVariants.objects.all()
    pagination_class = TotalPagination
    authentication_classes = []
    permission_classes = []

    def partial_update(self, request, *args, **kwargs):
        self.serializer_class = VariantsUpdateSerializer
        response = super().partial_update(request, *args, **kwargs)
        
        # Se o campo 'translated' foi atualizado com sucesso, removemos o cache temporário do MongoDB
        translated_path = request.data.get("translated")
        if translated_path:
            instance_id = kwargs.get("pk")
            if instance_id:
                try:
                    from pymongo import MongoClient
                    mongo_client = MongoClient("mongodb+srv://smcodes:8HmPrzJpJT5AiOR5@brscans-ia.lf9osoc.mongodb.net/?retryWrites=true&w=majority&appName=brscans-ia")
                    db = mongo_client["brscans-ia"]
                    collection = db["blk_list"]
                    
                    res = collection.delete_one({"image_id": int(instance_id)})
                    print(f"Limpeza de MongoDB para variant {instance_id}: deletou {res.deleted_count} documentos.")
                except Exception as e:
                    print(f"Erro ao deletar blk_list temporario para variant {instance_id}:", e)
                    
        return response
