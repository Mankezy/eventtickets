"""Tadbir va chipta turi formalari."""
from django import forms

from .models import Event, TicketType


class EventForm(forms.ModelForm):
    class Meta:
        model = Event
        fields = ["title", "image", "description", "category", "address", "date", "time", "status", "controllers"]
        widgets = {
            "date": forms.DateInput(attrs={"type": "date"}),
            "time": forms.TimeInput(attrs={"type": "time"}),
            "description": forms.Textarea(attrs={"rows": 5}),
            "controllers": forms.CheckboxSelectMultiple,
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Nazoratchilar ro'yxati
        from accounts.models import User
        self.fields["controllers"].queryset = User.objects.filter(role=User.Role.CONTROLLER)
        for name, field in self.fields.items():
            if not isinstance(field.widget, forms.CheckboxSelectMultiple):
                field.widget.attrs.setdefault("class", "form-control")

    def clean(self):
        cleaned = super().clean()
        date = cleaned.get("date")
        if date and self.instance.pk is None:
            from django.utils import timezone
            if date < timezone.localdate():
                self.add_error("date", "Sana bugundan ertaga bo'lishi kerak.")
        return cleaned


class TicketTypeForm(forms.ModelForm):
    class Meta:
        model = TicketType
        fields = ["name", "price", "capacity"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name, field in self.fields.items():
            field.widget.attrs.setdefault("class", "form-control")
