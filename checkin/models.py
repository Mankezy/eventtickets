"""QR nazorat modellari."""
from django.conf import settings
from django.db import models

from orders.models import Ticket


class ScanLog(models.Model):
    class Result(models.TextChoices):
        OK = "ok", "Ruxsat berildi"
        ALREADY_USED = "already_used", "Oldin ishlatilgan"
        NOT_FOUND = "not_found", "Topilmadi"
        BAD_SIGNATURE = "bad_signature", "Imzo noto'g'ri"
        CANCELLED = "cancelled", "Bekor qilingan"
        WRONG_EVENT = "wrong_event", "Boshqa tadbir chiptasi"
        WRONG_ORDER = "wrong_order", "To'lanmagan buyurtma"

    controller = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
        related_name="scan_logs", verbose_name="Nazoratchi",
    )
    event = models.ForeignKey(
        "events.Event", null=True, blank=True, on_delete=models.SET_NULL,
        related_name="scan_logs", verbose_name="Tadbir",
    )
    ticket = models.ForeignKey(
        Ticket, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="scan_logs", verbose_name="Chipta",
    )
    raw_code = models.TextField("Skanerlangan kod", blank=True)
    result = models.CharField("Natija", max_length=20, choices=Result.choices)
    created_at = models.DateTimeField("Vaqt", auto_now_add=True)

    class Meta:
        verbose_name = "Skanerlash qaydi"
        verbose_name_plural = "Skanerlash qaydlari"
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["event", "-created_at"])]

    def __str__(self):
        return f"{self.created_at:%Y-%m-%d %H:%M} — {self.get_result_display()}"
