param(
  [int]$Port = 5000
)

# Quick public share using Cloudflare Tunnel (no account). Requires cloudflared in PATH.
# If cloudflared is not installed, print instructions.

function Test-Command {
  param([string]$Name)
  $null -ne (Get-Command $Name -ErrorAction SilentlyContinue)
}

if (-not (Test-Command -Name 'cloudflared')) {
  Write-Warning 'cloudflared not found. Install from https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/downloads/ and re-run.'
  Write-Output 'Or with winget:'
  Write-Output '  winget install Cloudflare.cloudflared'
  exit 1
}

Write-Output "Publishing http://127.0.0.1:$Port via Cloudflare Tunnel..."
# This will print a public https://xxxx.trycloudflare.com URL
cloudflared tunnel --url ("http://127.0.0.1:{0}" -f $Port)
