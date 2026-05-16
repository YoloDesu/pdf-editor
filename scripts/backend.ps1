$ErrorActionPreference = 'Stop'

$repoRoot = Split-Path -Parent $PSScriptRoot
$backendPath = Join-Path $repoRoot 'backend'

Push-Location $backendPath
try {
    python -m uvicorn main:app --host 127.0.0.1 --port 8000
}
finally {
    Pop-Location
}
