from django.contrib import admin

from .models import (Buchung, BuchungRevision, BordkasseKonfig, CrewMember, ShoppingItem, StandardArtikel,
                     StandardKategorie, Toern)


@admin.register(BordkasseKonfig)
class BordkasseKonfigAdmin(admin.ModelAdmin):
    list_display = ('__str__', 'authentifizierung_erforderlich')

    def has_add_permission(self, request):
        return not BordkasseKonfig.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False


class StandardArtikelInline(admin.TabularInline):
    model = StandardArtikel
    extra = 3
    fields = ('name', 'position')


@admin.register(StandardKategorie)
class StandardKategorieAdmin(admin.ModelAdmin):
    list_display  = ('name', 'position', 'artikel_anzahl')
    list_editable = ('position',)
    search_fields = ('name', 'artikel__name')
    inlines = [StandardArtikelInline]

    @admin.display(description='Artikel')
    def artikel_anzahl(self, obj):
        return obj.artikel.count()


class CrewInline(admin.TabularInline):
    model = CrewMember
    extra = 0


@admin.register(Toern)
class ToernAdmin(admin.ModelAdmin):
    list_display  = ('name', 'slug', 'created_by', 'created_at', 'last_activity')
    search_fields = ('name',)
    prepopulated_fields = {'slug': ('name',)}
    inlines = [CrewInline]


class RevisionInline(admin.TabularInline):
    model = BuchungRevision
    extra = 0
    readonly_fields = ('changed_at', 'changed_by', 'kind', 'person', 'amount', 'method', 'note')
    can_delete = False


@admin.register(Buchung)
class BuchungAdmin(admin.ModelAdmin):
    list_display  = ('created_at', 'toern', 'kind', 'person', 'amount', 'method', 'note', 'deleted')
    list_filter   = ('toern', 'kind', 'method', 'deleted')
    search_fields = ('note', 'person__name')
    inlines = [RevisionInline]


@admin.register(ShoppingItem)
class ShoppingItemAdmin(admin.ModelAdmin):
    list_display  = ('text', 'toern', 'qty', 'info', 'done', 'created_at')
    list_filter   = ('toern', 'done')
    search_fields = ('text',)
