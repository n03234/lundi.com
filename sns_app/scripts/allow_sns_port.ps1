# Requires: Administrator PowerShell
param(
  [int]$Port = 5000,
  [string]$Profile = 'Private'
)

# Check admin
$curr = [Security.Principal.WindowsIdentity]::GetCurrent()
$pr = New-Object Security.Principal.WindowsPrincipal($curr)
$IsAdmin = $pr.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $IsAdmin) {
  Write-Error "Administrator privileges required. Right-click PowerShell and 'Run as administrator'."
  exit 1
}

# Add rule if not exists
$ruleName = "SNS App $Port"
$existing = Get-NetFirewallRule -DisplayName $ruleName -ErrorAction SilentlyContinue
if (-not $existing) {
  New-NetFirewallRule -DisplayName $ruleName -Direction Inbound -Protocol TCP -LocalPort $Port -Action Allow -Profile $Profile | Out-Null
  Write-Output "Firewall rule added: $ruleName on port $Port ($Profile)."
} else {
  Write-Output "Firewall rule already exists: $ruleName"
}
