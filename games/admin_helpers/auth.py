"""Admin login: username + password only (Spanish labels)."""

from django import forms
from django.contrib.admin.forms import AdminAuthenticationForm
from django.utils.translation import gettext_lazy as _


class UsernameAdminAuthenticationForm(AdminAuthenticationForm):
    """Staff login by username; email is not used or requested."""

    def __init__(self, request=None, *args, **kwargs):
        super().__init__(request, *args, **kwargs)
        self.fields["username"].label = _("Usuario")
        self.fields["username"].help_text = _(
            "Nombre de usuario (p. ej. ADMIN_USER), no el correo electrónico."
        )
        self.fields["username"].widget = forms.TextInput(
            attrs={
                "autofocus": True,
                "autocomplete": "username",
                "maxlength": self.fields["username"].max_length,
            }
        )
