output "resource_group" {
  value = azurerm_resource_group.main.name
}
output "vm_name" {
  value = azurerm_linux_virtual_machine.main.name
}
output "vm_resource_id" {
  value = azurerm_linux_virtual_machine.main.id
}
output "public_ip" {
  value = azurerm_public_ip.main.ip_address
}
output "hostname" {
  value = azurerm_public_ip.main.fqdn
}
output "dashboard_url" {
  value = "https://${azurerm_public_ip.main.fqdn}"
}
output "webhook_url" {
  value = "https://${azurerm_public_ip.main.fqdn}/webhook/github"
}
output "ssh_command" {
  value = "ssh ${var.admin_username}@${azurerm_public_ip.main.fqdn}"
}
output "github_azure_client_id" {
  value = try(azurerm_user_assigned_identity.github[0].client_id, "")
}
output "azure_tenant_id" {
  value = data.azurerm_client_config.current.tenant_id
}
output "azure_subscription_id" {
  value = var.subscription_id
}
