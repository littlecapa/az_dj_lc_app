import json

from django import forms
from django.contrib import admin, messages
from django.shortcuts import redirect
from django.template.response import TemplateResponse
from django.urls import path, reverse

from .importer import IMPORT_FORMAT, import_events_json
from .models import Artist, Location, UpcomingEvent


@admin.register(Location)
class LocationAdmin(admin.ModelAdmin):
    list_display = ('name', 'country', 'rating')
    list_editable = ('rating',)
    list_filter = ('country', 'rating')
    search_fields = ('name', 'country', 'info')


@admin.register(Artist)
class ArtistAdmin(admin.ModelAdmin):
    list_display = ('name', 'rating', 'song_url')
    list_editable = ('rating',)
    list_filter = ('rating',)
    search_fields = ('name', 'info')


class JsonImportForm(forms.Form):
    json_file = forms.FileField(label='JSON-Datei', required=False)
    json_text = forms.CharField(label='… oder JSON einfügen', required=False,
                                widget=forms.Textarea(attrs={'rows': 18, 'cols': 100, 'style': 'font-family: monospace'}))
    dry_run = forms.BooleanField(label='Nur prüfen (Dry-Run)', required=False, initial=True)

    def clean(self):
        cleaned = super().clean()
        raw = cleaned.get('json_file').read().decode('utf-8') if cleaned.get('json_file') else cleaned.get('json_text')
        if not raw or not raw.strip():
            raise forms.ValidationError('Bitte eine JSON-Datei hochladen oder JSON einfügen.')
        try:
            cleaned['data'] = json.loads(raw)
        except ValueError as exc:
            raise forms.ValidationError(f'Kein gültiges JSON: {exc}')
        return cleaned


@admin.register(UpcomingEvent)
class UpcomingEventAdmin(admin.ModelAdmin):
    list_display = ('date', 'artist', 'location', 'ticket_url')
    list_filter = ('location', 'artist')
    search_fields = ('artist__name', 'location__name', 'info')
    date_hierarchy = 'date'
    autocomplete_fields = ('location', 'artist')
    change_list_template = 'admin/events/upcomingevent/change_list.html'

    def get_urls(self):
        return [path('import/', self.admin_site.admin_view(self.import_view), name='events_import')] + super().get_urls()

    def import_view(self, request):
        if not self.has_add_permission(request):
            return redirect('admin:index')
        report = None
        form = JsonImportForm(request.POST or None, request.FILES or None)
        if request.method == 'POST' and form.is_valid():
            dry_run = form.cleaned_data['dry_run']
            report = import_events_json(form.cleaned_data['data'], dry_run=dry_run)
            if not report['errors'] and not dry_run:
                created = sum(len(v) for v in report['created'].values())
                updated = sum(len(v) for v in report['updated'].values())
                self.message_user(request, f'Import fertig: {created} neu, {updated} ergänzt.', messages.SUCCESS)
                return redirect(reverse('admin:events_upcomingevent_changelist'))
        context = {
            **self.admin_site.each_context(request),
            'title': 'Events aus JSON importieren',
            'opts': self.model._meta,
            'form': form,
            'report': report,
            'example': json.dumps(IMPORT_FORMAT['example'], ensure_ascii=False, indent=2),
        }
        return TemplateResponse(request, 'admin/events/import.html', context)
