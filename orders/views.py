"""Buyurtma, demo to'lov, chiptalar va PDF."""
import io
from decimal import Decimal

import qrcode
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.http import FileResponse, Http404, HttpResponseForbidden, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST
from reportlab.lib.pagesizes import A5
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas

from events.models import Event, TicketType

from .models import (
    Order,
    OrderItem,
    Ticket,
    create_tickets_for_order,
    release_reservation,
)

MAX_PER_ORDER = 10


@login_required
@require_POST
def order_create(request, event_pk):
    """Buyurtma yaratish — narx va jami summa FAQAT serverda hisoblanadi."""
    event = get_object_or_404(Event, pk=event_pk)
    if not event.is_on_sale:
        messages.error(request, "Bu tadbirga chipta sotilmaydi (bekor qilingan yoki yakunlangan).")
        return redirect("event_detail", slug=event.slug)
    if event.date < timezone.localdate():
        messages.error(request, "Sana o'tib ketgan tadbirga chipta sotilmaydi.")
        return redirect("event_detail", slug=event.slug)

    try:
        tt = event.ticket_types.get(pk=request.POST.get("ticket_type"))
    except (TicketType.DoesNotExist, ValueError):
        messages.error(request, "Chipta turi tanlanmadi.")
        return redirect("event_detail", slug=event.slug)

    try:
        qty = int(request.POST.get("quantity", "0"))
    except (TypeError, ValueError):
        qty = 0
    if not 1 <= qty <= MAX_PER_ORDER:
        messages.error(request, f"Miqdor 1 dan {MAX_PER_ORDER} gacha bo'lishi kerak.")
        return redirect("event_detail", slug=event.slug)

    # Atomar band qilish: bir vaqtda bir nechta mijoz xarid qilganda
    # mavjud sondan ortiq chipta sotilmaydi.
    try:
        with transaction.atomic():
            locked_tt = TicketType.objects.select_for_update().get(pk=tt.pk)
            if locked_tt.remaining < qty:
                messages.error(
                    request,
                    f"'{locked_tt.name}' turidan faqat {locked_tt.remaining} ta qoldi.",
                )
                raise transaction.TransactionManagementError("capacity")
            order = Order.objects.create(
                user=request.user, event=event, status=Order.Status.PENDING
            )
            OrderItem.objects.create(
                order=order,
                ticket_type=locked_tt,
                quantity=qty,
                unit_price=locked_tt.price,  # narx serverdan, mijoz o'zgartira olmaydi
            )
            locked_tt.sold += qty
            locked_tt.save(update_fields=["sold"])
            order.recalc_total()
            order.save(update_fields=["total_amount"])
    except transaction.TransactionManagementError:
        return redirect("event_detail", slug=event.slug)

    return redirect("order_confirm", pk=order.pk)


@login_required
def order_confirm(request, pk):
    order = get_object_or_404(
        Order.objects.select_related("event").prefetch_related("items__ticket_type"),
        pk=pk,
    )
    if order.user != request.user and not request.user.is_admin_role:
        return HttpResponseForbidden("Bu buyurtma sizga tegishli emas.")
    return render(request, "orders/order_confirm.html", {
        "order": order,
        "items": order.items.select_related("ticket_type"),
    })


@login_required
@require_POST
def order_cancel(request, pk):
    order = get_object_or_404(Order, pk=pk, user=request.user)
    if order.status == Order.Status.PENDING:
        release_reservation(order)
        messages.info(request, "Buyurtma bekor qilindi.")
    return redirect("event_detail", slug=order.event.slug)


@login_required
def payment(request, pk):
    """DEMO TO'LOV sahifasi. Haqiqiy karta ma'lumoti so'ralmaydi."""
    order = get_object_or_404(Order, pk=pk, user=request.user)
    if order.status == Order.Status.PAID:
        return redirect("payment_result", pk=order.pk, result="paid")
    if order.status in (Order.Status.FAILED, Order.Status.CANCELLED):
        messages.error(request, "Bu buyurtma bekor qilingan. Yangi buyurtma yarating.")
        return redirect("event_detail", slug=order.event.slug)
    return render(request, "orders/payment.html", {
        "order": order,
        "items": order.items.select_related("ticket_type"),
    })


@login_required
@require_POST
def payment_process(request, pk):
    """Demo to'lov natijasini qayta ishlash.

    Idempotent: takroriy so'rov yangi chiptalar yaratmaydi.
    """
    order = get_object_or_404(Order, pk=pk, user=request.user)
    outcome = request.POST.get("outcome")  # success | failure

    with transaction.atomic():
        locked = Order.objects.select_for_update().get(pk=order.pk)
        if locked.status == Order.Status.PAID:
            # Takroriy to'lov so'rovi — chiptalar qayta yaratilmaydi
            messages.info(request, "Bu buyurtma allaqachon to'langan.")
            return redirect("payment_result", pk=locked.pk, result="paid")
        if locked.status != Order.Status.PENDING:
            messages.error(request, "Buyurtma holati to'lov uchun yaroqsiz.")
            return redirect("event_detail", slug=locked.event.slug)

        if outcome == "success":
            create_tickets_for_order(locked)
            return redirect("payment_result", pk=locked.pk, result="success")
        else:
            release_reservation(locked)
            return redirect("payment_result", pk=locked.pk, result="failure")


@login_required
def payment_result(request, pk, result):
    order = get_object_or_404(
        Order.objects.prefetch_related("tickets"), pk=pk, user=request.user
    )
    return render(request, "orders/payment_result.html", {
        "order": order, "result": result,
    })


@login_required
def my_tickets(request):
    tickets = (
        Ticket.objects.filter(order__user=request.user)
        .select_related("event", "ticket_type", "order")
        .order_by("-created_at")
    )
    return render(request, "orders/my_tickets.html", {"tickets": tickets})


def _get_ticket_for_user(request, pk):
    ticket = get_object_or_404(
        Ticket.objects.select_related("event", "ticket_type", "order__user"), pk=pk
    )
    user = request.user
    is_owner = user.is_authenticated and ticket.order.user_id == user.id
    is_staff = user.is_authenticated and (user.is_admin_role or user.is_superuser)
    is_event_organizer = user.is_authenticated and ticket.event.organizer_id == user.id
    if not (is_owner or is_staff or is_event_organizer):
        # Boshqa foydalanuvchining chiptasini ko'rib/yuklab bo'lmaydi
        raise Http404()
    return ticket


@login_required
def ticket_detail(request, pk):
    ticket = _get_ticket_for_user(request, pk)
    qr_data_uri = _qr_data_uri(ticket.qr_token)
    return render(request, "orders/ticket_detail.html", {
        "ticket": ticket, "qr_data_uri": qr_data_uri,
    })


@login_required
def ticket_pdf(request, pk):
    ticket = _get_ticket_for_user(request, pk)
    pdf_bytes = build_ticket_pdf(ticket)
    response = FileResponse(
        io.BytesIO(pdf_bytes), as_attachment=True,
        filename=f"chipta-{ticket.serial or ticket.uid}.pdf",
        content_type="application/pdf",
    )
    return response


def _qr_data_uri(data: str) -> str:
    import base64

    qr = qrcode.QRCode(border=2, box_size=8)
    qr.add_data(data)
    qr.make(fit=True)
    img = qr.make_image(fill_color="#2e1065", back_color="white")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    b64 = base64.b64encode(buf.getvalue()).decode()
    return f"data:image/png;base64,{b64}"


def build_ticket_pdf(ticket: Ticket) -> bytes:
    """Chipta PDF'i — A5 formatda, QR kod bilan (reportlab)."""
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A5)
    w, h = A5

    # Binafsha sarlavha bloki
    c.setFillColor("#5b21b6")
    c.rect(0, h - 40 * mm, w, 40 * mm, stroke=0, fill=1)
    c.setFillColor("#ffffff")
    c.setFont("Helvetica-Bold", 18)
    c.drawString(10 * mm, h - 18 * mm, "KIRISH CHIPTASI")
    c.setFont("Helvetica", 10)
    c.drawString(10 * mm, h - 26 * mm, "DEMO - bu sinov chiptasi")
    c.drawString(10 * mm, h - 33 * mm, f"Seriya: {ticket.serial}")

    # Tadbir ma'lumotlari (lotin shriftida xavfsiz belgilar)
    def safe(s):
        return (s or "").encode("cp1252", "replace").decode("cp1252")

    ev = ticket.event
    c.setFillColor("#1f2937")
    c.setFont("Helvetica-Bold", 15)
    c.drawString(10 * mm, h - 52 * mm, safe(ev.title)[:60])
    c.setFont("Helvetica", 11)
    rows = [
        f"Sana: {ev.date:%d.%m.%Y}  Vaqt: {ev.time:%H:%M}",
        f"Manzil: {safe(ev.address)[:70]}",
        f"Chipta turi: {safe(ticket.ticket_type.name)}",
        f"Egasi: {safe(ticket.order.user.get_full_name() or ticket.order.user.username)}",
        f"Holat: {'ISHLATILGAN' if ticket.status == Ticket.Status.USED else 'AMALDAGI'}",
    ]
    y = h - 60 * mm
    for row in rows:
        c.drawString(10 * mm, y, row)
        y -= 6.5 * mm

    # QR kod
    qr = qrcode.QRCode(border=1, box_size=10)
    qr.add_data(ticket.qr_token)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    qr_buf = io.BytesIO()
    img.save(qr_buf, format="PNG")
    qr_buf.seek(0)
    from reportlab.lib.utils import ImageReader

    c.drawImage(ImageReader(qr_buf), w - 55 * mm, h - 105 * mm, 45 * mm, 45 * mm)
    c.setFont("Helvetica", 7)
    c.setFillColor("#6b7280")
    c.drawString(10 * mm, 12 * mm, "QR kodni nazorat punktida skaner qildirib kiring.")
    c.drawString(10 * mm, 8 * mm, f"ID: {ticket.uid}")

    c.showPage()
    c.save()
    return buf.getvalue()
