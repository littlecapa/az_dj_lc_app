"""
Gemeinsamer Namensabgleich für externe Quellen ohne ISIN (Wikipedia,
companiesmarketcap.com, manuelle Factsheet-Einträge) <-> bereits im System
bekannte Asset-Namen. Wird sowohl von update_etf_holdings (DAX-/MSCI-World-
Tail-Erweiterung) als auch von der Look-Through-View (ManualFondHolding)
verwendet — daher hier zentral statt in einem einzelnen Command.
"""
import re

_NAME_STOPWORDS_RE = re.compile(
    r"\b(ag|se|na|st|inh|inc|corp|corporation|group|holding|holdings|plc|nv|sa|ltd|co|class)\b"
)
_UMLAUT_TRANSLATION = str.maketrans({"ä": "ae", "ö": "oe", "ü": "ue", "ß": "ss"})


def normalize_company_name(name: str) -> str:
    """Grobe Normalisierung für den Namensabgleich (Umlaute transliteriert wie
    bei Börsenkürzeln üblich [ü->ue etc.], Rechtsform-Suffixe raus, nur
    alphanumerisch, ein Leerzeichen)."""
    name = name.lower().translate(_UMLAUT_TRANSLATION)
    name = _NAME_STOPWORDS_RE.sub(" ", name)
    name = re.sub(r"[^a-z0-9]+", " ", name)
    return " ".join(name.split())


def match_held_stock(external_name: str, held_assets):
    """Sucht unter den bereits im System bekannten STOCK-Assets (direkt
    gehalten oder bereits über einen anderen Fonds als Dummy-Holdings
    erfasst) eines, dessen normalisierte Wörter des externen Namens
    vollständig unter den Wörtern des gehaltenen Assets wiederfinden — als
    vollständige Wörter, nicht als bloßer Teilstring. Es wird bewusst nur
    diese eine Richtung geprüft (externer Name ⊆ gehaltener Name): gehaltene
    Assets führen typischerweise den vollen Namen inkl. Rechtsform-Suffixen
    (AG/SE/NA/O.N.), externe Quellen den kurzen Namen. Die umgekehrte
    Richtung würde z.B. "Siemens" fälschlich auf "Siemens Energy"/"Siemens
    Healthineers" matchen (eigenständige, abgespaltene Gesellschaften) — und
    reiner Teilstring-Vergleich würde kurze Namen wie "RWE" als Zeichenfolge
    in unverwandten Namen wie "Vorwerk" finden.
    Best-effort — bei einer kleinen, bekannten Portfoliogröße ausreichend
    zuverlässig; falsche/fehlende Treffer sind über den Admin leicht zu sehen."""
    external_tokens = set(normalize_company_name(external_name).split())
    if not external_tokens:
        return None
    for asset in held_assets:
        asset_tokens = set(normalize_company_name(asset.name).split())
        if asset_tokens and external_tokens <= asset_tokens:
            return asset
    return None
