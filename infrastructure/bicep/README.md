# Edge Sentinel Azure Infrastructure

This folder contains the resource-group-scoped Bicep deployment for the core Azure Monitor ingestion path.

It deploys:

- Log Analytics workspace
- `EdgeSentinel_CL` custom table
- Direct Data Collection Rule for the Logs Ingestion API

The existing resource group is intentionally not created by this template.

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
