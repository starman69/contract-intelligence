using '../main.bicep'

param env = 'dev'
param location = 'eastus2'

// Replace with your Entra ID security group's object id (preferred) or a user object id.
// Group is recommended so multiple developers / the Function MI can be admins without churn.
param aadAdminObjectId = '00000000-0000-0000-0000-000000000000'
param aadAdminLogin = 'sg-contracts-poc-admins'

// Replace with your workstation's public IP (curl ifconfig.me).
// Only this IP can reach the SQL server's public endpoint at POC.
param devClientIp = '0.0.0.0'

// Capacity is in 1000-token units (e.g. 100 = 100K TPM).
// Tune to match your Azure OpenAI quota in the chosen region.
param openAiCapacityTpm = {
  gpt4oMini: 100
  gpt4o: 30
  embedding: 50
}
