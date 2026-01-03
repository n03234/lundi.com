param(
  [string]$PythonPath = "C:\Users\User\AppData\Local\Programs\Python\Python312\python.exe",
  [string]$AppPath = "d:\python-hasegawa\sns_app\app.py",
  [string]$ListenHost = "0.0.0.0",
  [int]$Port = 5000,
  [int]$Debug = 0,
  [int]$Open = 1
)

if (-not (Test-Path $PythonPath)) {
  Write-Warning "Python not found at $PythonPath. Trying 'python' on PATH."
  $PythonPath = "python"
}

$env:SNS_HOST = $ListenHost
$env:SNS_PORT = "$Port"
$env:SNS_DEBUG = "$Debug"

# Start server in a new window to keep current shell free
$cmd = '"' + $PythonPath + '" "' + $AppPath + '"'
Start-Process -FilePath powershell.exe -ArgumentList "-NoExit","-Command",$cmd -WorkingDirectory (Split-Path $AppPath)

Write-Output "Server starting on http://127.0.0.1:$Port (host=$ListenHost, debug=$Debug)"
Start-Sleep -Seconds 1

# Wait for health up to ~10 seconds
$ok = $false
for ($i=0; $i -lt 20; $i++) {
  try {
    $r = Invoke-WebRequest -Uri ("http://127.0.0.1:{0}/health" -f $Port) -TimeoutSec 1 -UseBasicParsing
    if ($r.StatusCode -eq 200) { $ok = $true; break }
  } catch { Start-Sleep -Milliseconds 500 }
}

if ($ok) {
  Write-Output "Health OK."
  if ($Open -eq 1) { Start-Process ("http://127.0.0.1:{0}/" -f $Port) }
} else {
  Write-Warning "Health check did not succeed yet. Try again shortly."
}
