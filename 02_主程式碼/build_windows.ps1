$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$DistProject = Join-Path $ProjectRoot "delivery\legacy-desktop"

$buildRoot = Join-Path (Split-Path -Parent $ProjectRoot) '03_模型與影像資料\runtime\build\legacy'
Push-Location $ProjectRoot
try {
    & "$ProjectRoot\.venv\Scripts\python.exe" -m PyInstaller --clean --noconfirm --workpath $buildRoot --distpath $DistProject "$ProjectRoot\app.spec"
    if ($LASTEXITCODE -ne 0) { throw 'Legacy desktop build failed.' }
} finally { Pop-Location }

$NestedExe = Join-Path $DistProject "app.exe"
$ModelsDir = Join-Path $DistProject "models"
New-Item -ItemType Directory -Force -Path $ModelsDir | Out-Null

Write-Host ""
Write-Host "Build complete."
Write-Host "End-user folder:"
Write-Host "  $NestedExe"
Write-Host "  $ModelsDir\*.pth"
