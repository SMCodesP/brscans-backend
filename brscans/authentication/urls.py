from django.urls import path

from brscans.authentication.views import (
    discord_auth_view,
    favorite_view,
    favorites_list_view,
    is_favorited_view,
    login_view,
    me_view,
    register_view,
    unfavorite_view,
)

urlpatterns = [
    path("auth/register/", register_view, name="register"),
    path("auth/login/", login_view, name="login"),
    path("auth/me/", me_view, name="me"),
    path("auth/discord/", discord_auth_view, name="discord-auth"),
    path("manhwas/<int:manhwa_id>/favorite/", favorite_view, name="favorite"),
    path(
        "manhwas/<int:manhwa_id>/unfavorite/",
        unfavorite_view,
        name="unfavorite",
    ),
    path(
        "manhwas/<int:manhwa_id>/is-favorited/",
        is_favorited_view,
        name="is-favorited",
    ),
    path("favorites/", favorites_list_view, name="favorites-list"),
]
