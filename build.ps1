<#
.SYNOPSIS
  Build WildcatMD.exe (PyInstaller) and the Program Files installer (Inno Setup).

.EXAMPLE
  ./build.ps1                 # full build -> dist\installer\WildcatMD-Setup-<ver>.exe
  ./build.ps1 -SkipInstaller  # just dist\WildcatMD\WildcatMD.exe
#>
param(
    [switch]$SkipInstaller,
    [string]$D2Path,
    [string]$IsccPath
)
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

$version = (uv run python -c "import wildcat_markdown_viewer as m; print(m.__version__)").Trim()
Write-Host "==> Wildcat Markdown Viewer $version"

Write-Host "==> Syncing environment (uv)"
uv sync --frozen
if ($LASTEXITCODE) { throw "uv sync failed" }

Write-Host "==> PyInstaller"
uv run pyinstaller installer/WildcatMD.spec --noconfirm --clean --distpath dist --workpath build
if ($LASTEXITCODE) { throw "PyInstaller failed" }

# Bundle d2.exe so diagrams work without a separate D2 install.
if (-not $D2Path) {
    $cmd = Get-Command d2 -ErrorAction SilentlyContinue
    $D2Path = if ($cmd) { $cmd.Source } else { "$env:ProgramFiles\D2\d2.exe" }
}
if (Test-Path $D2Path) {
    Write-Host "==> Bundling $D2Path"
    $d2Dir = New-Item -ItemType Directory -Force "dist\WildcatMD\d2"
    Copy-Item $D2Path $d2Dir -Force
    $notices = Join-Path (Split-Path $D2Path) "THIRD_PARTY_NOTICES.txt"
    if (Test-Path $notices) { Copy-Item $notices $d2Dir -Force }
    Copy-Item "installer\D2-LICENSE-NOTICE.txt" $d2Dir -Force
} else {
    Write-Warning "d2.exe not found - the build will rely on a d2 on the user's PATH."
}

if ($SkipInstaller) { Write-Host "==> Done: dist\WildcatMD\WildcatMD.exe"; return }

if (-not $IsccPath) {
    $IsccPath = @(
        "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe",
        "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
        "$env:ProgramFiles\Inno Setup 6\ISCC.exe"
    ) | Where-Object { Test-Path $_ } | Select-Object -First 1
}
if (-not $IsccPath) { throw "Inno Setup 6 (ISCC.exe) not found. Install it: winget install JRSoftware.InnoSetup" }

Write-Host "==> Inno Setup"
& $IsccPath "/DAppVersion=$version" "installer\WildcatMD.iss"
if ($LASTEXITCODE) { throw "ISCC failed" }
Write-Host "==> Done: dist\installer\WildcatMD-Setup-$version.exe"
