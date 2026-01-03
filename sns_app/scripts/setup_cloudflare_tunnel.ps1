param(
  [string]$TunnelName = "sns-app",
  [string]$Hostname = "sns.wp.lundi.com",
  [int]$Port = 5000,
  [switch]$InstallService
)

function Resolve-CloudflaredPath {
  $cmd = Get-Command cloudflared -ErrorAction SilentlyContinue
  if ($cmd) { return $cmd.Path }
  $cand1 = "C:\Program Files\cloudflared\cloudflared.exe"
  $cand2 = "C:\Program Files (x86)\cloudflared\cloudflared.exe"
  if (Test-Path $cand1) { return $cand1 }
  if (Test-Path $cand2) { return $cand2 }
  return $null
}

$cf = Resolve-CloudflaredPath
if (-not $cf) {
  Write-Output 'cloudflared not found. Installing via winget...'
  winget install -e --id Cloudflare.cloudflared
  $cf = Resolve-CloudflaredPath
  if (-not $cf) {
    Write-Error 'Failed to find/install cloudflared. Install manually and rerun.'
    exit 1
  }
}

Write-Output 'Step 1: Login to Cloudflare (opens browser).'
& $cf tunnel login

Write-Output "Step 2: Create named tunnel '$TunnelName'"
$tunnelCreateOutput = & $cf tunnel create $TunnelName 2>&1
Write-Output $tunnelCreateOutput

# Extract Tunnel UUID from output or by listing
$tunnelList = & $cf tunnel list --output json 2>$null | ConvertFrom-Json
$tunnel = $tunnelList | Where-Object { $_.name -eq $TunnelName } | Select-Object -First 1
if (-not $tunnel) {
  Write-Error "Tunnel '$TunnelName' not found after creation."
  exit 1
}
$TunnelId = $tunnel.id
Write-Output "Tunnel ID: $TunnelId"

# Write config.yml under user profile
$cfgDir = Join-Path $env:USERPROFILE ".cloudflared"
$cfgPath = Join-Path $cfgDir "config.yml"
$credPath = Join-Path $cfgDir ("{0}.json" -f $TunnelId)

$cfg = @"
# Cloudflare Tunnel config for persistent public URL
# Hostname: $Hostname

# Tunnel identifier and credentials file

tunnel: $TunnelId
credentials-file: "$credPath"

# Ingress rules (map hostname to local service)
ingress:
  - hostname: $Hostname
    service: http://127.0.0.1:$Port
  - service: http_status:404
"@

New-Item -ItemType Directory -Force -Path $cfgDir | Out-Null
$cfg | Set-Content -Path $cfgPath -Encoding UTF8
Write-Output "Wrote config: $cfgPath"

Write-Output "Step 3: Create DNS route for $Hostname"
& $cf tunnel route dns $TunnelName $Hostname

if ($InstallService.IsPresent) {
  Write-Output 'Step 4: Install Windows service to keep tunnel running.'
  # cloudflared will use config.yml in user profile by default
  & $cf service install
  Write-Output 'Service installed. You can start it from Services or with:'
  Write-Output '  sc start cloudflared'
}

Write-Output 'Setup complete.'
Write-Output "To run the tunnel now: cloudflared tunnel run $TunnelName"
