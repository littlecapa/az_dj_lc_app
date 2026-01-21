from django.contrib import admin
from .models import ContactMessage

@admin.register(ContactMessage)
class ContactMessageAdmin(admin.ModelAdmin):
    list_display = ('created_at', 'name', 'email', 'is_read') # Übersichtstabelle
    list_filter = ('is_read', 'created_at') # Filter rechts
    search_fields = ('name', 'email', 'message') # Suchleiste oben
    readonly_fields = ('created_at',) # Datum nicht änderbar machen
