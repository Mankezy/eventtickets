"""Foydalanuvchi modeli — rollar bilan."""
from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    class Role(models.TextChoices):
        CLIENT = "client", "Mijoz"
        ORGANIZER = "organizer", "Tashkilotchi"
        CONTROLLER = "controller", "Nazoratchi"
        ADMIN = "admin", "Administrator"

    role = models.CharField(
        "Rol", max_length=20, choices=Role.choices, default=Role.CLIENT
    )
    phone = models.CharField("Telefon", max_length=20, blank=True)

    class Meta:
        verbose_name = "Foydalanuvchi"
        verbose_name_plural = "Foydalanuvchilar"

    def __str__(self):
        return f"{self.username} ({self.get_role_display()})"

    # Rol tekshiruvlari (backendda ruxsatlar shular orqali nazorat qilinadi)
    @property
    def is_client(self):
        return self.role == self.Role.CLIENT

    @property
    def is_organizer(self):
        return self.role in (self.Role.ORGANIZER, self.Role.ADMIN) or self.is_superuser

    @property
    def is_controller(self):
        return self.role in (self.Role.CONTROLLER, self.Role.ADMIN) or self.is_superuser

    @property
    def is_admin_role(self):
        return self.role == self.Role.ADMIN or self.is_superuser
