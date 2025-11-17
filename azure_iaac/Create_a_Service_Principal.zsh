RESOURCE_GROUP="RG_LC"
SUBSCRIPTION_ID="0d128348-5c28-4d97-9b2b-f40d7022ae96"
az ad sp create-for-rbac --name "github-deploy-lc-app" --role contributor \
  --scopes /subscriptions/$SUBSCRIPTION_ID/resourceGroups/$RESOURCE_GROUP \
  --sdk-auth