from django.contrib import admin

from . import sender_intel
from .models import PendingContact


@admin.register(PendingContact)
class PendingContactAdmin(admin.ModelAdmin):
    list_display = ("created_at", "name", "email", "subject", "submitted_ip", "status")
    list_filter = ("delivered_at", "verified_at")
    search_fields = ("name", "email", "subject", "message", "submitted_ip", "verified_ip")
    readonly_fields = [f.name for f in PendingContact._meta.fields] + ["sender_report"]
    ordering = ("-created_at",)

    @admin.display(description="Sender report")
    def sender_report(self, obj):
        # Offline read of what was captured; no network lookups from the admin.
        return sender_intel.format_report(sender_intel.build_report(obj, lookups={}))
