param(
  [string]$TunnelName = "sns-app"
)

# Run the named tunnel using the config at %USERPROFILE%\.cloudflared\config.yml
cloudflared tunnel run $TunnelName
