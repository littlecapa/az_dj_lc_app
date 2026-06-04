"""
Excel / CSV Importer für Rezepte.

Erwartet Spalten (case-insensitive, Leerzeichen egal):
  Titel, Kategorie, Unterkategorie, Quelle, Fundstelle, Zutaten, Bemerkung, Bewertung

Felder ohne Entsprechung im Modell:
  Unterkategorie → wird an notiz angehängt
  Fundstelle     → wird als link gesetzt wenn URL, sonst ignoriert
  Bewertung      → ≥ 4 Sterne → liebling = True
"""

import logging
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)

# ── Kategorie-Mapping ──────────────────────────────────────────────────────
# Excel-Kategorie (lowercase) → App-Kategorie-Key
KATEGORIE_MAPPING: dict[str, str] = {
    'frühstück':      'fruehstueck',
    'fruehstueck':    'fruehstueck',
    'suppe':          'suppen',
    'suppen':         'suppen',
    'vegetarisch':    'vegetarisch',
    'vegi':           'vegetarisch',
    'fleisch':        'fleisch',
    'fisch':          'fleisch',
    'fleisch & fisch':'fleisch',
    'geflügel':       'fleisch',
    'geflugel':       'fleisch',
    'pasta':          'pasta',
    'pasta & reis':   'pasta',
    'reis':           'pasta',
    'nudeln':         'pasta',
    'kartoffeln':     'vegetarisch',   # ⚠️ ambiguous – im Protokoll als vegetarisch gewählt
    'backen':         'backen',
    'gebäck':         'backen',
    'gebaeck':        'backen',
    'kuchen':         'backen',
    'dessert':        'dessert',
    'desserts':       'dessert',
    'nachtisch':      'dessert',
    'snacks':         'snacks',
    'snacks & dips':  'snacks',
    'dips':           'snacks',
    'herzhaft':       'snacks',        # ⚠️ ambiguous – im Protokoll als snacks gewählt
    'getränke':       'getraenke',
    'getraenke':      'getraenke',
    'getränk':        'getraenke',
}

# ── Quelle-Mapping ────────────────────────────────────────────────────────
QUELLE_MAPPING: dict[str, str] = {
    'ck':         'Chefkoch',
    'chefkoch':   'Chefkoch',
    'ow':         'OneNote',
    'one note':   'OneNote',
    'onenote':    'OneNote',
    'papier':     'Papier',
    'buch':       'Buch',
    'familie':    'Familie',
    'eigenes':    'Eigenes',
    'eigene':     'Eigenes',
    'screenshot': 'Screenshot',
}

GUELTIGE_QUELLEN = {'Chefkoch', 'OneNote', 'Papier', 'Buch', 'Familie', 'Eigenes', 'Screenshot'}
GUELTIGE_KATEGORIEN = {
    'fruehstueck', 'suppen', 'vegetarisch', 'fleisch',
    'pasta', 'backen', 'dessert', 'snacks', 'getraenke',
}


@dataclass
class RezeptRow:
    """Ein Rezept wie es aus dem Import hervorgeht."""
    name:       str
    kategorie:  str = 'vegetarisch'
    aufwand:    str = 'niedrig'
    quelle:     str = ''
    zutaten:    str = ''
    saison:     str = 'Ganzjährig'
    notiz:      str = ''
    link:       str = ''
    liebling:   bool = False
    # Metadaten für die Vorschau
    row_num:    int = 0
    warnings:   list = field(default_factory=list)


@dataclass
class ImportResult:
    total:    int = 0
    imported: int = 0
    skipped:  int = 0
    errors:   list = field(default_factory=list)
    rows:     list = field(default_factory=list)  # RezeptRow-Objekte
    dry_run:  bool = True


def _normalize(value) -> str:
    if value is None:
        return ''
    return str(value).strip()


def _map_kategorie(raw: str) -> tuple[str, Optional[str]]:
    """Gibt (app_key, warning) zurück."""
    key = raw.lower().strip()
    if key in GUELTIGE_KATEGORIEN:
        return key, None
    mapped = KATEGORIE_MAPPING.get(key)
    if mapped:
        return mapped, None
    return 'vegetarisch', f"Unbekannte Kategorie '{raw}' → 'vegetarisch' (bitte prüfen)"


def _map_quelle(raw: str) -> tuple[str, str]:
    """Gibt (quelle, link) zurück. Link wenn raw eine URL ist."""
    raw = raw.strip()
    if raw.lower().startswith('http'):
        return 'Chefkoch', raw   # URL geht ins link-Feld
    # "Ordner..." Muster → Papier
    if raw.lower().startswith('ordner'):
        return 'Papier', ''
    key = raw.lower()
    return QUELLE_MAPPING.get(key, raw if raw in GUELTIGE_QUELLEN else 'Eigenes'), ''


def _parse_liebling(raw) -> bool:
    if raw is None:
        return False
    try:
        return float(raw) >= 4
    except (ValueError, TypeError):
        s = str(raw).lower().strip()
        return s in ('ja', 'yes', 'true', '1', 'x')


def parse_excel(file_obj) -> list[RezeptRow]:
    """Liest eine .xlsx-Datei und gibt eine Liste von RezeptRow zurück."""
    import openpyxl
    # Mehrere Ladestrategien — manche xlsx-Dateien haben invalide Stylesheets
    wb = None
    errors = []
    for kwargs in [
        {'data_only': True},
        {'data_only': True, 'read_only': True},
        {'data_only': True, 'keep_links': False},
    ]:
        try:
            file_obj.seek(0)
            wb = openpyxl.load_workbook(file_obj, **kwargs)
            break
        except Exception as exc:
            errors.append(str(exc))

    if wb is None:
        raise ValueError(
            f"Die Excel-Datei konnte nicht gelesen werden. "
            f"Bitte als CSV speichern (Excel → Speichern unter → CSV UTF-8) "
            f"und nochmal hochladen. Details: {errors[0]}"
        )

    ws = wb.active

    rows = list(ws.iter_rows(values_only=True))
    if not rows:
        return []

    # Spaltennamen aus erster Zeile
    header = [str(h).strip().lower() if h else '' for h in rows[0]]

    def col(name_variants: list[str]) -> Optional[int]:
        for v in name_variants:
            if v in header:
                return header.index(v)
        return None

    idx_titel     = col(['titel', 'name', 'rezeptname'])
    idx_kat       = col(['kategorie', 'kategory', 'kat'])
    idx_unterkat  = col(['unterkategorie', 'unterkat'])
    idx_quelle    = col(['quelle', 'source'])
    idx_fundst    = col(['fundstelle'])
    idx_zutaten   = col(['zutaten', 'ingredients'])
    idx_bemerk    = col(['bemerkung', 'notiz', 'note', 'anmerkung'])
    idx_bewert    = col(['bewertung', 'sterne', 'rating', 'wertung'])

    result = []
    for i, row in enumerate(rows[1:], start=2):
        titel = _normalize(row[idx_titel] if idx_titel is not None else None)
        if not titel:
            continue   # Zeile ohne Titel überspringen

        r = RezeptRow(name=titel, row_num=i)

        # Kategorie
        kat_raw = _normalize(row[idx_kat] if idx_kat is not None else None)
        if kat_raw:
            r.kategorie, warn = _map_kategorie(kat_raw)
            if warn:
                r.warnings.append(warn)

        # Quelle + Link aus Quelle-Spalte
        quelle_raw = _normalize(row[idx_quelle] if idx_quelle is not None else None)
        if quelle_raw:
            r.quelle, r.link = _map_quelle(quelle_raw)

        # Fundstelle → link (wenn URL und link noch leer)
        fundst_raw = _normalize(row[idx_fundst] if idx_fundst is not None else None)
        if fundst_raw and not r.link and fundst_raw.lower().startswith('http'):
            r.link = fundst_raw

        # Zutaten
        r.zutaten = _normalize(row[idx_zutaten] if idx_zutaten is not None else None)

        # Notiz = Bemerkung + ggf. Unterkategorie
        bemerk = _normalize(row[idx_bemerk] if idx_bemerk is not None else None)
        unterkat = _normalize(row[idx_unterkat] if idx_unterkat is not None else None)
        parts = [p for p in [bemerk, f"({unterkat})" if unterkat else ''] if p]
        r.notiz = ' '.join(parts)

        # Liebling aus Bewertung
        r.liebling = _parse_liebling(row[idx_bewert] if idx_bewert is not None else None)

        result.append(r)

    return result


def parse_csv(file_obj) -> list[RezeptRow]:
    """Liest eine .csv-Datei (UTF-8 oder Latin-1)."""
    import csv, io
    raw = file_obj.read()
    for enc in ('utf-8-sig', 'utf-8', 'latin-1'):
        try:
            text = raw.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    else:
        text = raw.decode('latin-1', errors='replace')

    reader = csv.DictReader(io.StringIO(text))
    result = []
    for i, row in enumerate(reader, start=2):
        row_lower = {k.strip().lower(): v for k, v in row.items() if k}
        titel = row_lower.get('titel') or row_lower.get('name') or ''
        titel = _normalize(titel)
        if not titel:
            continue

        r = RezeptRow(name=titel, row_num=i)

        kat_raw = _normalize(row_lower.get('kategorie', ''))
        if kat_raw:
            r.kategorie, warn = _map_kategorie(kat_raw)
            if warn:
                r.warnings.append(warn)

        quelle_raw = _normalize(row_lower.get('quelle', ''))
        if quelle_raw:
            r.quelle, r.link = _map_quelle(quelle_raw)

        fundst = _normalize(row_lower.get('fundstelle', ''))
        if fundst and not r.link and fundst.lower().startswith('http'):
            r.link = fundst

        r.zutaten = _normalize(row_lower.get('zutaten', ''))

        bemerk   = _normalize(row_lower.get('bemerkung') or row_lower.get('notiz', ''))
        unterkat = _normalize(row_lower.get('unterkategorie', ''))
        parts = [p for p in [bemerk, f"({unterkat})" if unterkat else ''] if p]
        r.notiz = ' '.join(parts)

        r.liebling = _parse_liebling(row_lower.get('bewertung') or row_lower.get('sterne'))
        result.append(r)

    return result


def do_import(rows: list[RezeptRow], user, dry_run: bool = True) -> ImportResult:
    """Speichert die Rezepte in der DB (oder simuliert es bei dry_run=True)."""
    from recipes.models import Rezept

    result = ImportResult(total=len(rows), dry_run=dry_run, rows=rows)

    for r in rows:
        try:
            if not dry_run:
                Rezept.objects.update_or_create(
                    name=r.name,
                    user=user,
                    defaults={
                        'kategorie': r.kategorie,
                        'aufwand':   r.aufwand,
                        'quelle':    r.quelle,
                        'zutaten':   r.zutaten,
                        'saison':    r.saison,
                        'notiz':     r.notiz,
                        'link':      r.link,
                        'liebling':  r.liebling,
                    }
                )
            result.imported += 1
        except Exception as exc:
            result.errors.append(f"Zeile {r.row_num} ({r.name}): {exc}")
            result.skipped += 1

    return result
