param(
    [string]$TesseractRoot = "",
    [switch]$SkipDependencyInstall
)

$ErrorActionPreference = 'Stop'

$repoRoot = Split-Path -Parent $PSScriptRoot
$frontendPath = Join-Path $repoRoot 'frontend'
$backendPath = Join-Path $repoRoot 'backend'
$frontendDist = Join-Path $frontendPath 'dist\frontend\browser'
$runtimeStage = Join-Path $repoRoot 'build\publish-runtime'
$tesseractStage = Join-Path $runtimeStage 'tesseract'
$publishRoot = Join-Path $repoRoot 'publish'
$pyInstallerWork = Join-Path $repoRoot 'build\pyinstaller'
$appName = 'PdfEditor'

function Invoke-PublishStep {
    param([string]$Name, [scriptblock]$Body)
    Write-Host ""
    Write-Host "== $Name =="
    & $Body
}

function Reset-Directory {
    param([string]$Path)
    if (Test-Path -LiteralPath $Path) {
        Remove-Item -LiteralPath $Path -Recurse -Force
    }
    New-Item -ItemType Directory -Path $Path -Force | Out-Null
}

function Ensure-PyInstaller {
    if ($SkipDependencyInstall) {
        return
    }
    $hasPyInstaller = Test-PyInstaller
    if ($hasPyInstaller) {
        return
    }
    python -m pip install -r (Join-Path $backendPath 'requirements-build.txt')
}

function Test-PyInstaller {
    $previousPreference = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    python -c "import PyInstaller" *> $null
    $exitCode = $LASTEXITCODE
    $ErrorActionPreference = $previousPreference
    return $exitCode -eq 0
}

function Find-TesseractExe {
    if ($TesseractRoot -ne "") {
        return Assert-TesseractExe (Join-Path $TesseractRoot 'tesseract.exe')
    }
    $command = Get-Command tesseract.exe -ErrorAction SilentlyContinue
    if ($command -ne $null) {
        return $command.Source
    }
    return Assert-TesseractExe 'C:\Program Files\Tesseract-OCR\tesseract.exe'
}

function Assert-TesseractExe {
    param([string]$Path)
    if (Test-Path -LiteralPath $Path) {
        return (Resolve-Path -LiteralPath $Path).Path
    }
    throw "Tesseract executable not found at $Path; expected tesseract.exe"
}

function Find-Tessdata {
    param([string]$TesseractExe)
    $exeDir = Split-Path -Parent $TesseractExe
    $candidates = TessdataCandidates $exeDir
    foreach ($candidate in $candidates) {
        if (Test-TessdataDirectory $candidate) {
            return (Resolve-Path -LiteralPath $candidate).Path
        }
    }
    throw "tessdata not found near $TesseractExe; expected a folder with *.traineddata files"
}

function TessdataCandidates {
    param([string]$ExeDir)
    $parent = Split-Path -Parent $ExeDir
    $candidates = @($env:TESSDATA_PREFIX, (Join-Path $ExeDir 'tessdata'))
    $candidates += Join-Path $parent 'tessdata'
    $candidates += Join-Path $parent 'share\tessdata'
    $candidates += 'C:\Program Files\Tesseract-OCR\tessdata'
    return $candidates | Where-Object { $_ -ne $null -and $_ -ne '' }
}

function Test-TessdataDirectory {
    param([string]$Path)
    if (-not (Test-Path -LiteralPath $Path)) {
        return $false
    }
    $trainedData = Get-ChildItem -LiteralPath $Path -Filter '*.traineddata' -File -ErrorAction SilentlyContinue
    return $trainedData.Count -gt 0
}

function Copy-TesseractRuntime {
    param([string]$TesseractExe, [string]$TessdataDir)
    Reset-Directory $tesseractStage
    $exeDir = Split-Path -Parent $TesseractExe
    Get-ChildItem -LiteralPath $exeDir -File | Where-Object { $_.Extension -in '.exe', '.dll' } |
        Copy-Item -Destination $tesseractStage -Force
    Copy-Item -LiteralPath $TessdataDir -Destination (Join-Path $tesseractStage 'tessdata') -Recurse -Force
}

function Invoke-PyInstallerBuild {
    Reset-Directory $publishRoot
    python -m PyInstaller --noconfirm --clean --onedir --name $appName `
        --distpath $publishRoot --workpath $pyInstallerWork --specpath $pyInstallerWork `
        --add-data "$frontendDist;frontend_dist" --add-data "$tesseractStage;tesseract" `
        (Join-Path $backendPath 'serve.py')
}

function Write-PublishedReadme {
    $readmePath = Join-Path $publishRoot "$appName\README.txt"
    $lines = @(
        'PDF Editor',
        '',
        'Run PdfEditor.exe and open http://127.0.0.1:8000 if the browser does not open automatically.',
        'No Python, Node.js, or separate Tesseract install is required for this published folder.',
        'Set PDF_EDITOR_PORT, PDF_EDITOR_HOST, or PDF_EDITOR_OPEN_BROWSER=0 to customize startup.'
    )
    Set-Content -LiteralPath $readmePath -Value $lines
}

function Compress-PublishedApp {
    $zipPath = Join-Path $publishRoot "$appName-windows.zip"
    if (Test-Path -LiteralPath $zipPath) {
        Remove-Item -LiteralPath $zipPath -Force
    }
    Compress-Archive -Path (Join-Path $publishRoot "$appName\*") -DestinationPath $zipPath
}

Invoke-PublishStep 'Install backend build dependency' { Ensure-PyInstaller }
Invoke-PublishStep 'Build Angular frontend' { npm --prefix $frontendPath run build }
Invoke-PublishStep 'Stage Tesseract runtime' {
    $tesseractExe = Find-TesseractExe
    $tessdataDir = Find-Tessdata $tesseractExe
    Copy-TesseractRuntime $tesseractExe $tessdataDir
}
Invoke-PublishStep 'Build Windows executable' { Invoke-PyInstallerBuild }
Invoke-PublishStep 'Write package notes' { Write-PublishedReadme }
Invoke-PublishStep 'Create zip package' { Compress-PublishedApp }

Write-Host ""
Write-Host "Published to: $(Join-Path $publishRoot $appName)"
Write-Host "Zip package:  $(Join-Path $publishRoot "$appName-windows.zip")"
