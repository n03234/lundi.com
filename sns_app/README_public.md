# Public URL (Persistent)

This project includes scripts to publish the app to the public internet with a persistent URL via Cloudflare Tunnel.

## Requirements
- A domain managed on Cloudflare (e.g., `lundi.com`)
- `cloudflared` installed (`winget install Cloudflare.cloudflared`)
- The app running locally (Waitress or Flask)

## Steps (one-time setup)
1. Start the app locally (Waitress recommended):
   ```powershell
   powershell -ExecutionPolicy Bypass -File d:\python-hasegawa\sns_app\scripts\run_waitress.ps1
   ```
2. Run the tunnel setup (opens browser to login):
   ```powershell
   powershell -ExecutionPolicy Bypass -File d:\python-hasegawa\sns_app\scripts\setup_cloudflare_tunnel.ps1 -TunnelName sns-app -Hostname sns.wp.lundi.com -Port 5000 -InstallService
   ```
   - This creates a named tunnel and DNS record `sns.wp.lundi.com` pointing to the tunnel, and writes `%USERPROFILE%\.cloudflared\config.yml`.
   - With `-InstallService`, Cloudflare Tunnel runs as a Windows service so the URL remains available.

## Run Tunnel (manual)
```powershell
powershell -ExecutionPolicy Bypass -File d:\python-hasegawa\sns_app\scripts\run_cloudflare_tunnel.ps1 -TunnelName sns-app
```

## Notes
- Change `-Hostname` to your desired subdomain.
- Ensure port 5000 is reachable locally and Windows Firewall allows local loopback (for LAN access, add inbound rule).
- To uninstall the service:
  ```powershell
  cloudflared service uninstall
  ```
