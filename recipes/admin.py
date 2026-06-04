from django.contrib import admin
from .models import Rezept


@admin.register(Rezept)
class RezeptAdmin(admin.ModelAdmin):
    list_display  = ('name', 'kategorie', 'aufwand', 'saison', 'liebling', 'erstellt')
    list_filter   = ('kategorie', 'aufwand', 'saison', 'liebling')
    search_fields = ('name', 'zutaten', 'quelle', 'notiz')
    list_editable = ('liebling',)
    ordering      = ('name',)
