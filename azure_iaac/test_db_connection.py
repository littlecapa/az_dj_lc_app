import os
import sys
import pyodbc
from dotenv import load_dotenv

# 1. Lade Umgebungsvariablen aus der .env Datei
load_dotenv(override=True)

def get_env_var(name):
    """Hilfsfunktion um Variablen sicher zu holen"""
    val = os.getenv(name)
    if not val:
        print(f"❌ Fehler: Variable '{name}' fehlt in der .env Datei oder Umgebung!")
        sys.exit(1)
    # WICHTIG: Bereinigung von Whitespace (analog zum Shell Script)
    return val.strip()

def test_connection():
    # 2. Hole Konfiguration
    server = get_env_var("DB_HOST")      # lcsqlserver-live.database.windows.net
    database = get_env_var("DB_NAME")    # lc_db
    username = get_env_var("DB_USER")    # lc_db_admin
    password = get_env_var("SQL_ADMIN_PASS") # Korrekt angepasst!
    
    # Treiber für macOS (Muss installiert sein: brew install msodbcsql18)
    driver = "{ODBC Driver 18 for SQL Server}"

    print(f"🔌 Verbinde zu: {server} ...")

    try:
        # 3. Connection String bauen
        # Wir entfernen die Einrückungen, um Parsing-Fehler zu vermeiden
        conn_str = (
            f"DRIVER={driver};"
            f"SERVER={server};"
            f"DATABASE={database};"
            f"UID={username};"
            f"PWD={password};"
            "Encrypt=yes;"
            "TrustServerCertificate=no;"  # Prod-Safe
            "Connection Timeout=30;"
        )
        
        print("Testing database connection...")
        
        # Verbindung herstellen
        conn = pyodbc.connect(conn_str)
        cursor = conn.cursor()
        
        # Test-Abfrage
        cursor.execute("SELECT @@VERSION")
        row = cursor.fetchone()
        
        print("✅ Database connection successful!")
        print(f"ℹ️  Server Version: {row[0][:50]}...") 
        
        conn.close()
        return True
        
    except Exception as e:
        print(f"\n❌ Connection failed: {type(e).__name__}")
        print(f"Details: {str(e)}")
        
        # Häufigster Fehler-Check
        if "Client with IP address" in str(e):
            print("\n⚠️  URSACHE: Ihre IP ist nicht in der Azure Firewall!")
            print("   Nutzen Sie 'az sql server firewall-rule create ...' für Ihre IP.")
            
        return False

if __name__ == "__main__":
    success = test_connection()
    sys.exit(0 if success else 1)
