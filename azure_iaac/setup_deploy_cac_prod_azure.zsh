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
SQL_ADMIN_PASS="CAC_password123!"
GITHUB_REPO="https://github.com/littlecapa/chess_ai_coach"
GITHUB_BRANCH="main"

# ============================
# 🚀 Create Resource Group
# ============================
az group create --name $RESOURCE_GROUP --location $LOCATION

# ============================
# 🌐 Create App Service Plan & Web App
# ============================
az appservice plan create \
  --name $APP_PLAN \
  --resource-group $RESOURCE_GROUP \
  --sku F1 \
  --is-linux \
  --location $LOCATION

az webapp create \
  --resource-group $RESOURCE_GROUP \
  --plan $APP_PLAN \
  --name $WEB_APP_NAME \
  --runtime $RUNTIME

# ============================
# 🛠️ Create SQL Server & Database
# ============================
az sql server create \
  --name $SQL_SERVER_NAME \
  --resource-group $RESOURCE_GROUP \
  --location $LOCATION \
  --admin-user $SQL_ADMIN_USER \
  --admin-password $SQL_ADMIN_PASS

az sql db create \
  --resource-group $RESOURCE_GROUP \
  --server $SQL_SERVER_NAME \
  --name $SQL_DB_NAME \
  --service-objective Basic

# ============================
# 🔐 Configure Firewall
# ============================
az sql server firewall-rule create \
  --resource-group $RESOURCE_GROUP \
  --server $SQL_SERVER_NAME \
  --name AllowAzureServices \
  --start-ip-address 0.0.0.0 \
  --end-ip-address 0.0.0.0

# ============================
# 🔄 Setup GitHub Deployment
# ============================
az webapp deployment github-actions add \
  --resource-group $RESOURCE_GROUP \
  --name $WEB_APP_NAME \
  --repo-url $GITHUB_REPO \
  --branch $GITHUB_BRANCH \
  --runtime $RUNTIME

echo "✅ Deployment script completed."