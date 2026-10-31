import json

from django.core.management.base import BaseCommand, CommandError

from leisure.importer import import_events_json


class Command(BaseCommand):
    help = 'Importiert Venues, Artists und Upcoming Events aus einer JSON-Datei (Format: leisure.importer).'

    def add_arguments(self, parser):
        parser.add_argument('file', help='Pfad zur JSON-Datei')
        parser.add_argument('--dry-run', action='store_true', help='Nur prüfen, nichts speichern')

    def handle(self, *args, **options):
        try:
            with open(options['file'], encoding='utf-8') as f:
                data = json.load(f)
        except (OSError, ValueError) as exc:
            raise CommandError(f'Datei nicht lesbar: {exc}')

        report = import_events_json(data, dry_run=options['dry_run'])
        for key in ('created', 'updated', 'unchanged'):
            for kind, names in report[key].items():
                for name in names:
                    self.stdout.write(f'{key:9} {kind:9} {name}')
        if report['errors']:
            for error in report['errors']:
                self.stderr.write(self.style.ERROR(error))
            raise CommandError(f'{len(report["errors"])} Fehler — nichts gespeichert.')
        self.stdout.write(self.style.SUCCESS('Dry-Run ok, nichts gespeichert.' if options['dry_run'] else 'Import fertig.'))
