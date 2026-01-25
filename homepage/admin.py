from django.contrib import admin
from .models import ContactMessage, HistChessMagazine, BlogPost

@admin.register(ContactMessage)
class ContactMessageAdmin(admin.ModelAdmin):
    list_display = ('created_at', 'name', 'email', 'is_read') # Übersichtstabelle
    list_filter = ('is_read', 'created_at') # Filter rechts
    search_fields = ('name', 'email', 'message') # Suchleiste oben
    readonly_fields = ('created_at',) # Datum nicht änderbar machen

@admin.register(HistChessMagazine)
class HistChessMagazineAdmin(admin.ModelAdmin):
    list_display = ('language', 'name') # Übersichtstabelle
    list_filter = ('is_active', 'language') # Filter rechts
    search_fields = ('name', 'language') # Suchleiste oben

@admin.register(BlogPost)
class BlogPostAdmin(admin.ModelAdmin):
    list_display = ('date', 'headline') # Übersichtstabelle
    list_filter = ('date', 'headline','is_active') # Filter rechts
    search_fields = ('date', 'headline') # Suchleiste oben
