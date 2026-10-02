# Kubrick — Windows-native Hermes Skill Installer (parity with install.sh)
# Usage:
#   .\install.ps1
#   .\install.ps1 -Creative
#   .\install.ps1 -DryRun
#   .\install.ps1 -Rollback
#   .\install.ps1 -Version
[CmdletBinding()]
param(
    [switch]$Creative,
    [switch]$DryRun,
    [switch]$Rollback,
    [switch]$Version
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$HermesRoot = if ($env:HERMES_HOME) { $env:HERMES_HOME } else { Join-Path $HOME ".hermes" }
$TargetBase = Join-Path $HermesRoot "skills"
$BackupBase = Join-Path $HermesRoot "backups\skills"
$StagingBase = Join-Path $HermesRoot "staging"
$ReceiptBase = Join-Path $HermesRoot "receipts"
$Subdir = if ($Creative) { "creative\" } else { "" }
$Dest = Join-Path $TargetBase ($Subdir + "kubrick")
$LastDestFile = Join-Path $ReceiptBase "kubrick-last-destination"
$LastBackupFile = Join-Path $ReceiptBase "kubrick-last-backup"

if ($Version) {
    Get-Content (Join-Path $Root "VERSION") -Raw
    exit 0
}

if ($DryRun) {
    if ($Rollback) {
        Write-Host "DRY RUN: would restore the last Kubrick backup to $Dest"
    } else {
        Write-Host "DRY RUN: would stage, validate, and atomically install Kubrick to $Dest"
    }
    exit 0
}

New-Item -ItemType Directory -Force -Path $BackupBase, $StagingBase, $ReceiptBase, (Split-Path $Dest) | Out-Null

function Write-Receipt {
    param([string]$Status, [string]$BackupPath = "", [string]$DisplacedPath = "")
    $stamp = (Get-Date).ToUniversalTime().ToString("yyyyMMddTHHmmssZ")
    $receiptPath = Join-Path $ReceiptBase "kubrick-install-$stamp-$PID.json"
    $payload = [ordered]@{
        schema_version = "1.0.0"
        status = $Status
        version = (Get-Content (Join-Path $Root "VERSION") -Raw).Trim()
        destination = $Dest
        backup_path = $(if ($BackupPath) { $BackupPath } else { $null })
        displaced_path = $(if ($DisplacedPath) { $DisplacedPath } else { $null })
        validated_before_activation = $true
        timestamp = (Get-Date).ToUniversalTime().ToString("o")
    }
    ($payload | ConvertTo-Json -Depth 5) + "`n" | Set-Content -Path $receiptPath -Encoding utf8
}

if ($Rollback) {
    if (Test-Path $LastDestFile) { $Dest = (Get-Content $LastDestFile -Raw).Trim() }
    if (-not (Test-Path $LastBackupFile)) { throw "No Kubrick backup receipt is available for rollback." }
    $BackupPath = (Get-Content $LastBackupFile -Raw).Trim()
    if (-not (Test-Path $BackupPath)) { throw "Recorded Kubrick backup is missing: $BackupPath" }
    $stamp = (Get-Date).ToUniversalTime().ToString("yyyyMMddTHHmmssZ")
    $Displaced = Join-Path $BackupBase "kubrick-rollback-displaced-$stamp"
    if (Test-Path $Dest) { Move-Item $Dest $Displaced }
    try {
        Move-Item $BackupPath $Dest
    } catch {
        if (Test-Path $Displaced) { Move-Item $Displaced $Dest }
        throw
    }
    if (Test-Path $Displaced) {
        Set-Content $LastBackupFile $Displaced
    } else {
        Remove-Item $LastBackupFile -ErrorAction SilentlyContinue
    }
    Set-Content $LastDestFile $Dest
    Write-Receipt -Status "ROLLED_BACK" -BackupPath $BackupPath -DisplacedPath $Displaced
    Write-Host "Kubrick rollback completed: $Dest"
    exit 0
}

$stamp = (Get-Date).ToUniversalTime().ToString("yyyyMMddTHHmmssZ")
$Stage = Join-Path $StagingBase "kubrick-$stamp"
New-Item -ItemType Directory -Force -Path $Stage | Out-Null

$exclude = @(".git", ".github", "out", "dist", "__pycache__", ".pytest_cache")
Get-ChildItem -Force $Root | Where-Object { $exclude -notcontains $_.Name } | ForEach-Object {
    Copy-Item $_.FullName -Destination $Stage -Recurse -Force
}
Remove-Item -Recurse -Force (Join-Path $Stage "references\usage") -ErrorAction SilentlyContinue
Remove-Item -Recurse -Force (Join-Path $Stage "references\reports") -ErrorAction SilentlyContinue
Get-ChildItem -Recurse -Directory -Filter "__pycache__" $Stage | Remove-Item -Recurse -Force -ErrorAction SilentlyContinue

Write-Host "Validating staged Kubrick skill..."
& python -c "import yaml, jsonschema" 2>$null
if ($LASTEXITCODE -ne 0) {
    & python -m pip install -r (Join-Path $Stage "requirements.txt")
    if ($LASTEXITCODE -ne 0) { throw "runtime dependency install failed" }
}
& python (Join-Path $Stage "scripts\validate_manifest.py")
if ($LASTEXITCODE -ne 0) { throw "manifest validation failed" }
& python (Join-Path $Stage "scripts\validate_hermes_skill.py")
if ($LASTEXITCODE -ne 0) { throw "skill validation failed" }
& python (Join-Path $Stage "scripts\validate_pattern_corpus.py")
if ($LASTEXITCODE -ne 0) { throw "corpus validation failed" }
& python (Join-Path $Stage "scripts\audit_release_version.py") --strict
if ($LASTEXITCODE -ne 0) { throw "release version audit failed" }

$BackupPath = ""
if (Test-Path $Dest) {
    $BackupPath = Join-Path $BackupBase "kubrick-$stamp"
    Move-Item $Dest $BackupPath
}

try {
    Move-Item $Stage $Dest
} catch {
    if ($BackupPath -and (Test-Path $BackupPath)) { Move-Item $BackupPath $Dest }
    throw "Activation failed; previous Kubrick installation was restored."
}

Set-Content $LastDestFile $Dest
if ($BackupPath) {
    Set-Content $LastBackupFile $BackupPath
} else {
    Remove-Item $LastBackupFile -ErrorAction SilentlyContinue
}
Write-Receipt -Status "INSTALLED" -BackupPath $BackupPath
Write-Host "Kubrick installed successfully."
Write-Host "Location: $Dest"
