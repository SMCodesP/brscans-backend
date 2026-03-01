from django.contrib.auth.models import User
from rest_framework import serializers

from brscans.authentication.models import Favorite, UserProfile


class UserProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = UserProfile
        fields = (
            "avatar",
            "bio",
            "discord_id",
            "discord_username",
            "created_at",
        )
        read_only_fields = ("discord_id", "discord_username", "created_at")


class UserSerializer(serializers.ModelSerializer):
    profile = UserProfileSerializer(read_only=True)

    class Meta:
        model = User
        fields = ("id", "username", "email", "profile")
        read_only_fields = ("id",)


class RegisterSerializer(serializers.Serializer):
    username = serializers.CharField(max_length=150)
    password = serializers.CharField(min_length=6, write_only=True)
    email = serializers.EmailField(required=False, allow_blank=True)

    def validate_username(self, value):
        if User.objects.filter(username=value).exists():
            raise serializers.ValidationError(
                "Esse nome de usuário já está em uso."
            )
        return value


class LoginSerializer(serializers.Serializer):
    username = serializers.CharField()
    password = serializers.CharField()


class DiscordAuthSerializer(serializers.Serializer):
    code = serializers.CharField()


class FavoriteSerializer(serializers.ModelSerializer):
    class Meta:
        model = Favorite
        fields = ("id", "manhwa", "created_at")
        read_only_fields = ("id", "created_at")
