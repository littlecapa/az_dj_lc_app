#!/bin/zsh
set -e

# ============================
# 📥 Konfiguration laden
# ============================

# Prüfen, ob die .env Datei existiert
if [[ ! -f ".env" ]]; then
    echo "❌ Fehler: Datei '.env' nicht gefunden!"
    echo "Bitte erstellen Sie eine Datei namens '.env' mit folgendem Inhalt:"
    echo 'AZURE_TENANT_ID="ihre-tenant-id"'
    echo 'AZURE_SUBSCRIPTION_ID="ihre-subscription-id"'
    exit 1
fi

# Laden der Variablen aus .env (exportiert sie für die Session)
# 'set -a' exportiert automatisch alle Variablen, 'source' liest die Datei, 'set +a' stoppt den Auto-Export
set -a
source .env
set +a

AZURE_TENANT_ID=$(echo "$AZURE_TENANT_ID" | tr -d '[:space:]')
AZURE_SUBSCRIPTION_ID=$(echo "$AZURE_SUBSCRIPTION_ID" | tr -d '[:space:]')

# Prüfen, ob die Variablen auch wirklich da sind
if [[ -z "$AZURE_TENANT_ID" ]] || [[ -z "$AZURE_SUBSCRIPTION_ID" ]]; then
    echo "❌ Fehler: Variablen in '.env' sind leer oder fehlen."
    exit 1
fi

echo "========================================================"
echo "🚀 Starte Azure Login Prozess..."
echo "========================================================"

# 1. Clean Slate
echo "🧹 Bereinige lokale Azure-Sitzungen..."
az account clear

# 2. Login mit Tenant ID aus der .env Datei
echo "🔑 Bitte einloggen (Device Code)..."
az login --use-device-code --tenant "$AZURE_TENANT_ID" --output none
echo "✅ Login erfolgreich."

# 3. Subscription setzen aus der .env Datei
echo "📌 Setze aktive Subscription..."
az account set --subscription "$AZURE_SUBSCRIPTION_ID"

# 4. Provider Check
REQUIRED_PROVIDER="Microsoft.Sql"
echo "🧾 Prüfe Status für Provider: $REQUIRED_PROVIDER..."
PROVIDER_STATE=$(az provider show --namespace $REQUIRED_PROVIDER --query "registrationState" -o tsv)

if [[ "$PROVIDER_STATE" == "Registered" ]]; then
    echo "✅ Provider '$REQUIRED_PROVIDER' ist bereits registriert."
else
    echo "⚠️ Provider nicht registriert. Starte Registrierung..."
    az provider register --namespace $REQUIRED_PROVIDER
    echo "⏳ Registrierung angestoßen."
fi

# 5. Abschluss
echo "========================================================"
echo "🎉 Fertig! Aktive Konfiguration:"
az account show --query "{Subscription:name, ID:id, User:user.name}" --output table
