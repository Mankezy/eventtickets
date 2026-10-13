"""Tadbir va chipta turlari modellari."""
from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models
from django.urls import reverse


class Event(models.Model):
    class Category(models.TextChoices):
        MUSIC = "music", "Musiqa"
        SPORT = "sport", "Sport"
        THEATER = "theater", "Teatr"
        CONFERENCE = "conference", "Konferensiya"
        FESTIVAL = "festival", "Festival"
        OTHER = "other", "Boshqa"

    class Status(models.TextChoices):
        ACTIVE = "active", "Faol"
        CANCELLED = "cancelled", "Bekor qilingan"
        FINISHED = "finished", "Yakunlangan"

    organizer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="events",
        verbose_name="Tashkilotchi",
    )
    controllers = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        blank=True,
        related_name="assigned_events",
        verbose_name="Nazoratchilar",
    )
    title = models.CharField("Nomi", max_length=200)
    slug = models.SlugField("Slug", max_length=220, unique=True, blank=True)
    image = models.ImageField("Rasm", upload_to="events/", blank=True, null=True)
    description = models.TextField("Tavsif", blank=True)
    category = models.CharField(
        "Kategoriya", max_length=20, choices=Category.choices, default=Category.OTHER
    )
    address = models.CharField("Manzil", max_length=300)
    date = models.DateField("Sana")
    time = models.TimeField("Vaqt", default="18:00")
    status = models.CharField(
        "Holat", max_length=20, choices=Status.choices, default=Status.ACTIVE
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Tadbir"
        verbose_name_plural = "Tadbirlar"
        ordering = ["date", "time"]
        indexes = [
            models.Index(fields=["category", "date"]),
            models.Index(fields=["status"]),
        ]

    def __str__(self):
        return self.title

    def save(self, *args, **kwargs):
        from django.utils.text import slugify

        if not self.slug:
            base = slugify(self.title) or f"event-{self.pk or 'yangi'}"
            slug = base
            n = 2
            while Event.objects.filter(slug=slug).exclude(pk=self.pk).exists():
                slug = f"{base}-{n}"
                n += 1
            self.slug = slug
        super().save(*args, **kwargs)

    def get_absolute_url(self):
        return reverse("event_detail", kwargs={"slug": self.slug})

    @property
    def is_on_sale(self):
        """Chipta sotish mumkinmi?"""
        return self.status == self.Status.ACTIVE

    @property
    def total_capacity(self):
        return sum(t.capacity for t in self.ticket_types.all())

    @property
    def total_sold(self):
        return sum(t.sold for t in self.ticket_types.all())

    @property
    def is_sold_out(self):
        types = list(self.ticket_types.all())
        return bool(types) and all(t.remaining == 0 for t in types)

    @property
    def min_price(self):
        prices = [t.price for t in self.ticket_types.all() if t.remaining > 0]
        return min(prices) if prices else None


class TicketType(models.Model):
    event = models.ForeignKey(
        Event, on_delete=models.CASCADE, related_name="ticket_types",
        verbose_name="Tadbir",
    )
    name = models.CharField("Nomi", max_length=100)  # masalan: Oddiy, VIP
    price = models.DecimalField(
        "Narx (so'm)", max_digits=12, decimal_places=2,
        validators=[MinValueValidator(0)],
    )
    capacity = models.PositiveIntegerField(
        "Sotuvga chiqarilgan son", validators=[MinValueValidator(1)]
    )
    sold = models.PositiveIntegerField("Sotilgan", default=0)

    class Meta:
        verbose_name = "Chipta turi"
        verbose_name_plural = "Chipta turlari"
        unique_together = ("event", "name")

    def __str__(self):
        return f"{self.event.title} — {self.name}"

    @property
    def remaining(self):
        return max(self.capacity - self.sold, 0)
