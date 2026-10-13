from django.contrib import admin

from .models import Event, TicketType


class TicketTypeInline(admin.TabularInline):
    model = TicketType
    extra = 1


@admin.register(Event)
class EventAdmin(admin.ModelAdmin):
    list_display = ("title", "category", "date", "time", "status", "organizer")
    list_filter = ("status", "category", "date")
    search_fields = ("title", "address")
    inlines = [TicketTypeInline]
    filter_horizontal = ("controllers",)


@admin.register(TicketType)
class TicketTypeAdmin(admin.ModelAdmin):
    list_display = ("event", "name", "price", "capacity", "sold")
    list_filter = ("event",)
