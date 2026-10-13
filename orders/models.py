"""Buyurtma va chipta modellari."""
import uuid

from django.conf import settings
from django.core.signing import BadSignature, SignatureExpired, TimestampSigner
from django.db import models, transaction
from django.urls import reverse
from django.utils import timezone

from events.models import Event, TicketType


class Order(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Kutilmoqda"
        PAID = "paid", "To'langan"
        FAILED = "failed", "To'lov muvaffaqiyatsiz"
        CANCELLED = "cancelled", "Bekor qilingan"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
        related_name="orders", verbose_name="Mijoz",
    )
    event = models.ForeignKey(
        Event, on_delete=models.PROTECT, related_name="orders", verbose_name="Tadbir"
    )
    status = models.CharField(
        "Holat", max_length=20, choices=Status.choices, default=Status.PENDING
    )
    total_amount = models.DecimalField("Jami summa (so'm)", max_digits=14, decimal_places=2, default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    paid_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "Buyurtma"
        verbose_name_plural = "Buyurtmalar"
        ordering = ["-created_at"]

    def __str__(self):
        return f"#{self.pk} — {self.user.username} — {self.event.title}"

    def get_absolute_url(self):
        return reverse("payment", kwargs={"pk": self.pk})

    def recalc_total(self):
        """Jami summa faqat serverda hisoblanadi."""
        self.total_amount = sum(
            (item.unit_price * item.quantity for item in self.items.all()),
            start=0,
        )
        return self.total_amount


class OrderItem(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="items")
    ticket_type = models.ForeignKey(
        TicketType, on_delete=models.PROTECT, verbose_name="Chipta turi"
    )
    quantity = models.PositiveIntegerField("Miqdor")
    unit_price = models.DecimalField("Bir dona narxi", max_digits=12, decimal_places=2)

    class Meta:
        verbose_name = "Buyurtma qatori"
        verbose_name_plural = "Buyurtma qatorlari"

    @property
    def subtotal(self):
        return self.unit_price * self.quantity

    def __str__(self):
        return f"{self.ticket_type.name} x{self.quantity}"


def make_signer():
    return TimestampSigner(salt=settings.QR_SIGN_SALT)


def generate_ticket_token(ticket_uuid: str) -> str:
    """Imzolangan QR token — taxmin qilib bo'lmaydigan UUID + HMAC imzo."""
    return make_signer().sign(str(ticket_uuid))


def verify_ticket_token(token: str, max_age_seconds: int = 60 * 60 * 24 * 365 * 10):
    """Tokenni tekshirish. Noto'g'ri imzo bo'lsa None qaytaradi."""
    try:
        value = make_signer().unsign(token, max_age=max_age_seconds)
    except (BadSignature, SignatureExpired):
        return None
    try:
        return uuid.UUID(value)
    except (ValueError, AttributeError, TypeError):
        return None


class Ticket(models.Model):
    class Status(models.TextChoices):
        VALID = "valid", "Amaldagi"
        USED = "used", "Ishlatilgan"
        CANCELLED = "cancelled", "Bekor qilingan"

    order = models.ForeignKey(
        Order, on_delete=models.CASCADE, related_name="tickets", verbose_name="Buyurtma"
    )
    ticket_type = models.ForeignKey(
        TicketType, on_delete=models.PROTECT, verbose_name="Chipta turi"
    )
    event = models.ForeignKey(
        Event, on_delete=models.PROTECT, related_name="tickets", verbose_name="Tadbir"
    )
    # Taxmin qilib bo'lmaydigan identifikator (UUID4 = 122 bit tasodifiylik)
    uid = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    serial = models.CharField("Seriya raqami", max_length=20, blank=True)
    status = models.CharField(
        "Holat", max_length=20, choices=Status.choices, default=Status.VALID
    )
    created_at = models.DateTimeField(auto_now_add=True)
    used_at = models.DateTimeField(null=True, blank=True)
    used_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True,
        on_delete=models.SET_NULL, related_name="scanned_tickets",
        verbose_name="Tekshirgan nazoratchi",
    )

    class Meta:
        verbose_name = "Chipta"
        verbose_name_plural = "Chiptalar"
        ordering = ["pk"]

    def __str__(self):
        return f"{self.event.title} — {self.serial or self.uid}"

    @property
    def qr_token(self) -> str:
        return generate_ticket_token(self.uid)

    def save(self, *args, **kwargs):
        if not self.serial:
            self.serial = f"{self.event_id:05d}-{self.pk or 0:06d}"
        super().save(*args, **kwargs)


def create_tickets_for_order(order: Order) -> list[Ticket]:
    """To'lov tasdiqlanganda chiptalarni yaratish.

    Idempotent: agar buyurtma allaqachon to'langan va chiptalari bo'lsa,
    yangi chiptalar yaratilmaydi (takroriy to'lov so'rovi xavfsiz).
    """
    with transaction.atomic():
        locked = Order.objects.select_for_update().get(pk=order.pk)
        if locked.status == Order.Status.PAID and locked.tickets.exists():
            return list(locked.tickets.all())
        if locked.status == Order.Status.PAID:
            # Allaqachon to'langan, lekin chiptalar yo'q — yaratamiz
            pass
        tickets = []
        for item in locked.items.select_related("ticket_type"):
            for _ in range(item.quantity):
                t = Ticket(
                    order=locked,
                    ticket_type=item.ticket_type,
                    event=locked.event,
                )
                t.save()
                t.serial = f"{t.event_id:05d}-{t.pk:06d}"
                t.save(update_fields=["serial"])
                tickets.append(t)
        locked.status = Order.Status.PAID
        locked.paid_at = timezone.now()
        locked.save(update_fields=["status", "paid_at"])
        return tickets


def release_reservation(order: Order):
    """To'lov muvaffaqiyatsiz bo'lsa, band qilingan o'rinlarni qaytarish."""
    with transaction.atomic():
        locked = Order.objects.select_for_update().get(pk=order.pk)
        if locked.status != Order.Status.PENDING:
            return locked
        for item in locked.items.select_for_update().select_related("ticket_type"):
            tt = item.ticket_type
            tt.sold = max(tt.sold - item.quantity, 0)
            tt.save(update_fields=["sold"])
        locked.status = Order.Status.FAILED
        locked.save(update_fields=["status"])
        return locked
