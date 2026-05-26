from django.contrib.auth.models import AbstractUser
from django.db import models

from .managers import UserManager


class Role(models.TextChoices):
    RESIDENT = "resident", "Resident"
    FACULTY = "faculty", "Faculty"
    ADMIN = "admin", "Admin"


class User(AbstractUser):
    username = None
    email = models.EmailField(unique=True)
    role = models.CharField(max_length=16, choices=Role.choices, default=Role.RESIDENT)

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = []

    objects = UserManager()

    def __str__(self) -> str:
        return self.email
