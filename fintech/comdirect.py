import os
import django
from decimal import Decimal
from logging import getLogger

logger = getLogger(__name__)

# Nur nötig, falls als Standalone-Skript ausgeführt (außerhalb manage.py shell)
# os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'azureproject.settings')
# django.setup()

from fintech.models import Asset, Holdings

def run_import():
    # 1. Sicherheits-Check: Nur importieren, wenn Holdings leer sind
    if Holdings.objects.exists():
        logger.error("ABBRUCH: Es existieren bereits Holdings in der Datenbank. Import wird nicht durchgeführt.")
        return

    logger.info("Starte Import der Comdirect-Depotdaten...")

    # Rohe Daten aus Ihrer CSV extrahiert
    portfolio_data = [
        {"stueck": "40", "name": "DANONE S.A. EO -,25", "wkn": "851194", "typ": "Aktie", "kurs": "72.30", "kaufkurs": "54.52", "isin": "FR0000120644"},
        {"stueck": "3", "name": "BLACKROCK INC. O.N.", "wkn": "A40PW4", "typ": "Aktie", "kurs": "819.90", "kaufkurs": "857.30", "isin": "US09290D1019"},
        {"stueck": "57.334", "name": "UNILEVER PLC LS -,035", "wkn": "A41NM1", "typ": "Aktie", "kurs": "56.93", "kaufkurs": "33.0784", "isin": "GB00BVZK7T90"},
        {"stueck": "17", "name": "ALLIANZ SE NA O.N.", "wkn": "840400", "typ": "Aktie", "kurs": "358.60", "kaufkurs": "119.80", "isin": "DE0008404005"},
        {"stueck": "40", "name": "ISHS CORE DAX UC.ETF EOA", "wkn": "593393", "typ": "ETF", "kurs": "195.90", "kaufkurs": "97.1838", "isin": "DE0005933931"},
        {"stueck": "25", "name": "MORGAN STANLEY DL-,01", "wkn": "885836", "typ": "Aktie", "kurs": "136.52", "kaufkurs": "80.34", "isin": "US6174464486"},
        {"stueck": "50", "name": "NIKE INC. B", "wkn": "866993", "typ": "Aktie", "kurs": "47.56", "kaufkurs": "48.071", "isin": "US6541061031"},
        {"stueck": "133", "name": "IBERDROLA INH. EO -,75", "wkn": "A0M46B", "typ": "Aktie", "kurs": "19.905", "kaufkurs": "8.9142", "isin": "ES0144580Y14"},
        {"stueck": "64.762", "name": "VANECK MSTR.DM DIV.UC.ETF", "wkn": "A2JAHJ", "typ": "ETF", "kurs": "52.15", "kaufkurs": "34.8964", "isin": "NL0011683594"},
        {"stueck": "80", "name": "TALANX AG NA O.N.", "wkn": "TLX100", "typ": "Aktie", "kurs": "106.40", "kaufkurs": "19.785", "isin": "DE000TLX1005"},
        {"stueck": "25", "name": "HANNOVER RUECK SE NA O.N.", "wkn": "840221", "typ": "Aktie", "kurs": "262.60", "kaufkurs": "60.8732", "isin": "DE0008402215"},
        {"stueck": "75", "name": "DEUTSCHE POST AG NA O.N.", "wkn": "555200", "typ": "Aktie", "kurs": "45.24", "kaufkurs": "26.57", "isin": "DE0005552004"},
        {"stueck": "40", "name": "AIRBUS SE", "wkn": "938914", "typ": "Aktie", "kurs": "168.84", "kaufkurs": "48.33", "isin": "NL0000235190"},
        {"stueck": "101", "name": "TOTALENERGIES SE EO 2,50", "wkn": "850727", "typ": "Aktie", "kurs": "72.28", "kaufkurs": "38.2857", "isin": "FR0000120271"},
        {"stueck": "78", "name": "RWE AG INH O.N.", "wkn": "703712", "typ": "Aktie", "kurs": "57.18", "kaufkurs": "28.2355", "isin": "DE0007037129"},
        {"stueck": "40", "name": "MENSCH UND MASCH.O.N.", "wkn": "658080", "typ": "Aktie", "kurs": "35.30", "kaufkurs": "50.00", "isin": "DE0006580806"},
        {"stueck": "37", "name": "DAIMLER TRUCK HLDG NA ON", "wkn": "DTR0CK", "typ": "Aktie", "kurs": "42.63", "kaufkurs": "0.00", "isin": "DE000DTR0CK8"},
        {"stueck": "216", "name": "E.ON SE NA O.N.", "wkn": "ENAG99", "typ": "Aktie", "kurs": "19.87", "kaufkurs": "14.0684", "isin": "DE000ENAG999"},
        {"stueck": "44", "name": "SAP SE O.N.", "wkn": "716460", "typ": "Aktie", "kurs": "166.16", "kaufkurs": "47.705", "isin": "DE0007164600"},
        {"stueck": "22", "name": "NKT A/S NAM. DK 20", "wkn": "861226", "typ": "Aktie", "kurs": "105.40", "kaufkurs": "50.10", "isin": "DK0010287663"},
        {"stueck": "300", "name": "EVOTEC SE INH O.N.", "wkn": "566480", "typ": "Aktie", "kurs": "4.159", "kaufkurs": "3.8034", "isin": "DE0005664809"},
        {"stueck": "135", "name": "WACKER NEUSON SE NA O.N.", "wkn": "WACK01", "typ": "Aktie", "kurs": "18.50", "kaufkurs": "11.3213", "isin": "DE000WACK012"},
        {"stueck": "50", "name": "FR.VORWERK GRP SE INH ON", "wkn": "A255F1", "typ": "Aktie", "kurs": "76.30", "kaufkurs": "30.10", "isin": "DE000A255F11"},
        {"stueck": "75", "name": "MERCEDES-BENZ GRP NA O.N.", "wkn": "710000", "typ": "Aktie", "kurs": "54.46", "kaufkurs": "39.0968", "isin": "DE0007100000"},
        {"stueck": "23", "name": "3M CO. DL-,01", "wkn": "851745", "typ": "Aktie", "kurs": "130.94", "kaufkurs": "89.00", "isin": "US88579Y1010"},
        {"stueck": "30", "name": "BAY.MOTOREN WERKE AG ST", "wkn": "519000", "typ": "Aktie", "kurs": "80.24", "kaufkurs": "65.72", "isin": "DE0005190003"}
    ]

    assets_created = 0
    holdings_created = 0

    for item in portfolio_data:
        # Typ-Mapping für das Model
        asset_class = Asset.AssetClass.ETF if item['typ'] == 'ETF' else Asset.AssetClass.STOCK

        # 1. Asset anlegen oder updaten (Update für den aktuellen Kurs)
        asset, created = Asset.objects.update_or_create(
            isin=item['isin'],
            defaults={
                'wkn': item['wkn'],
                'name': item['name'][:200],  # Kürzen falls zu lang
                'asset_class': asset_class,
                'current_price': Decimal(item['kurs']),
                'currency': 'EUR'
            }
        )
        if created:
            assets_created += 1

        # 2. Holding anlegen
        Holdings.objects.create(
            asset=asset,
            quantity=Decimal(item['stueck']),
            average_purchase_price=Decimal(item['kaufkurs']) if Decimal(item['kaufkurs']) > 0 else None,
            category=Holdings.Category.SONSTIGES  # Standardwert
        )
        holdings_created += 1
        
        logger.warning(f"[{item['isin']}] Importiert: {item['stueck']}x {item['name']}")

    logger.warning(f"\n--- IMPORT ABGESCHLOSSEN ---")
    logger.warning(f"Assets erstellt/aktualisiert: {assets_created}")
    logger.warning(f"Holdings erstellt: {holdings_created}")    
