"""QR nazorat: skanerlash sahifasi va atomar tekshirish endpoint'i."""
import json

from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, render
from django.utils import timezone
from django.views.decorators.csrf import csrf_protect
from django.views.decorators.http import require_POST

from accounts.decorators import controller_required
from events.models import Event
from orders.models import Order, Ticket, verify_ticket_token

from .models import ScanLog


@controller_required
def scan_page(request, event_pk=None):
    """Kamera orqali yoki qo'lda kod kiritib tekshirish sahifasi."""
    user = request.user
    if user.is_admin_role:
        my_events = Event.objects.all()
    else:
        my_events = user.assigned_events.all()
    selected = None
    if event_pk:
        selected = get_object_or_404(my_events, pk=event_pk)
    elif my_events.count() == 1:
        selected = my_events.first()
    return render(request, "checkin/scan.html", {
        "events": my_events.order_by("date"),
        "selected_event": selected,
        "logs": (
            ScanLog.objects.filter(event=selected).select_related("ticket", "controller")[:15]
            if selected else []
        ),
    })


@controller_required
@require_POST
@csrf_protect
def verify(request, event_pk):
    """Chiptani tekshirish va 'ishlatildi' belgilash — BITTA atomar operatsiya.

    Ikkita nazoratchi bir vaqtda skanerlasa, select_for_update tufayli
    faqat bittasiga kirish tasdiqlanadi. Server javob bermasa, mijoz
    tomonida hech qachon 'tasdiqlandi' ko'rsatilmaydi (fetch xatosi).
    """
    event = get_object_or_404(Event, pk=event_pk)
    user = request.user
    # Nazoratchi faqat o'ziga biriktirilgan tadbirlarda ishlay oladi
    if not user.is_admin_role and not event.controllers.filter(pk=user.pk).exists():
        return JsonResponse(
            {"result": "forbidden", "message": "Siz bu tadbirga biriktirilmagansiz."},
            status=403,
        )

    if request.content_type == "application/json":
        try:
            body = json.loads(request.body.decode() or "{}")
        except json.JSONDecodeError:
            body = {}
        code = (body.get("code") or "").strip()
    else:
        code = (request.POST.get("code") or "").strip()

    result, message, extra = _verify_and_mark(code, event, user)
    payload = {"result": result, "message": message, **extra}

    if request.content_type == "application/json":
        return JsonResponse(payload)
    # Forma orqali (qo'lda kiritish, JS o'chiq) — sahifaga qaytarish
    from django.contrib import messages as dj_messages

    dj_messages.info(request, message)
    return render(request, "checkin/scan.html", {
        "events": user.assigned_events.all() if not user.is_admin_role else Event.objects.all(),
        "selected_event": event,
        "last_result": payload,
        "logs": ScanLog.objects.filter(event=event).select_related("ticket", "controller")[:15],
    })


def _verify_and_mark(code: str, event: Event, controller):
    """Atomar tekshirish + belgilash + ScanLog. (result, message, extra) qaytaradi."""

    def log(result, ticket=None, raw=None):
        ScanLog.objects.create(
            controller=controller, event=event, ticket=ticket,
            raw_code=(raw or code)[:500], result=result,
        )

    if not code:
        log(ScanLog.Result.NOT_FOUND)
        return "not_found", "Kod kiritilmadi.", {}

    ticket_uid = verify_ticket_token(code)
    if ticket_uid is None:
        log(ScanLog.Result.BAD_SIGNATURE)
        return "bad_signature", "QR kod yaroqsiz yoki imzosi noto'g'ri.", {}

    with transaction.atomic():
        ticket = (
            Ticket.objects.select_for_update()
            .select_related("order", "ticket_type")
            .filter(uid=ticket_uid)
            .first()
        )
        if ticket is None:
            log(ScanLog.Result.NOT_FOUND)
            return "not_found", "Bunday chipta tizimda topilmadi.", {}

        info = {
            "serial": ticket.serial,
            "event_title": ticket.event.title,
            "ticket_type": ticket.ticket_type.name,
            "holder": ticket.order.user.get_full_name() or ticket.order.user.username,
        }

        if ticket.event_id != event.id:
            log(ScanLog.Result.WRONG_EVENT, ticket)
            return (
                "wrong_event",
                f"Bu chipta boshqa tadbirga tegishli: {ticket.event.title}",
                info,
            )
        if ticket.status == Ticket.Status.CANCELLED or ticket.event.status == Event.Status.CANCELLED:
            log(ScanLog.Result.CANCELLED, ticket)
            return "cancelled", "Chipta yoki tadbir bekor qilingan.", info
        if ticket.order.status != Order.Status.PAID:
            log(ScanLog.Result.WRONG_ORDER, ticket)
            return "wrong_order", "Buyurtma to'lanmagan.", info
        if ticket.status == Ticket.Status.USED:
            log(ScanLog.Result.ALREADY_USED, ticket)
            used_local = timezone.localtime(ticket.used_at) if ticket.used_at else None
            info["used_at"] = used_local.strftime("%d.%m.%Y %H:%M") if used_local else ""
            info["used_by"] = ticket.used_by.username if ticket.used_by else ""
            return "already_used", "Diqqat: chipta oldin ishlatilgan!", info

        # Yagona haqiqiy kirish — atomar belgilash
        ticket.status = Ticket.Status.USED
        ticket.used_at = timezone.now()
        ticket.used_by = controller
        ticket.save(update_fields=["status", "used_at", "used_by"])
        log(ScanLog.Result.OK, ticket)
        return "ok", "Chipta haqiqiy — kirishga ruxsat berildi!", info
