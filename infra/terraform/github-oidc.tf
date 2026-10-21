data "azurerm_client_config" "current" {}

resource "azurerm_user_assigned_identity" "github" {
  count               = var.enable_github_deploy ? 1 : 0
  name                = "github-${local.name}"
  location            = var.location
  resource_group_name = azurerm_resource_group.main.name
  tags                = local.tags
  lifecycle {
    precondition {
      condition     = var.github_repository != ""
      error_message = "Set github_repository to your CloudPulse application's owner/repo."
    }
  }
}

resource "azurerm_federated_identity_credential" "github" {
  count               = var.enable_github_deploy ? 1 : 0
  name                = "github-main"
  resource_group_name = azurerm_resource_group.main.name
  parent_id           = azurerm_user_assigned_identity.github[0].id
  audience            = ["api://AzureADTokenExchange"]
  issuer              = "https://token.actions.githubusercontent.com"
  subject             = "repo:${var.github_repository}:ref:refs/heads/main"
}

resource "azurerm_role_assignment" "github_deploy" {
  count                            = var.enable_github_deploy ? 1 : 0
  scope                            = azurerm_linux_virtual_machine.main.id
  role_definition_name             = "Virtual Machine Contributor"
  principal_id                     = azurerm_user_assigned_identity.github[0].principal_id
  skip_service_principal_aad_check  = true
}
