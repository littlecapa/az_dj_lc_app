"""
Django Management Command: change_isin

Zieht ein Asset auf eine neue ISIN um (z.B. nach einem 1:1-Umtausch in neue
Aktien): legt es unter der neuen ISIN an, hängt Holdings, Kurshistorie,
Watchlist-Einträge, Alarme usw. um und löscht das alte Asset. Anschließend
werden WKN, Symbol, Yahoo-Symbol und Kurs für die neue ISIN neu ermittelt.

Aufruf:
python manage.py change_isin DE000PFSE212 DE000PFSE253 --dry-run
python manage.py change_isin DE000PFSE212 DE000PFSE253
python manage.py change_isin DE000PFSE212 DE000PFSE253 --skip-attributes

Dieselbe Funktion gibt es als Seite unter /fintech/isin-change/.
"""

from django.core.management.base import BaseCommand, CommandError

from fintech.isin_change import (
    MANUAL, IsinChangeError, change_isin, needs_manual_review, refresh_attributes,
)


class Command(BaseCommand):
    help = "Zieht ein Asset samt aller abhängigen Daten auf eine neue ISIN um"

    def add_arguments(self, parser):
        parser.add_argument("old_isin", help="Bisherige ISIN des Assets")
        parser.add_argument("new_isin", help="Neue ISIN")
        parser.add_argument(
            "--dry-run", action="store_true",
            help="Alles durchspielen und zurückrollen — es wird nichts gespeichert",
        )
        parser.add_argument(
            "--skip-attributes", action="store_true",
            help="WKN/Symbol/Yahoo-Symbol/Kurs nicht neu ermitteln (keine externen Abfragen)",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        try:
            result = change_isin(options["old_isin"], options["new_isin"], dry_run=dry_run)
        except IsinChangeError as exc:
            raise CommandError(str(exc))

        prefix = "[Dry-Run] " if dry_run else ""
        verb = "würde umgezogen" if dry_run else "umgezogen"
        self.stdout.write(self.style.SUCCESS(
            f"{prefix}{result.name}: {result.old_isin} → {result.new_isin} {verb}"
        ))
        for row in result.moved:
            self.stdout.write(f"  {row['count']:>6}  {row['label']}")
        self.stdout.write(f"  {result.total_moved:>6}  Zeilen insgesamt")

        if options["skip_attributes"]:
            return

        attributes = refresh_attributes(result.old_isin, result.new_isin, dry_run=dry_run)
        self.stdout.write("")
        self.stdout.write(f"{prefix}Attribute:")
        for a in attributes:
            line = f"  {a.label}: {a.old or '–'} → {a.new or '–'}  ({a.note})"
            self.stdout.write(self.style.WARNING(line) if a.status == MANUAL else line)
        if needs_manual_review(attributes):
            self.stdout.write(self.style.WARNING(
                f"Bitte im Admin prüfen: /admin/fintech/asset/{result.new_isin}/change/"
            ))
