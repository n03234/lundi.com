param(
  [string]$AppImport = "sns_app.app:app",
  [string]$Listen = "0.0.0.0:5000",
  [int]$Threads = 8
)

# Disable debug by default for public serving
$env:SNS_DEBUG = '0'

# Prefer the installed waitress-serve entrypoint
try {
  waitress-serve --listen $Listen --threads $Threads $AppImport
} catch {
  # Fallback via python -m waitress
  & "C:\Users\User\AppData\Local\Programs\Python\Python312\python.exe" -m waitress --listen $Listen --threads $Threads $AppImport
}
