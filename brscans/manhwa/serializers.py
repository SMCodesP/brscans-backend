from rest_framework import serializers

from brscans.manhwa.models import Manhwa


class ManhwaSerializer(serializers.HyperlinkedModelSerializer):
    class Meta:
        model = Manhwa
        fields = ("title", "author", "description")
