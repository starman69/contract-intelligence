@description('Event Grid system topic name.')
param topicName string
param location string
param tags object

@description('Resource id of the Storage Account that is the source.')
param storageAccountId string

@description('Resource id of the Function App that hosts the Event Grid trigger.')
param functionAppResourceId string

@description('Function name (Event Grid-triggered) inside the Function App.')
param functionName string

resource topic 'Microsoft.EventGrid/systemTopics@2023-12-15-preview' = {
  name: topicName
  location: location
  tags: tags
  properties: {
    source: storageAccountId
    topicType: 'Microsoft.Storage.StorageAccounts'
  }
}

// Subscription: BlobCreated under raw/contracts/  -->  Function (Event Grid trigger)
// Note: When using Event Grid trigger bindings on a Function, the destination is the
// Microsoft.Web/sites/functions resource id. With Azure Functions runtime v4 +
// the Event Grid trigger binding, this is the standard wiring.
resource subscription 'Microsoft.EventGrid/systemTopics/eventSubscriptions@2023-12-15-preview' = {
  parent: topic
  name: 'raw-contracts-created'
  properties: {
    destination: {
      endpointType: 'AzureFunction'
      properties: {
        resourceId: '${functionAppResourceId}/functions/${functionName}'
        maxEventsPerBatch: 1
        preferredBatchSizeInKilobytes: 64
      }
    }
    filter: {
      includedEventTypes: [
        'Microsoft.Storage.BlobCreated'
      ]
      subjectBeginsWith: '/blobServices/default/containers/raw/blobs/contracts/'
      enableAdvancedFilteringOnArrays: true
    }
    eventDeliverySchema: 'EventGridSchema'
    retryPolicy: {
      maxDeliveryAttempts: 30
      eventTimeToLiveInMinutes: 1440
    }
  }
}

output topicId string = topic.id
output topicName string = topic.name
