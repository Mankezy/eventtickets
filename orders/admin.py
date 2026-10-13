from django.contrib import admin

from .models import Order, OrderItem, Ticket


class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0
    readonly_fields = ("ticket_type", "quantity", "unit_price")


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "event", "status", "total_amount", "created_at")
    list_filter = ("status", "created_at")
    search_fields = ("user__username", "event__title")
    inlines = [OrderItemInline]


@admin.register(Ticket)
class TicketAdmin(admin.ModelAdmin):
    list_display = ("serial", "uid", "event", "ticket_type", "status", "used_at")
    list_filter = ("status", "event")
    search_fields = ("serial", "uid")
