from django.contrib import admin

from .models import ScanLog


@admin.register(ScanLog)
class ScanLogAdmin(admin.ModelAdmin):
    list_display = ("created_at", "controller", "event", "ticket", "result")
    list_filter = ("result", "event", "created_at")
    search_fields = ("ticket__serial", "controller__username")
