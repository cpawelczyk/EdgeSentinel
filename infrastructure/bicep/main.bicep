targetScope = 'resourceGroup'

@description('Azure region for Edge Sentinel observability resources.')
param location string = resourceGroup().location

@description('Log Analytics workspace name.')
param workspaceName string = 'law-edgesentinel-dev'

@description('Data Collection Rule name.')
param dcrName string = 'dcr-edgesentinel-dev'

@description('Custom Log Analytics table name.')
param tableName string = 'EdgeSentinel_CL'

@description('Retention period for the Log Analytics workspace and custom table.')
param retentionInDays int = 30

var streamName = 'Custom-EdgeSentinel'
var destinationName = 'EdgeSentinelWorkspace'

resource workspace 'Microsoft.OperationalInsights/workspaces@2022-10-01' = {
  name: workspaceName
  location: location
  properties: {
    sku: {
      name: 'PerGB2018'
    }
    retentionInDays: retentionInDays
    publicNetworkAccessForIngestion: 'Enabled'
    publicNetworkAccessForQuery: 'Enabled'
    features: {
      enableLogAccessUsingOnlyResourcePermissions: true
      disableLocalAuth: false
    }
  }
}

resource edgeSentinelTable 'Microsoft.OperationalInsights/workspaces/tables@2022-10-01' = {
  parent: workspace
  name: tableName
  properties: {
    plan: 'Analytics'
    retentionInDays: retentionInDays
    totalRetentionInDays: retentionInDays
    schema: {
      name: tableName
      columns: [
        {
          name: 'TimeGenerated'
          type: 'dateTime'
        }
        {
          name: 'timestamp'
          type: 'string'
        }
        {
          name: 'deviceId'
          type: 'string'
        }
        {
          name: 'siteId'
          type: 'string'
        }
        {
          name: 'componentType'
          type: 'string'
        }
        {
          name: 'checkType'
          type: 'string'
        }
        {
          name: 'status'
          type: 'string'
        }
        {
          name: 'latencyMs'
          type: 'real'
        }
        {
          name: 'failureReason'
          type: 'string'
        }
      ]
    }
  }
}

resource dcr 'Microsoft.Insights/dataCollectionRules@2024-03-11' = {
  name: dcrName
  location: location
  kind: 'Direct'
  properties: {
    streamDeclarations: {
      '${streamName}': {
        columns: [
          {
            name: 'timestamp'
            type: 'string'
          }
          {
            name: 'deviceId'
            type: 'string'
          }
          {
            name: 'siteId'
            type: 'string'
          }
          {
            name: 'componentType'
            type: 'string'
          }
          {
            name: 'checkType'
            type: 'string'
          }
          {
            name: 'status'
            type: 'string'
          }
          {
            name: 'latencyMs'
            type: 'real'
          }
          {
            name: 'failureReason'
            type: 'string'
          }
        ]
      }
    }
    destinations: {
      logAnalytics: [
        {
          name: destinationName
          workspaceResourceId: workspace.id
        }
      ]
    }
    dataFlows: [
      {
        streams: [
          streamName
        ]
        destinations: [
          destinationName
        ]
        transformKql: 'source | extend TimeGenerated = todatetime(timestamp)'
        outputStream: 'Custom-${tableName}'
      }
    ]
  }
  dependsOn: [
    edgeSentinelTable
  ]
}

output workspaceResourceId string = workspace.id
output dcrResourceId string = dcr.id
output dcrImmutableId string = dcr.properties.immutableId
output logsIngestionEndpoint string = dcr.properties.endpoints.logsIngestion
output streamName string = streamName
