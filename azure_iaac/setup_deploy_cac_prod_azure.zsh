#!/bin/zsh
az version | grep '"azure-cli"' || az upgrade

# ============================
# 🔧 Parameter Definitions
# ============================
RESOURCE_GROUP="RG_LC"
LOCATION="westeurope"
APP_PLAN="lc_plan"
WEB_APP_NAME="lc-app"  # Must be globally unique
RUNTIME="PYTHON|3.11"
SQL_SERVER_NAME="lcsqlserver"
SQL_DB_NAME="lc_db"
SQL_ADMIN_USER="lc_db_admin"
GITHUB_REPO="littlecapa/az_dj_lc_app"
GITHUB_BRANCH="main"

echo -n "Enter SQL admin password: "
read -s SQL_ADMIN_PASS
echo
export SQL_ADMIN_PASS
if [ -z "$SQL_ADMIN_PASS" ]; then
  echo "❌ SQL admin password cannot be empty. Exiting."
  exit 1
fi

# ============================
# 🚀 Create Resource Group
# ============================
if ! az group show --name $RESOURCE_GROUP &>/dev/null; then
  echo "Creating resource group $RESOURCE_GROUP..."
  az group create --name $RESOURCE_GROUP --location $LOCATION
else
  echo "Resource group $RESOURCE_GROUP already exists. Skipping."
fi

# ============================
# 🌐 Create App Service Plan
# ============================
if ! az appservice plan show --name $APP_PLAN --resource-group $RESOURCE_GROUP &>/dev/null; then
  echo "Creating App Service Plan $APP_PLAN..."
  az appservice plan create \
    --name $APP_PLAN \
    --resource-group $RESOURCE_GROUP \
    --sku F1 \
    --is-linux \
    --location $LOCATION
else
  echo "App Service Plan $APP_PLAN already exists. Skipping."
fi

# ============================
# 🌐 Create Web App
# ============================
if ! az webapp show --name $WEB_APP_NAME --resource-group $RESOURCE_GROUP &>/dev/null; then
  echo "Creating Web App $WEB_APP_NAME..."
  az webapp create \
    --resource-group $RESOURCE_GROUP \
    --plan $APP_PLAN \
    --name $WEB_APP_NAME \
    --runtime "$RUNTIME"
else
  echo "Web App $WEB_APP_NAME already exists. Skipping."
fi

# ============================
# 🛠️ Create SQL Server
# ============================
if ! az sql server show --name $SQL_SERVER_NAME --resource-group $RESOURCE_GROUP &>/dev/null; then
  echo "Creating SQL Server $SQL_SERVER_NAME..."
  az sql server create \
    --name $SQL_SERVER_NAME \
    --resource-group $RESOURCE_GROUP \
    --location $LOCATION \
    --admin-user $SQL_ADMIN_USER \
    --admin-password $SQL_ADMIN_PASS
else
  echo "SQL Server $SQL_SERVER_NAME already exists. Skipping."
fi

# ============================
# 🛠️ Create SQL Database
# ============================
if ! az sql db show --name $SQL_DB_NAME --server $SQL_SERVER_NAME --resource-group $RESOURCE_GROUP &>/dev/null; then
  echo "Creating SQL Database $SQL_DB_NAME..."
  az sql db create \
    --resource-group $RESOURCE_GROUP \
    --server $SQL_SERVER_NAME \
    --name $SQL_DB_NAME \
    --service-objective Basic
else
  echo "SQL Database $SQL_DB_NAME already exists. Skipping."
fi

# ============================
# 🔐 Configure Firewall
# ============================
if ! az sql server firewall-rule show --name AllowAzureServices --server $SQL_SERVER_NAME --resource-group $RESOURCE_GROUP &>/dev/null; then
  echo "Creating firewall rule AllowAzureServices..."
  az sql server firewall-rule create \
    --resource-group $RESOURCE_GROUP \
    --server $SQL_SERVER_NAME \
    --name AllowAzureServices \
    --start-ip-address 0.0.0.0 \
    --end-ip-address 0.0.0.0
else
  echo "Firewall rule AllowAzureServices already exists. Skipping."
fi

# ============================
# 🔄 Setup GitHub Deployment
# ============================
echo "Setting up GitHub Actions deployment..."
az webapp deployment github-actions add \
  --resource-group $RESOURCE_GROUP \
  --name $WEB_APP_NAME \
  --repo $GITHUB_REPO \
  --branch $GITHUB_BRANCH \
  --runtime $RUNTIME \
  --login-with-github


echo "✅ Deployment script completed."

az webapp config appsettings set \
  --name $WEB_APP_NAME \
  --resource-group $RESOURCE_GROUP \
  --settings \
    DB_NAME=$SQL_DB_NAME \
    DB_USER=$SQL_ADMIN_USER \
    DB_PASSWORD=$SQL_ADMIN_PASS \
    DB_HOST=$SQL_SERVER_NAME.database.windows.net \
    DB_PORT=1433 \
    DJANGO_ENV=production \
    DJANGO_SETTINGS_MODULE=azureproject.production \
    STARTUP_COMMAND="/home/site/wwwroot/startup.sh" \
    SCM_DO_BUILD_DURING_DEPLOYMENT=true 

az webapp log config \
  --name $WEB_APP_NAME \
  --resource-group $RESOURCE_GROUP \
  --application-logging filesystem \
  --level information --output table

az webapp restart