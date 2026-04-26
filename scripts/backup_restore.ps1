<#
.SYNOPSIS
    Automated Backup & Restore orchestration for IATB.

.DESCRIPTION
    Creates hourly snapshots of SQLite, DuckDB, config files, and trading state.
    Supports restore with integrity validation.

.PARAMETER Action
    "backup" to create a new snapshot, "restore" to restore from a snapshot,
    "list" to show available backups, "cleanup" to remove old backups.

.PARAMETER BackupId
    Required for restore. The backup ID to restore from (e.g., backup_20260426T090000Z).

.PARAMETER BackupRoot
    Root directory for backup storage. Defaults to ./data/backups.

.PARAMETER RetentionCount
    Number of backups to retain. Defaults to 24 (hourly for 1 day).

.EXAMPLE
    .\scripts\backup_restore.ps1 -Action backup
    .\scripts\backup_restore.ps1 -Action restore -BackupId backup_20260426T090000Z
    .\scripts\backup_restore.ps1 -Action list
    .\scripts\backup_restore.ps1 -Action cleanup -RetentionCount 48
#>

param(
    [Parameter(Mandatory = $true)]
    [ValidateSet("backup", "restore", "list", "cleanup")]
    [string]$Action,

    [Parameter(Mandatory = $false)]
    [string]$BackupId,

    [Parameter(Mandatory = $false)]
    [string]$BackupRoot = (Join-Path (Join-Path (Join-Path $PSScriptRoot "..") "data") "backups"),

    [Parameter(Mandatory = $false)]
    [int]$RetentionCount = 24
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

function Write-Log {
    param([string]$Message, [string]$Level = "INFO")
    $timestamp = (Get-Date).ToUniversalTime().ToString("yyyy-MM-ddTHH:mm:ssZ")
    Write-Host "[$timestamp] [$Level] $Message"
}

function Get-IatbPaths {
    $repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
    $dataDir = Join-Path $repoRoot "data"
    $configDir = Join-Path $repoRoot "config"

    $sqlitePaths = @()
    $auditDb = Join-Path $dataDir "audit.sqlite3"
    if (Test-Path $auditDb) { $sqlitePaths += $auditDb }

    $duckdbPaths = @()
    $ohlcvDb = Join-Path $dataDir "ohlcv.duckdb"
    if (Test-Path $ohlcvDb) { $duckdbPaths += $ohlcvDb }

    $statePath = Join-Path $dataDir "trading_state.json"

    return @{
        RepoRoot    = $repoRoot
        SqlitePaths = $sqlitePaths
        DuckdbPaths = $duckdbPaths
        ConfigDir   = $configDir
        StatePath   = $statePath
    }
}

function Invoke-Backup {
    param(
        [string]$BackupRoot,
        [int]$RetentionCount,
        [array]$SqlitePaths,
        [array]$DuckdbPaths,
        [string]$ConfigDir,
        [string]$StatePath
    )

    Write-Log "Starting backup operation..."

    if (-not (Test-Path $BackupRoot)) {
        New-Item -ItemType Directory -Path $BackupRoot -Force | Out-Null
        Write-Log "Created backup root: $BackupRoot"
    }

    $timestamp = (Get-Date).ToUniversalTime().ToString("yyyyMMddTHHmmssZ")
    $backupDir = Join-Path $BackupRoot "backup_$timestamp"
    New-Item -ItemType Directory -Path $backupDir -Force | Out-Null

    $fileCount = 0
    $manifest = @{
        backup_id     = "backup_$timestamp"
        timestamp_utc = (Get-Date).ToUniversalTime().ToString("o")
        sqlite_files  = @()
        duckdb_files  = @()
        config_files  = @()
        state_file    = $null
        checksums     = @{}
    }

    foreach ($dbPath in $SqlitePaths) {
        if (Test-Path $dbPath) {
            $destFile = Join-Path $backupDir ("sqlite_" + (Split-Path $dbPath -Leaf))
            Copy-Item -Path $dbPath -Destination $destFile -Force
            $hash = (Get-FileHash -Path $destFile -Algorithm SHA256).Hash
            $manifest.sqlite_files += @{ source = $dbPath; dest = (Split-Path $destFile -Leaf) }
            $manifest.checksums[(Split-Path $destFile -Leaf)] = $hash
            $fileCount++
            Write-Log "Backed up SQLite: $dbPath"
        } else {
            Write-Log "SQLite DB not found, skipping: $dbPath" "WARN"
        }
    }

    foreach ($dbPath in $DuckdbPaths) {
        if (Test-Path $dbPath) {
            $destFile = Join-Path $backupDir ("duckdb_" + (Split-Path $dbPath -Leaf))
            Copy-Item -Path $dbPath -Destination $destFile -Force
            $hash = (Get-FileHash -Path $destFile -Algorithm SHA256).Hash
            $manifest.duckdb_files += @{ source = $dbPath; dest = (Split-Path $destFile -Leaf) }
            $manifest.checksums[(Split-Path $destFile -Leaf)] = $hash
            $fileCount++
            Write-Log "Backed up DuckDB: $dbPath"
        } else {
            Write-Log "DuckDB DB not found, skipping: $dbPath" "WARN"
        }
    }

    if (Test-Path $ConfigDir) {
        $configBackupDir = Join-Path $backupDir "configs"
        New-Item -ItemType Directory -Path $configBackupDir -Force | Out-Null
        foreach ($tomlFile in (Get-ChildItem -Path $ConfigDir -Filter "*.toml")) {
            $destFile = Join-Path $configBackupDir $tomlFile.Name
            Copy-Item -Path $tomlFile.FullName -Destination $destFile -Force
            $relKey = "configs/" + $tomlFile.Name
            $hash = (Get-FileHash -Path $destFile -Algorithm SHA256).Hash
            $manifest.config_files += @{ source = $tomlFile.FullName; dest = $relKey }
            $manifest.checksums[$relKey] = $hash
            $fileCount++
            Write-Log "Backed up config: $($tomlFile.Name)"
        }
    }

    if (Test-Path $StatePath) {
        $destFile = Join-Path $backupDir "state_export.json"
        Copy-Item -Path $StatePath -Destination $destFile -Force
        $hash = (Get-FileHash -Path $destFile -Algorithm SHA256).Hash
        $manifest.state_file = @{ source = $StatePath; dest = "state_export.json" }
        $manifest.checksums["state_export.json"] = $hash
        $fileCount++
        Write-Log "Backed up state: $StatePath"
    }

    $manifestPath = Join-Path $backupDir "manifest.json"
    $manifest | ConvertTo-Json -Depth 5 | Set-Content -Path $manifestPath -Encoding UTF8
    Write-Log "Manifest written: $manifestPath"

    Invoke-Cleanup -BackupRoot $BackupRoot -RetentionCount $RetentionCount

    Write-Log "Backup complete: backup_$timestamp ($fileCount files)"
    return $backupDir
}

function Invoke-Restore {
    param(
        [string]$BackupId,
        [string]$BackupRoot,
        [array]$SqlitePaths,
        [array]$DuckdbPaths,
        [string]$ConfigDir,
        [string]$StatePath
    )

    Write-Log "Starting restore from: $BackupId"

    $backupDir = Join-Path $BackupRoot $BackupId
    $manifestPath = Join-Path $backupDir "manifest.json"

    if (-not (Test-Path $manifestPath)) {
        Write-Log "Backup manifest not found: $manifestPath" "ERROR"
        exit 1
    }

    $manifest = Get-Content -Path $manifestPath -Raw | ConvertFrom-Json

    Write-Log "Validating checksums..."
    foreach ($key in $manifest.checksums.PSObject.Properties.Name) {
        $expectedHash = $manifest.checksums.$key
        $filePath = Join-Path $backupDir $key
        if (-not (Test-Path $filePath)) {
            Write-Log "Backup file missing: $key" "ERROR"
            exit 1
        }
        $actualHash = (Get-FileHash -Path $filePath -Algorithm SHA256).Hash.ToLower()
        if ($actualHash -ne $expectedHash.ToLower()) {
            Write-Log "Checksum mismatch for: $key" "ERROR"
            exit 1
        }
    }
    Write-Log "All checksums validated."

    foreach ($entry in $manifest.sqlite_files) {
        $srcFile = Join-Path $backupDir $entry.dest
        if (Test-Path $srcFile) {
            Copy-Item -Path $srcFile -Destination $entry.source -Force
            Write-Log "Restored SQLite: $($entry.source)"
        }
    }

    foreach ($entry in $manifest.duckdb_files) {
        $srcFile = Join-Path $backupDir $entry.dest
        if (Test-Path $srcFile) {
            Copy-Item -Path $srcFile -Destination $entry.source -Force
            Write-Log "Restored DuckDB: $($entry.source)"
        }
    }

    foreach ($entry in $manifest.config_files) {
        $srcFile = Join-Path $backupDir $entry.dest
        if (Test-Path $srcFile) {
            Copy-Item -Path $srcFile -Destination $entry.source -Force
            Write-Log "Restored config: $($entry.source)"
        }
    }

    if ($manifest.state_file) {
        $srcFile = Join-Path $backupDir $manifest.state_file.dest
        if (Test-Path $srcFile) {
            Copy-Item -Path $srcFile -Destination $manifest.state_file.source -Force
            Write-Log "Restored state: $($manifest.state_file.source)"
        }
    }

    Write-Log "Restore complete from: $BackupId"
}

function Invoke-List {
    param([string]$BackupRoot)

    if (-not (Test-Path $BackupRoot)) {
        Write-Log "No backups found (directory does not exist)"
        return
    }

    $backups = Get-ChildItem -Path $BackupRoot -Directory |
        Where-Object { Test-Path (Join-Path $_.FullName "manifest.json") } |
        Sort-Object Name -Descending

    if ($backups.Count -eq 0) {
        Write-Log "No backups found"
        return
    }

    Write-Log "Available backups ($($backups.Count)):"
    foreach ($backup in $backups) {
        $manifest = Get-Content (Join-Path $backup.FullName "manifest.json") -Raw | ConvertFrom-Json
        $fileCount = $manifest.checksums.PSObject.Properties.Name.Count
        Write-Log "  $($backup.Name) | Files: $fileCount | Created: $($manifest.timestamp_utc)"
    }
}

function Invoke-Cleanup {
    param(
        [string]$BackupRoot,
        [int]$RetentionCount
    )

    if (-not (Test-Path $BackupRoot)) { return }

    $backups = Get-ChildItem -Path $BackupRoot -Directory |
        Where-Object { Test-Path (Join-Path $_.FullName "manifest.json") } |
        Sort-Object Name -Descending

    if ($backups.Count -le $RetentionCount) { return }

    $toRemove = $backups | Select-Object -Skip $RetentionCount
    foreach ($backup in $toRemove) {
        Remove-Item -Path $backup.FullName -Recurse -Force
        Write-Log "Removed old backup: $($backup.Name)"
    }
}

$paths = Get-IatbPaths

switch ($Action) {
    "backup"  { Invoke-Backup -BackupRoot $BackupRoot -RetentionCount $RetentionCount -SqlitePaths $paths.SqlitePaths -DuckdbPaths $paths.DuckdbPaths -ConfigDir $paths.ConfigDir -StatePath $paths.StatePath }
    "restore" {
        if (-not $BackupId) {
            Write-Log "BackupId is required for restore action" "ERROR"
            exit 1
        }
        Invoke-Restore -BackupId $BackupId -BackupRoot $BackupRoot -SqlitePaths $paths.SqlitePaths -DuckdbPaths $paths.DuckdbPaths -ConfigDir $paths.ConfigDir -StatePath $paths.StatePath
    }
    "list"    { Invoke-List -BackupRoot $BackupRoot }
    "cleanup" { Invoke-Cleanup -BackupRoot $BackupRoot -RetentionCount $RetentionCount }
}
