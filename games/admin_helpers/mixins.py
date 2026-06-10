from django.contrib import admin, messages
from django.core.exceptions import ValidationError


class GuardedDeleteMixin:
    """Call check_delete(obj) before admin delete; show Spanish error via messages."""

    def check_delete(self, obj):
        raise NotImplementedError

    def has_delete_permission(self, request, obj=None):
        if obj is not None:
            try:
                self.check_delete(obj)
            except ValidationError:
                return False
        return super().has_delete_permission(request, obj)

    def delete_model(self, request, obj):
        try:
            self.check_delete(obj)
        except ValidationError as exc:
            self.message_user(request, exc.messages[0], messages.ERROR)
            return
        super().delete_model(request, obj)

    def delete_queryset(self, request, queryset):
        blocked = []
        for obj in queryset:
            try:
                self.check_delete(obj)
            except ValidationError as exc:
                blocked.append(str(exc.messages[0]))
        if blocked:
            self.message_user(request, blocked[0], messages.ERROR)
            return
        super().delete_queryset(request, queryset)
