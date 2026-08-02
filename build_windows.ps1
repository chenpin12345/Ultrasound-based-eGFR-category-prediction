$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$DistProject = Join-Path $ProjectRoot "dist\project"

python -m PyInstaller --clean --noconfirm --distpath $DistProject app.spec

$NestedExe = Join-Path $DistProject "app.exe"
$ModelsDir = Join-Path $DistProject "models"
New-Item -ItemType Directory -Force -Path $ModelsDir | Out-Null

Write-Host ""
Write-Host "Build complete."
Write-Host "End-user folder:"
Write-Host "  $NestedExe"
Write-Host "  $ModelsDir\*.pth"
