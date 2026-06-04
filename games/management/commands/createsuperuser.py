"""
Create superuser with username + password only (skip email prompt).

Stock User.REQUIRED_FIELDS includes email; this command clears it for the run.
"""

from django.contrib.auth.management.commands.createsuperuser import (
    Command as BaseCreateSuperuserCommand,
)


class Command(BaseCreateSuperuserCommand):
    def handle(self, *args, **options):
        required = list(self.UserModel.REQUIRED_FIELDS)
        self.UserModel.REQUIRED_FIELDS = []
        try:
            return super().handle(*args, **options)
        finally:
            self.UserModel.REQUIRED_FIELDS = required
