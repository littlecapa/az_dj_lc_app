#!/bin/zsh

# ============================
# 🔧 Parameter Definitions
# ============================
RESOURCE_GROUP="RG_CAC"
LOCATION="westeurope"
APP_PLAN="cac_plan"
WEB_APP_NAME="cac-app"  # Must be globally unique
RUNTIME="PYTHON|3.11"
SQL_SERVER_NAME="cacsqlserver"
SQL_DB_NAME="cac_db"
SQL_ADMIN_USER="cac_db_admin"
SQL_ADMIN_PASS="LC_G7q!mP4zR@t2"
GITHUB_REPO="littlecapa/chess_ai_coach"
GITHUB_BRANCH="main"

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
    --runtime $RUNTIME
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