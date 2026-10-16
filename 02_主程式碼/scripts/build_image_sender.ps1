$ErrorActionPreference = 'Stop'
# Builds the portable A-side sender, its zip and hash manifest, then runs the
# packaged self-test from an independent extracted copy (not from the build tree).
$projectRoot = Split-Path -Parent $PSScriptRoot
$python = Join-Path $projectRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $python)) { throw 'Run setup.bat first.' }
$workspaceRoot = Split-Path -Parent $projectRoot
$buildRoot = Join-Path $workspaceRoot '03_模型與影像資料\runtime\build\sender'
$delivery = Join-Path $projectRoot 'delivery'
& $python -m PyInstaller --noconfirm --clean --onedir --windowed --name UltrasoundImageSender --distpath "$delivery" --workpath "$buildRoot\work" --specpath "$buildRoot" --add-data "$projectRoot\tools\image_sender\index.html;." --add-data "$projectRoot\tools\image_sender\sender.js;." "$projectRoot\tools\image_sender\sender.py"
if ($LASTEXITCODE -ne 0) { throw 'Sender build failed.' }
$zip = Join-Path $delivery 'UltrasoundImageSender-portable.zip'
if (Test-Path -LiteralPath $zip) { Remove-Item -LiteralPath $zip }
Compress-Archive -Path (Join-Path $delivery 'UltrasoundImageSender') -DestinationPath $zip
# Self-test from a fresh extraction in a temporary folder outside the project.
$check = Join-Path ([IO.Path]::GetTempPath()) ('sender-selftest-' + [guid]::NewGuid().ToString('N'))
Expand-Archive -LiteralPath $zip -DestinationPath $check
$report = Join-Path $check 'selftest.json'
$process = Start-Process -FilePath (Join-Path $check 'UltrasoundImageSender\UltrasoundImageSender.exe') -ArgumentList @('--self-test', "`"$report`"") -Wait -PassThru
if ($process.ExitCode -ne 0 -or -not (Test-Path -LiteralPath $report)) { throw 'Packaged self-test failed.' }
$selftest = Get-Content -LiteralPath $report -Raw -Encoding utf8 | ConvertFrom-Json
if (-not $selftest.ok -or -not $selftest.portable -or $selftest.protocol -ne 2) { throw 'Packaged self-test reported a wrong build.' }
Remove-Item -LiteralPath $check -Recurse -Force
$manifest = [ordered]@{
  file = 'UltrasoundImageSender-portable.zip'; bytes = (Get-Item -LiteralPath $zip).Length
  sha256 = (Get-FileHash -LiteralPath $zip -Algorithm SHA256).Hash.ToLower()
  exe_sha256 = (Get-FileHash -LiteralPath (Join-Path $delivery 'UltrasoundImageSender\UltrasoundImageSender.exe') -Algorithm SHA256).Hash.ToLower()
  version = $selftest.version; protocol = $selftest.protocol; case_schema = $selftest.case_schema
  source_sha256 = (Get-FileHash -LiteralPath "$projectRoot\tools\image_sender\sender.py" -Algorithm SHA256).Hash.ToLower()
  built = (Get-Date).ToString('s'); selftest = 'passed from an independent extracted copy'
}
$manifest | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $delivery 'SHA256.json') -Encoding utf8
Write-Output "Portable tool: $delivery\UltrasoundImageSender\UltrasoundImageSender.exe (version $($selftest.version), protocol $($selftest.protocol))"
