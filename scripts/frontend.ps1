$ErrorActionPreference = 'Stop'

$repoRoot = Split-Path -Parent $PSScriptRoot
$frontendPath = Join-Path $repoRoot 'frontend'

Push-Location $frontendPath
try {
    npm start
}
finally {
    Pop-Location
}
