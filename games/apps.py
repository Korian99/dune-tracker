from django.apps import AppConfig


class GamesConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "games"

    def ready(self):
        from django.contrib import admin

        from games.admin_helpers.auth import UsernameAdminAuthenticationForm

        admin.site.login_form = UsernameAdminAuthenticationForm
