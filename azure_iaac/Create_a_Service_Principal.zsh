#!/bin/zsh
set -e

# ============================
# 📥 Konfiguration laden
# ============================
if [[ ! -f ".env" ]]; then
    echo "❌ Fehler: Datei '.env' nicht gefunden!"
    exit 1
fi

# Laden und Bereinigen der Variablen
set -a
source .env
set +a

# Bereinigung von unsichtbaren Zeichen (wichtig bei Windows/Mac Wechsel!)
AZURE_SUBSCRIPTION_ID=$(echo "$AZURE_SUBSCRIPTION_ID" | tr -d '[:space:]')
RESOURCE_GROUP="RG_LC"   # Resource Group fest im Skript (oder auch in .env, falls gewünscht)
SP_NAME="github-deploy-lc-app"

# Sicherheits-Check
if [[ -z "$AZURE_SUBSCRIPTION_ID" ]]; then
    echo "❌ Fehler: AZURE_SUBSCRIPTION_ID fehlt in der .env Datei."
    exit 1
fi

echo "========================================================"
echo "🛠️ Erstelle Service Principal für GitHub Actions..."
echo "========================================================"
echo "🎯 Ziel:"
echo "   App: $SP_NAME"
echo "   RG:  $RESOURCE_GROUP"
echo "   Sub: $AZURE_SUBSCRIPTION_ID"
echo "--------------------------------------------------------"

# Befehl ausführen
# Hinweis: --sdk-auth ist 'deprecated', aber für GitHub Actions oft noch nötig.
# Falls GitHub meckert, nutzen Sie später JSON ohne --sdk-auth.
az ad sp create-for-rbac \
    --name "$SP_NAME" \
    --role contributor \
    --scopes "/subscriptions/$AZURE_SUBSCRIPTION_ID/resourceGroups/$RESOURCE_GROUP" \
    --sdk-auth

echo ""
echo "========================================================"
echo "⚠️ WICHTIG:"
echo "Kopieren Sie den gesamten JSON-Output oben (inkl. {})"
echo "und speichern Sie ihn in GitHub als Secret: 'AZURE_CREDENTIALS'"
echo "========================================================"
