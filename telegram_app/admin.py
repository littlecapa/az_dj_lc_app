from django.contrib import admin
from .models import TelegramMessage


@admin.register(TelegramMessage)
class TelegramMessageAdmin(admin.ModelAdmin):
    list_display = ['sent_at', 'trigger', 'message_preview']
    list_filter = ['sent_at', 'trigger']
    search_fields = ['message', 'trigger']
    date_hierarchy = 'sent_at'

    def message_preview(self, obj):
        return obj.message if len(obj.message) <= 80 else obj.message[:80] + '…'
    message_preview.short_description = 'Nachricht'
