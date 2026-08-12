from django.contrib import admin
from .models import ContactMessage, HistChessMagazine, BlogPost, QuickLink, ChessPosition

@admin.register(ContactMessage)
class ContactMessageAdmin(admin.ModelAdmin):
    list_display = ('created_at', 'name', 'email', 'is_read') # Übersichtstabelle
    list_filter = ('is_read', 'created_at') # Filter rechts
    search_fields = ('name', 'email', 'message') # Suchleiste oben
    readonly_fields = ('created_at',) # Datum nicht änderbar machen

@admin.register(HistChessMagazine)
class HistChessMagazineAdmin(admin.ModelAdmin):
    list_display = ('language', 'name', 'link', 'is_active') # Übersichtstabelle
    list_filter = ('is_active', 'language') # Filter rechts
    list_editable = ('is_active',)
    search_fields = ('name', 'language') # Suchleiste oben

@admin.register(BlogPost)
class BlogPostAdmin(admin.ModelAdmin):
    list_display = ('date', 'headline') # Übersichtstabelle
    list_filter = ('date', 'headline','is_active') # Filter rechts
    search_fields = ('date', 'headline') # Suchleiste oben

@admin.register(QuickLink)
class QuickLinkAdmin(admin.ModelAdmin):
    list_display  = ('category', 'prio', 'name', 'url', 'is_active')
    list_filter   = ('category', 'prio', 'is_active')
    search_fields = ('name', 'url')
    list_editable = ('prio', 'is_active')

@admin.register(ChessPosition)
class ChessPositionAdmin(admin.ModelAdmin):
    list_display  = ('fen', 'valid_moves_regex')
    search_fields = ('fen', 'valid_moves_regex')