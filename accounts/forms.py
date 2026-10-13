"""Registratsiya formasi."""
from django import forms
from django.contrib.auth.forms import UserCreationForm

from .models import User


class RegisterForm(UserCreationForm):
    ROLE_CHOICES = [
        ("client", "Mijoz"),
        ("organizer", "Tashkilotchi"),
        ("controller", "Nazoratchi"),
    ]

    role = forms.ChoiceField(
        label="Rol", choices=ROLE_CHOICES, initial="client", required=True
    )
    first_name = forms.CharField(label="Ism", max_length=150, required=True)
    last_name = forms.CharField(label="Familiya", max_length=150, required=True)
    phone = forms.CharField(label="Telefon", max_length=20, required=False)

    class Meta:
        model = User
        fields = ("username", "first_name", "last_name", "phone", "role")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name, field in self.fields.items():
            field.widget.attrs.setdefault("class", "form-control")
