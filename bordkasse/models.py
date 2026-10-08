import re
import unicodedata

from django.conf import settings
from django.db import models
from django.utils import timezone


def toern_slugify(name):
    """'Kroatien Süd 2026' → 'kroatien-sued-2026' (Umlaute ausgeschrieben, wie im Prototyp)."""
    s = (name or '').strip().lower()
    for a, b in (('ä', 'ae'), ('ö', 'oe'), ('ü', 'ue'), ('ß', 'ss')):
        s = s.replace(a, b)
    s = unicodedata.normalize('NFKD', s).encode('ascii', 'ignore').decode('ascii')
    s = re.sub(r'[^a-z0-9]+', '-', s).strip('-')
    return s[:60].strip('-')


class Toern(models.Model):
    name         = models.CharField(max_length=60, unique=True)
    slug         = models.SlugField(max_length=60, unique=True)
    created_at   = models.DateTimeField(auto_now_add=True)
    created_by   = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
                                     null=True, blank=True, related_name='+')
    last_activity = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ['-last_activity']
        verbose_name = 'Törn'
        verbose_name_plural = 'Törns'

    def __str__(self):
        return self.name

    def touch(self):
        self.last_activity = timezone.now()
        self.save(update_fields=['last_activity'])


class CrewMember(models.Model):
    """Crew pro Törn. Buchungen referenzieren die Person per FK, damit eine
    Umbenennung automatisch für Saldo und Historie gilt."""
    toern      = models.ForeignKey(Toern, on_delete=models.CASCADE, related_name='crew')
    name       = models.CharField(max_length=40)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at', 'id']
        constraints = [
            models.UniqueConstraint(fields=['toern', 'name'], name='bordkasse_crew_unique_name'),
        ]
        verbose_name = 'Crew-Mitglied'
        verbose_name_plural = 'Crew'

    def __str__(self):
        return self.name


class BuchungFields(models.Model):
    """Gemeinsame Felder von Buchung und ihren Revisionen (vorheriger Stand)."""
    AUSGABE    = 'ausgabe'
    EINZAHLUNG = 'einzahlung'
    KIND_CHOICES = [(AUSGABE, 'Ausgabe'), (EINZAHLUNG, 'Einzahlung')]

    KARTE = 'karte'
    BAR   = 'bar'
    METHOD_CHOICES = [(KARTE, 'Karte'), (BAR, 'Bar')]

    kind   = models.CharField(max_length=12, choices=KIND_CHOICES)
    # NULL bei einer Ausgabe = direkt aus der Bordkasse (Bargeld) bezahlt.
    person = models.ForeignKey(CrewMember, on_delete=models.PROTECT, null=True, blank=True,
                               related_name='+')
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    # Nur bei Ausgaben gesetzt; Ausgaben aus der Bordkasse sind immer 'bar'.
    method = models.CharField(max_length=8, choices=METHOD_CHOICES, blank=True)
    note   = models.CharField(max_length=80, blank=True)

    class Meta:
        abstract = True

    @property
    def from_kasse(self):
        return self.kind == self.AUSGABE and self.person_id is None


class Buchung(BuchungFields):
    toern      = models.ForeignKey(Toern, on_delete=models.CASCADE, related_name='buchungen')
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
                                   null=True, blank=True, related_name='+')
    updated_at = models.DateTimeField(null=True, blank=True)
    # Soft-Delete: Eintrag bleibt für die Historie erhalten.
    deleted    = models.BooleanField(default=False)
    deleted_at = models.DateTimeField(null=True, blank=True)
    deleted_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
                                   null=True, blank=True, related_name='+')

    class Meta:
        ordering = ['-created_at', '-id']
        verbose_name = 'Buchung'
        verbose_name_plural = 'Buchungen'

    def __str__(self):
        return f'{self.get_kind_display()} {self.amount} €'


class BuchungRevision(BuchungFields):
    """Stand einer Buchung *vor* einer Bearbeitung."""
    buchung    = models.ForeignKey(Buchung, on_delete=models.CASCADE, related_name='revisionen')
    changed_at = models.DateTimeField(auto_now_add=True)
    changed_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
                                   null=True, blank=True, related_name='+')

    class Meta:
        ordering = ['changed_at', 'id']
        verbose_name = 'Buchungs-Revision'
        verbose_name_plural = 'Buchungs-Revisionen'


class ShoppingItem(models.Model):
    toern      = models.ForeignKey(Toern, on_delete=models.CASCADE, related_name='einkaufsliste')
    text       = models.CharField(max_length=80)
    qty        = models.CharField(max_length=24, blank=True)
    info       = models.CharField(max_length=60, blank=True)
    done       = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at', '-id']
        verbose_name = 'Einkaufslisten-Eintrag'
        verbose_name_plural = 'Einkaufsliste'

    def __str__(self):
        return self.text


class BordkasseKonfig(models.Model):
    """Globale Einstellungen der Bordkasse — genau ein Datensatz, gepflegt im Django-Admin."""
    authentifizierung_erforderlich = models.BooleanField(
        'Authentifizierung erforderlich', default=False, db_column='Authentifizierung_erforderlich',
        help_text='Aktiv: Alle Seiten unter /bordkasse/ (auch Ansehen und Einkaufsliste) nur nach Login.',
    )

    class Meta:
        db_table = 'Bordkasse_Konfig'
        verbose_name = 'Bordkasse-Konfiguration'
        verbose_name_plural = 'Bordkasse-Konfiguration'

    def __str__(self):
        return 'Bordkasse-Konfiguration'

    @classmethod
    def load(cls):
        return cls.objects.order_by('pk').first() or cls.objects.create()


class StandardKategorie(models.Model):
    """Kategorie der Standard-Einkaufsliste für Segeltörns (z. B. Getränke)."""
    name     = models.CharField(max_length=40, unique=True)
    position = models.PositiveIntegerField(default=0, help_text='Reihenfolge, kleinere Zahl zuerst.')

    class Meta:
        ordering = ['position', 'name']
        verbose_name = 'Standardlisten-Kategorie'
        verbose_name_plural = 'Standardliste'

    def __str__(self):
        return self.name


class StandardArtikel(models.Model):
    """Artikel der Standardliste — reine Auswahlquelle; „Übernehmen“ legt einen ShoppingItem an."""
    kategorie = models.ForeignKey(StandardKategorie, on_delete=models.CASCADE, related_name='artikel')
    name      = models.CharField(max_length=80)
    position  = models.PositiveIntegerField(default=0, help_text='Reihenfolge, kleinere Zahl zuerst.')

    class Meta:
        ordering = ['position', 'name']
        constraints = [
            models.UniqueConstraint(fields=['kategorie', 'name'], name='bordkasse_standardartikel_unique'),
        ]
        verbose_name = 'Standardlisten-Artikel'
        verbose_name_plural = 'Standardlisten-Artikel'

    def __str__(self):
        return self.name
