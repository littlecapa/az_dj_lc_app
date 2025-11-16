#!/bin/zsh
az account clear
# ============================
# 🔐 Log out of any existing sessions
# ============================
echo "Logging out of any existing Azure sessions..."
az logout

# ============================
# 🔑 Log in using device code (MFA-friendly)
# ============================
echo "Logging in to Azure using device code..."
az login --use-device-code

# ============================
# 🧾 Register required resource provider
# ============================
echo "Registering Microsoft.Sql provider..."
az provider register --namespace Microsoft.Sql

# ============================
# 📋 List available subscriptions
# ============================
echo "Listing available subscriptions..."
az account list --output table

# ============================
# 📌 Set active subscription
# ============================
echo "Setting active subscription..."
az account set --subscription "0d128348-5c28-4d97-9b2b-f40d7022ae96"

# ✅ Confirm active subscription
echo "Current active subscription:"
az account show --output table