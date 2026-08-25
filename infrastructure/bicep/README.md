# Edge Sentinel Azure Infrastructure

This folder contains the resource-group-scoped Bicep deployment for the core Azure Monitor ingestion path.

It deploys:

- Log Analytics workspace
- `EdgeSentinel_CL` custom table
- Direct Data Collection Rule for the Logs Ingestion API

The existing resource group is intentionally not created by this template.

The Log Analytics workspace disables local/non-Microsoft Entra authentication; Edge Sentinel uses Microsoft Entra ID and Azure RBAC for Azure access.

## Validate

```powershell
az bicep build --file .\infrastructure\bicep\main.bicep
```

## Preview changes

```powershell
az deployment group what-if `
  --resource-group rg-edgesentinel-dev `
  --template-file .\infrastructure\bicep\main.bicep `
  --parameters .\infrastructure\bicep\parameters.dev.json
```

## Deploy

```powershell
az deployment group create `
  --resource-group rg-edgesentinel-dev `
  --template-file .\infrastructure\bicep\main.bicep `
  --parameters .\infrastructure\bicep\parameters.dev.json
```

After deployment, use the `logsIngestionEndpoint` and `dcrImmutableId` outputs for:

- `EDGESENTINEL_DCR_ENDPOINT`
- `EDGESENTINEL_DCR_IMMUTABLE_ID`

## Authorize the collector identity

Bicep intentionally does not create or select the identity that runs the collector. The collector identity requires the Azure built-in `Monitoring Metrics Publisher` role scoped to the deployed Data Collection Rule resource. This authorization is required before Azure ingestion will succeed. RBAC propagation may take time, and an initial HTTP 403 can occur before the assignment becomes effective.

```powershell
az role assignment create `
  --assignee-object-id "<collector-principal-object-id>" `
  --assignee-principal-type "<User|ServicePrincipal>" `
  --role "Monitoring Metrics Publisher" `
  --scope "/subscriptions/<subscription-id>/resourceGroups/<resource-group-name>/providers/Microsoft.Insights/dataCollectionRules/<dcr-name>"
```

A managed identity uses its service-principal object ID with `ServicePrincipal` as the principal type.
