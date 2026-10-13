"""Tadbirlar, tashkilotchi paneli va admin boshqaruvi viewlari."""
from datetime import datetime

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.core.paginator import Paginator
from django.db.models import Count, Q, Sum
from django.http import HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from accounts.decorators import admin_required, organizer_required
from orders.models import Order, Ticket

from .forms import EventForm, TicketTypeForm
from .models import Event, TicketType

User = get_user_model()


# ---------------- Ommaviy sahifalar ----------------

def home(request):
    today = timezone.localdate()
    upcoming = (
        Event.objects.filter(status=Event.Status.ACTIVE, date__gte=today)
        .prefetch_related("ticket_types")
        .order_by("date", "time")[:6]
    )
    categories = Event.Category.choices
    return render(request, "home.html", {
        "events": upcoming,
        "categories": categories,
        "total_events": Event.objects.filter(status=Event.Status.ACTIVE).count(),
        "total_tickets": Ticket.objects.filter(status__in=["valid", "used"]).count(),
    })


def event_list(request):
    qs = (
        Event.objects.filter(status=Event.Status.ACTIVE)
        .prefetch_related("ticket_types")
        .order_by("date", "time")
    )
    q = request.GET.get("q", "").strip()
    category = request.GET.get("category", "").strip()
    date_str = request.GET.get("date", "").strip()

    if q:
        qs = qs.filter(Q(title__icontains=q) | Q(address__icontains=q) | Q(description__icontains=q))
    if category and category in dict(Event.Category.choices):
        qs = qs.filter(category=category)
    if date_str:
        try:
            d = datetime.strptime(date_str, "%Y-%m-%d").date()
            qs = qs.filter(date=d)
        except ValueError:
            pass

    paginator = Paginator(qs, 9)
    page_obj = paginator.get_page(request.GET.get("page"))
    return render(request, "events/event_list.html", {
        "page_obj": page_obj,
        "events": page_obj,
        "q": q,
        "category": category,
        "date": date_str,
        "categories": Event.Category.choices,
    })


def event_detail(request, slug):
    event = get_object_or_404(
        Event.objects.prefetch_related("ticket_types"), slug=slug
    )
    ticket_types = list(event.ticket_types.all())
    can_buy = event.is_on_sale and event.date >= timezone.localdate() and any(
        t.remaining > 0 for t in ticket_types
    )
    return render(request, "events/event_detail.html", {
        "event": event,
        "ticket_types": ticket_types,
        "can_buy": can_buy,
    })


# ---------------- Tashkilotchi paneli ----------------

@organizer_required
def organizer_dashboard(request):
    user = request.user
    events = Event.objects.filter(organizer=user).prefetch_related("ticket_types")
    if user.is_admin_role:
        events = Event.objects.all().prefetch_related("ticket_types")
    stats = []
    for e in events:
        stats.append({
            "event": e,
            "sold": e.total_sold,
            "capacity": e.total_capacity,
            "revenue": sum(
                (t.price * t.sold for t in e.ticket_types.all()), start=0
            ),
        })
    return render(request, "organizer/dashboard.html", {"stats": stats})


@organizer_required
def event_create(request):
    if request.method == "POST":
        form = EventForm(request.POST, request.FILES)
        if form.is_valid():
            event = form.save(commit=False)
            event.organizer = request.user
            event.save()
            form.save_m2m()
            messages.success(request, "Tadbir yaratildi. Endi chipta turlarini qo'shing.")
            return redirect("event_sales", pk=event.pk)
    else:
        form = EventForm()
    return render(request, "organizer/event_form.html", {"form": form, "editing": False})


@organizer_required
def event_update(request, pk):
    event = get_object_or_404(Event, pk=pk)
    if not (event.organizer == request.user or request.user.is_admin_role):
        return HttpResponseForbidden("Faqat o'z tadbiringizni tahrirlay olasiz.")
    if request.method == "POST":
        form = EventForm(request.POST, request.FILES, instance=event)
        if form.is_valid():
            form.save()
            messages.success(request, "Tadbir yangilandi.")
            return redirect("organizer_dashboard")
    else:
        form = EventForm(instance=event)
    return render(request, "organizer/event_form.html", {
        "form": form, "editing": True, "event": event,
    })


@organizer_required
def tickettype_create(request, event_pk):
    event = get_object_or_404(Event, pk=event_pk)
    if not (event.organizer == request.user or request.user.is_admin_role):
        return HttpResponseForbidden("Faqat o'z tadbiringiz uchun chipta qo'sha olasiz.")
    if request.method == "POST":
        form = TicketTypeForm(request.POST)
        if form.is_valid():
            tt = form.save(commit=False)
            tt.event = event
            tt.save()
            messages.success(request, f"'{tt.name}' chipta turi qo'shildi.")
            return redirect("event_sales", pk=event.pk)
    else:
        form = TicketTypeForm()
    return render(request, "organizer/tickettype_form.html", {
        "form": form, "event": event, "editing": False,
    })


@organizer_required
def tickettype_update(request, pk):
    tt = get_object_or_404(TicketType.objects.select_related("event"), pk=pk)
    event = tt.event
    if not (event.organizer == request.user or request.user.is_admin_role):
        return HttpResponseForbidden("Ruxsat yo'q.")
    if request.method == "POST":
        form = TicketTypeForm(request.POST, instance=tt)
        if form.is_valid():
            obj = form.save(commit=False)
            # Sotilgan sondan kam sig'im belgilashni oldini olish
            if obj.capacity < tt.sold:
                messages.error(request, f"Sig'im sotilgan sondan ({tt.sold}) kam bo'lolmaydi.")
            else:
                obj.save()
                messages.success(request, "Chipta turi yangilandi.")
                return redirect("event_sales", pk=event.pk)
    else:
        form = TicketTypeForm(instance=tt)
    return render(request, "organizer/tickettype_form.html", {
        "form": form, "event": event, "editing": True, "ticket_type": tt,
    })


@organizer_required
def event_sales(request, pk):
    """Sotuv natijalari: buyurtmalar, chiptalar, tushum."""
    event = get_object_or_404(Event.objects.prefetch_related("ticket_types"), pk=pk)
    if not (event.organizer == request.user or request.user.is_admin_role):
        return HttpResponseForbidden("Faqat o'z tadbiringiz sotuvini ko'ra olasiz.")
    orders = event.orders.select_related("user").order_by("-created_at")[:100]
    paid_orders = event.orders.filter(status=Order.Status.PAID)
    revenue = paid_orders.aggregate(s=Sum("total_amount"))["s"] or 0
    tickets_total = event.tickets.count()
    tickets_used = event.tickets.filter(status=Ticket.Status.USED).count()
    return render(request, "organizer/sales.html", {
        "event": event,
        "orders": orders,
        "revenue": revenue,
        "paid_count": paid_orders.count(),
        "tickets_total": tickets_total,
        "tickets_used": tickets_used,
    })


# ---------------- Administrator paneli ----------------

@admin_required
def admin_dashboard(request):
    tab = request.GET.get("tab", "events")
    events = Event.objects.select_related("organizer").order_by("-created_at")
    users = User.objects.order_by("-date_joined")
    orders = Order.objects.select_related("user", "event").order_by("-created_at")
    context = {
        "tab": tab,
        "events": Paginator(events, 20).get_page(request.GET.get("p_events")),
        "users": Paginator(users, 20).get_page(request.GET.get("p_users")),
        "orders": Paginator(orders, 20).get_page(request.GET.get("p_orders")),
        "stats": {
            "events": events.count(),
            "users": users.count(),
            "orders": orders.count(),
            "tickets": Ticket.objects.count(),
            "revenue": Order.objects.filter(status=Order.Status.PAID).aggregate(
                s=Sum("total_amount")
            )["s"] or 0,
        },
    }
    return render(request, "adminpanel/dashboard.html", context)


@admin_required
@require_POST
def admin_event_status(request, pk):
    event = get_object_or_404(Event, pk=pk)
    new_status = request.POST.get("status")
    if new_status in dict(Event.Status.choices):
        event.status = new_status
        event.save(update_fields=["status"])
        messages.success(request, f"'{event.title}' holati o'zgartirildi: {event.get_status_display()}.")
        # Bekor qilingan tadbir chiptalarini bekor qilish
        if new_status == Event.Status.CANCELLED:
            event.tickets.filter(status=Ticket.Status.VALID).update(
                status=Ticket.Status.CANCELLED
            )
    return redirect("admin_dashboard")


@admin_required
@require_POST
def admin_user_role(request, pk):
    user = get_object_or_404(User, pk=pk)
    new_role = request.POST.get("role")
    if new_role in dict(User.Role.choices):
        user.role = new_role
        user.save(update_fields=["role"])
        messages.success(request, f"{user.username} roli o'zgartirildi.")
    return redirect("admin_dashboard")
