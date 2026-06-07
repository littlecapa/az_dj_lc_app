from django.contrib import admin
from .models import Rezept, Tag


@admin.register(Tag)
class TagAdmin(admin.ModelAdmin):
    search_fields = ('name',)


@admin.register(Rezept)
class RezeptAdmin(admin.ModelAdmin):
    list_display  = ('name', 'kategorie', 'aufwand', 'liebling', 'erstellt')
    list_filter   = ('kategorie', 'aufwand', 'liebling', 'tags')
    search_fields = ('name', 'zutaten', 'quelle', 'notiz')
    list_editable = ('liebling',)
    ordering      = ('name',)
    filter_horizontal = ('tags',)

    def save_model(self, request, obj, form, change):
        if not obj.pk:
            obj.user = request.user
        super().save_model(request, obj, form, change)

    fieldsets     = (
        (None, {'fields': ('name', 'kategorie', 'aufwand', 'quelle', 'link', 'liebling', 'tags')}),
        ('Zutaten & Zubereitung', {'fields': ('zutaten', 'notiz')}),
        ('Foto', {'fields': ('foto_url', 'foto'), 'classes': ('collapse',)}),
    )
