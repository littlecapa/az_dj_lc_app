from django.contrib import admin

from .models import Buchung, BuchungRevision, CrewMember, ShoppingItem, Toern


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
