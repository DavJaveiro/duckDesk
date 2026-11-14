# DuckDesk installer build (docs/06 step 3): end-to-end on a clean machine.
# Usage:  powershell -ExecutionPolicy Bypass -File scripts\build_installer.ps1
# Prereqs: uv no PATH, Inno Setup 6 (winget install JRSoftware.InnoSetup).

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

Write-Host "== 1/4 uv sync --frozen" -ForegroundColor Cyan
uv sync --frozen

Write-Host "== 2/4 verify assets" -ForegroundColor Cyan
uv run python scripts/fetch_assets.py --verify

# versao do pyproject.toml -> define do Inno
$version = (Select-String -Path pyproject.toml -Pattern '^version = "([^"]+)"').Matches[0].Groups[1].Value
Write-Host "   versao: $version"

# pagina de licenca: Inno so aceita .txt/.rtf (docs/06)
Copy-Item THIRD_PARTY_NOTICES.md installer\licenca.txt -Force

Write-Host "== 3/4 PyInstaller (onedir)" -ForegroundColor Cyan
uv run pyinstaller installer/duckdesk.spec --noconfirm --clean
if (-not (Test-Path "dist\DuckDesk\DuckDesk.exe")) { throw "PyInstaller nao gerou dist\DuckDesk\DuckDesk.exe" }

Write-Host "== 4/4 Inno Setup" -ForegroundColor Cyan
$iscc = "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe"
if (-not (Test-Path $iscc)) { $iscc = "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe" }
if (-not (Test-Path $iscc)) { throw "ISCC.exe nao encontrado (winget install JRSoftware.InnoSetup)" }
& $iscc /DMyAppVersion=$version installer\duckdesk.iss
if ($LASTEXITCODE -ne 0) { throw "ISCC falhou: $LASTEXITCODE" }

$exe = Get-Item "installer\out\DuckDesk-Setup-$version.exe"
$size = [math]::Round($exe.Length / 1MB, 1)
$hash = (Get-FileHash $exe.FullName -Algorithm SHA256).Hash.ToLower()
$dist = (Get-Item "dist\DuckDesk").FullName
$distSize = [math]::Round(((Get-ChildItem $dist -Recurse | Measure-Object Length -Sum).Sum) / 1MB, 1)

Write-Host ""
Write-Host "Instalador : $($exe.FullName)" -ForegroundColor Green
Write-Host "Tamanho    : $size MB (limite 350 MB)"
Write-Host "Instalado  : $distSize MB em dist\DuckDesk (limite 900 MB)"
Write-Host "SHA-256    : $hash" -ForegroundColor Green
