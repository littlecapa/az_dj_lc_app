#!/bin/zsh
set -e

# ============================
# 📥 Konfiguration laden
# ============================
if [[ ! -f ".env" ]]; then
    echo "❌ Fehler: Datei '.env' nicht gefunden!"
    exit 1
fi

# Laden der Variablen
set -a
source .env
set +a

# ============================
# 🧹 Automatische Bereinigung (Smart Loop)
# ============================
# Entfernt unsichtbare Zeichen/Leerzeichen am Anfang und Ende aller Variablen,
# lässt aber Leerzeichen INNERHALB von Strings (z.B. bei Commands) intakt.

# 1. Liste der Variablennamen aus der .env extrahieren (ignoriert Kommentare & leere Zeilen)
# grep -v '^#' : Ignoriert Kommentarzeilen
# grep '='     : Nimmt nur Zeilen mit Zuweisungen
# cut -d '='   : Schneidet den Namen vor dem Ist-Gleich aus
ENV_VARS=($(grep -v '^#' .env | grep '=' | cut -d '=' -f 1))

# 2. Loop über alle Variablen
for var in $ENV_VARS; do
    # Wert holen (zsh indirekte Referenz)
    val="${(P)var}"
    
    # Trimmen von Whitespace/Newline am Anfang & Ende (zsh pattern matching)
    trimmed_val="${val#"${val%%[![:space:]]*}"}"   # Leading whitespace weg
    trimmed_val="${trimmed_val%"${trimmed_val##*[![:space:]]}"}"   # Trailing whitespace weg
    
    # Variable neu setzen
    # (q) quotet den String sicher für eval, damit Sonderzeichen erhalten bleiben
    eval "$var=${(q)trimmed_val}"
done

# 3. Spezielle "Hard Cleaning" für IDs
# Bei IDs darf es absolut KEINE Leerzeichen geben (auch nicht innen), daher hier radikaler
IDS_TO_CHECK=("AZURE_SUBSCRIPTION_ID" "AZURE_TENANT_ID" "SQL_ADMIN_PASS")
for id_var in $IDS_TO_CHECK; do
    val="${(P)id_var}"
    # tr -d '[:space:]' entfernt alles was unsichtbar ist
    clean_val=$(echo "$val" | tr -d '[:space:]')
    eval "$id_var='$clean_val'"
done

# ============================
# ✅ Validierung
# ============================
REQUIRED_VARS=("RESOURCE_GROUP" "LOCATION" "WEB_APP_NAME" "SQL_SERVER_NAME" "DB_NAME" "DB_USER" "SQL_ADMIN_PASS")
for var in $REQUIRED_VARS; do
    if [[ -z "${(P)var}" ]]; then
        echo "❌ Fehler: Variable '$var' fehlt in der .env Datei!"
        exit 1
    fi
done

# Zusätzliche Skript-Definitionen
RUNTIME="PYTHON:3.11"
GITHUB_REPO="littlecapa/az_dj_lc_app"
GITHUB_BRANCH="main"

echo "========================================================"
echo "🚀 Starte Infrastructure Deployment"
echo "========================================================"
echo "Ziel-Subscription: $AZURE_SUBSCRIPTION_ID"
echo "Resource Group:    $RESOURCE_GROUP"
echo "Web App Name:      $WEB_APP_NAME"
echo "SQL Server:        $SQL_SERVER_NAME"
echo "Datenbank:         $DB_NAME"
echo "--------------------------------------------------------"

# ============================
# 🔐 Login & Context
# ============================
az account show &>/dev/null || az login --use-device-code --tenant "$AZURE_TENANT_ID" --output none
az account set --subscription "$AZURE_SUBSCRIPTION_ID"

# ============================
# 1. Resource Group
# ============================
if ! az group show --name $RESOURCE_GROUP &>/dev/null; then
  echo "📦 Erstelle Resource Group: $RESOURCE_GROUP..."
  az group create --name $RESOURCE_GROUP --location $LOCATION
else
  echo "✅ Resource Group existiert bereits."
fi

# ============================
# 2. App Service Plan (Linux/Free)
# ============================
if ! az appservice plan show --name $APP_PLAN --resource-group $RESOURCE_GROUP &>/dev/null; then
  echo "🏗️ Erstelle App Service Plan: $APP_PLAN (F1 Free Tier)..."
  az appservice plan create \
    --name $APP_PLAN \
    --resource-group $RESOURCE_GROUP \
    --sku F1 \
    --is-linux \
    --location $LOCATION
else
  echo "✅ App Service Plan existiert bereits."
fi

# ============================
# 3. Web App
# ============================
if ! az webapp show --name $WEB_APP_NAME --resource-group $RESOURCE_GROUP &>/dev/null; then
  echo "🌐 Erstelle Web App: $WEB_APP_NAME..."
  az webapp create \
    --resource-group $RESOURCE_GROUP \
    --plan $APP_PLAN \
    --name $WEB_APP_NAME \
    --runtime "$RUNTIME"
else
  echo "✅ Web App existiert bereits."
fi

# ============================
# 4. SQL Server
# ============================
if ! az sql server show --name $SQL_SERVER_NAME --resource-group $RESOURCE_GROUP &>/dev/null; then
  echo "🗄️ Erstelle SQL Server: $SQL_SERVER_NAME (Das dauert etwas)..."
  az sql server create \
    --name $SQL_SERVER_NAME \
    --resource-group $RESOURCE_GROUP \
    --location $LOCATION \
    --admin-user $DB_USER \
    --admin-password "$SQL_ADMIN_PASS"
else
  echo "✅ SQL Server existiert bereits."
fi

# ============================
# 5. SQL Database
# ============================
if ! az sql db show --name $DB_NAME --server $SQL_SERVER_NAME --resource-group $RESOURCE_GROUP &>/dev/null; then
  echo "💾 Erstelle SQL Datenbank: $DB_NAME..."
  az sql db create \
    --resource-group $RESOURCE_GROUP \
    --server $SQL_SERVER_NAME \
    --name $DB_NAME \
    --service-objective Basic
else
  echo "✅ SQL Datenbank existiert bereits."
fi

# ============================
# 6. Firewall (Zugriff für Azure Apps)
# ============================
if ! az sql server firewall-rule show --name AllowAzureServices --server $SQL_SERVER_NAME --resource-group $RESOURCE_GROUP &>/dev/null; then
  echo "🔥 Konfiguriere Firewall (AllowAzureServices)..."
  az sql server firewall-rule create \
    --resource-group $RESOURCE_GROUP \
    --server $SQL_SERVER_NAME \
    --name AllowAzureServices \
    --start-ip-address 0.0.0.0 \
    --end-ip-address 0.0.0.0
else
  echo "✅ Firewall Regel existiert bereits."
fi

# ============================
# 7. Environment Variables (App Settings)
# ============================
echo "⚙️ Konfiguriere App Settings (Environment Variables)..."
az webapp config appsettings set \
  --name $WEB_APP_NAME \
  --resource-group $RESOURCE_GROUP \
  --settings \
    DB_NAME="$DB_NAME" \
    DB_USER="$DB_USER" \
    DB_PASSWORD="$SQL_ADMIN_PASS" \
    DB_HOST="$SQL_SERVER_NAME.database.windows.net" \
    DB_PORT="1433" \
    RESOURCE_GROUP="$RESOURCE_GROUP" \
    APP_NAME="$WEB_APP_NAME" \
    DJANGO_ENV="production" \
    DJANGO_SETTINGS_MODULE="azureproject.production" \
    SCM_DO_BUILD_DURING_DEPLOYMENT="true" \
    PYTHON_ENABLE_GUNICORN_MULTIWORKERS="true"

# Separat den Startup-Command setzen (sauberer als via AppSettings)
# Das ist der offizielle Weg, um das Startup-File zu definieren
echo "🚀 Setze Startup Command auf startup.sh..."
az webapp config set \
  --resource-group $RESOURCE_GROUP \
  --name $WEB_APP_NAME \
  --startup-file "/home/site/wwwroot/startup.sh"

# ============================
# 8. GitHub Deployment
# ============================
echo "🔄 Verbinde mit GitHub Repo: $GITHUB_REPO..."
az webapp deployment github-actions add \
  --resource-group $RESOURCE_GROUP \
  --name $WEB_APP_NAME \
  --repo $GITHUB_REPO \
  --branch $GITHUB_BRANCH \
  --login-with-github || echo "⚠️  GitHub Verbindung übersprungen/fehlgeschlagen."

# ============================
# 9. Logging & Restart
# ============================
echo "📝 Aktiviere Logging..."
az webapp log config \
  --name $WEB_APP_NAME \
  --resource-group $RESOURCE_GROUP \
  --application-logging filesystem \
  --level information --output table

echo "🔄 Starte Web App neu..."
az webapp restart --name $WEB_APP_NAME --resource-group $RESOURCE_GROUP

echo "========================================================"
echo "🎉 Fertig! Ihre App sollte bald unter https://$WEB_APP_NAME.azurewebsites.net erreichbar sein."
echo "========================================================"
