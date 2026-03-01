import os

import requests
from django.contrib.auth import authenticate
from django.contrib.auth.models import User
from rest_framework import status
from rest_framework.authtoken.models import Token
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response

from brscans.authentication.models import Favorite, UserProfile
from brscans.authentication.serializers import (
    DiscordAuthSerializer,
    LoginSerializer,
    RegisterSerializer,
    UserSerializer,
)
from brscans.manhwa.serializers import ManhwaSerializer

DISCORD_API_URL = "https://discord.com/api/v10"


@api_view(["POST"])
@permission_classes([AllowAny])
def register_view(request):
    serializer = RegisterSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)

    user = User.objects.create_user(
        username=serializer.validated_data["username"],
        password=serializer.validated_data["password"],
        email=serializer.validated_data.get("email", ""),
    )
    UserProfile.objects.create(user=user)
    token, _ = Token.objects.get_or_create(user=user)

    return Response(
        {"token": token.key, "user": UserSerializer(user).data},
        status=status.HTTP_201_CREATED,
    )


@api_view(["POST"])
@permission_classes([AllowAny])
def login_view(request):
    serializer = LoginSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)

    user = authenticate(
        username=serializer.validated_data["username"],
        password=serializer.validated_data["password"],
    )

    if user is None:
        return Response(
            {"error": "Credenciais inválidas."},
            status=status.HTTP_401_UNAUTHORIZED,
        )

    token, _ = Token.objects.get_or_create(user=user)
    return Response({"token": token.key, "user": UserSerializer(user).data})


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def me_view(request):
    return Response(UserSerializer(request.user).data)


@api_view(["POST"])
@permission_classes([AllowAny])
def discord_auth_view(request):
    serializer = DiscordAuthSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)

    code = serializer.validated_data["code"]
    redirect_uri = request.data.get(
        "redirect_uri", os.environ.get("DISCORD_REDIRECT_URI", "")
    )

    # Exchange code for access token
    token_response = requests.post(
        f"{DISCORD_API_URL}/oauth2/token",
        data={
            "client_id": os.environ.get("DISCORD_CLIENT_ID"),
            "client_secret": os.environ.get("DISCORD_CLIENT_SECRET"),
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": redirect_uri,
        },
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )

    if token_response.status_code != 200:
        return Response(
            {"error": "Falha ao autenticar com Discord."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    access_token = token_response.json().get("access_token")

    # Fetch Discord user info
    user_response = requests.get(
        f"{DISCORD_API_URL}/users/@me",
        headers={"Authorization": f"Bearer {access_token}"},
    )

    if user_response.status_code != 200:
        return Response(
            {"error": "Falha ao buscar dados do Discord."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    discord_data = user_response.json()
    discord_id = discord_data["id"]
    discord_username = discord_data.get("username", "")
    avatar_hash = discord_data.get("avatar")
    avatar_url = (
        f"https://cdn.discordapp.com/avatars/{discord_id}/{avatar_hash}.png"
        if avatar_hash
        else None
    )

    # Find or create user
    try:
        profile = UserProfile.objects.get(discord_id=discord_id)
        user = profile.user
        # Update discord info
        profile.discord_username = discord_username
        if avatar_url:
            profile.avatar = avatar_url
        profile.save()
    except UserProfile.DoesNotExist:
        # Create new user with discord username
        username = f"discord_{discord_id}"
        user = User.objects.create_user(username=username)
        UserProfile.objects.create(
            user=user,
            discord_id=discord_id,
            discord_username=discord_username,
            avatar=avatar_url,
        )

    token, _ = Token.objects.get_or_create(user=user)
    return Response({"token": token.key, "user": UserSerializer(user).data})


# ─── Favorites ────────────────────────────────────────────────


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def favorite_view(request, manhwa_id):
    from brscans.manhwa.models import Manhwa

    try:
        manhwa = Manhwa.objects.get(id=manhwa_id)
    except Manhwa.DoesNotExist:
        return Response(
            {"error": "Mangá não encontrado."}, status=status.HTTP_404_NOT_FOUND
        )

    _, created = Favorite.objects.get_or_create(
        user=request.user, manhwa=manhwa
    )
    if not created:
        return Response(
            {"message": "Já favoritado."}, status=status.HTTP_200_OK
        )

    return Response({"message": "Favoritado!"}, status=status.HTTP_201_CREATED)


@api_view(["DELETE"])
@permission_classes([IsAuthenticated])
def unfavorite_view(request, manhwa_id):
    deleted, _ = Favorite.objects.filter(
        user=request.user, manhwa_id=manhwa_id
    ).delete()

    if not deleted:
        return Response(
            {"error": "Não estava favoritado."},
            status=status.HTTP_404_NOT_FOUND,
        )

    return Response(status=status.HTTP_204_NO_CONTENT)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def favorites_list_view(request):
    favorites = Favorite.objects.filter(user=request.user).select_related(
        "manhwa__thumbnail"
    )
    manhwas = [f.manhwa for f in favorites]
    return Response(ManhwaSerializer(manhwas, many=True).data)


@api_view(["GET"])
@permission_classes([AllowAny])
def is_favorited_view(request, manhwa_id):
    if not request.user.is_authenticated:
        return Response({"is_favorited": False})

    is_fav = Favorite.objects.filter(
        user=request.user, manhwa_id=manhwa_id
    ).exists()
    return Response({"is_favorited": is_fav})
