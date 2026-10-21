variable "subscription_id" {
  type        = string
  description = "Azure subscription ID with credits and permission to create resources."
}

variable "location" {
  type        = string
  default     = "centralindia"
  description = "Choose a region permitted by your subscription. VM size availability varies."
}

variable "project_name" {
  type    = string
  default = "cloudpulse"
  validation {
    condition     = can(regex("^[a-z][a-z0-9-]{2,15}$", var.project_name))
    error_message = "Use 3-16 lowercase letters, digits, or hyphens; start with a letter."
  }
}

variable "vm_size" {
  type    = string
  default = "Standard_B1ms"
}

variable "admin_username" {
  type    = string
  default = "cloudpulseadmin"
}

variable "ssh_public_key" {
  type        = string
  description = "Public SSH key contents (one line). Never supply a private key."
}

variable "ssh_allowed_cidr" {
  type        = string
  description = "Your public IPv4 address as a CIDR. SSH is restricted to this range. Use /32 for a static address, or a wider prefix (for example /29) when your ISP assigns addresses from a rotating pool."
  validation {
    condition     = can(cidrnetmask(var.ssh_allowed_cidr)) && can(tonumber(split("/", var.ssh_allowed_cidr)[1])) && tonumber(split("/", var.ssh_allowed_cidr)[1]) >= 24 && tonumber(split("/", var.ssh_allowed_cidr)[1]) <= 32 && var.ssh_allowed_cidr != "0.0.0.0/0"
    error_message = "Supply your own public IPv4 CIDR (a /32 for a fixed address, or a wider prefix such as /29 for a rotating NAT pool). Never 0.0.0.0/0."
  }
}

variable "enable_github_deploy" {
  type        = bool
  default     = false
  description = "Create a managed identity, GitHub OIDC trust, and a role scoped to this VM. Requires role-assignment permission."
}

variable "github_repository" {
  type        = string
  default     = ""
  description = "Exact owner/cloudpulse repository name for GitHub Actions deployment; not the test repository."
  validation {
    condition     = var.github_repository == "" || can(regex("^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$", var.github_repository))
    error_message = "Use an owner/repository name."
  }
}
