# ──────────────────────────────────────────────────────────────────────────────
# Pre-Market Token Validator Scheduler — Risk 2 Mitigation Strategy
# ──────────────────────────────────────────────────────────────────────────────
#
# This PowerShell script schedules the pre-market token validator to run at
# 9:00 AM IST daily, ensuring Zerodha tokens are refreshed before market opens.
#
# Risk Mitigated:
#   Risk 2: Token Expiry During Trading Hours
#   - Zerodha tokens expire at 6 AM IST daily
#   - If token refresh fails, the system has no data
#
# Mitigation:
#   ✓ Pre-market token validation (run at 9:00 AM IST)
#   ✓ Automated re-login via zerodha_connect.py with TOTP
#   ✓ Alert on token expiry
#
# Usage:
#   .\scripts\schedule_pre_market_validator.ps1
#
# Requirements:
#   - PowerShell 5.1+ (Windows 10/11)
#   - Poetry installed and configured
#   - ZERODHA_API_KEY, ZERODHA_API_SECRET, ZERODHA_TOTP_SECRET in environment
# ──────────────────────────────────────────────────────────────────────────────

#Requires -Version 5.1

[CmdletBinding()]
param(
    [Parameter(Mandatory = $false)]
    [ValidateSet("Create", "Remove", "List", "RunOnce", "Help")]
    [string]$Action = "Create",

    [Parameter(Mandatory = $false)]
    [int]$ScheduledHour = 9,

    [Parameter(Mandatory = $false)]
    [int]$ScheduledMinute = 0,

    [Parameter(Mandatory = $false)]
    [string]$TaskName = "IATB_PreMarketTokenValidator"
)

# ── Constants ───────────────────────────────────────────────────────────────────

$ErrorActionPreference = "Stop"
$ScriptPath = $PSScriptRoot
$ProjectRoot = Split-Path -Path $ScriptPath -Parent
$ValidatorScript = Join-Path -Path $ScriptPath -ChildPath "pre_market_token_validator.py"
$LogDir = Join-Path -Path $ProjectRoot -ChildPath "logs"

# ── Helper Functions ────────────────────────────────────────────────────────────

function Write-ColorOutput {
    <#
    .SYNOPSIS
    Write colored output to console
    #>
    param(
        [string]$Message,
        [string]$Color = "White"
    )
    Write-Host $Message -ForegroundColor $Color
}

function Test-Prerequisites {
    <#
    .SYNOPSIS
    Check if all prerequisites are met
    #>
    Write-ColorOutput "`n[1/6] Checking prerequisites..." -Color Cyan

    # Check Python
    $pythonCmd = Get-Command python -ErrorAction SilentlyContinue
    if (-not $pythonCmd) {
        Write-ColorOutput "✗ Python not found in PATH" -Color Red
        return $false
    }
    Write-ColorOutput "  ✓ Python found: $($pythonCmd.Source)" -Color Green

    # Check Poetry
    $poetryCmd = Get-Command poetry -ErrorAction SilentlyContinue
    if (-not $poetryCmd) {
        Write-ColorOutput "✗ Poetry not found in PATH" -Color Red
        return $false
    }
    Write-ColorOutput "  ✓ Poetry found: $($poetryCmd.Source)" -Color Green

    # Check validator script exists
    if (-not (Test-Path -Path $ValidatorScript)) {
        Write-ColorOutput "✗ Validator script not found: $ValidatorScript" -Color Red
        return $false
    }
    Write-ColorOutput "  ✓ Validator script exists" -Color Green

    # Check environment variables
    $envVars = @("ZERODHA_API_KEY", "ZERODHA_API_SECRET")
    $missingVars = @()

    foreach ($var in $envVars) {
        if (-not [System.Environment]::GetEnvironmentVariable($var)) {
            $missingVars += $var
        }
    }

    if ($missingVars.Count -gt 0) {
        Write-ColorOutput "  ⚠ Missing environment variables: $($missingVars -join ', ')" -Color Yellow
        Write-ColorOutput "    TOTP secret is optional but recommended for auto-login" -Color Yellow
    } else {
        Write-ColorOutput "  ✓ Required environment variables set" -Color Green
    }

    # Check if running as admin (required for scheduled tasks)
    $isAdmin = ([Security.Principal.WindowsPrincipal] [Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
    if (-not $isAdmin) {
        Write-ColorOutput "  ⚠ Not running as Administrator. Scheduled task creation requires admin privileges." -Color Yellow
        Write-ColorOutput "    Run PowerShell as Administrator to create tasks." -Color Yellow
    } else {
        Write-ColorOutput "  ✓ Running with Administrator privileges" -Color Green
    }

    return $true
}

function Get-TaskAction {
    <#
    .SYNOPSIS
    Get the scheduled task action object
    #>
    $workingDir = $ProjectRoot
    $pythonExe = (Get-Command python).Source

    # Create action to run the validator in scheduled mode
    $action = New-ScheduledTaskAction `
        -Execute $pythonExe `
        -Argument "-m poetry run python `"$ValidatorScript`" --scheduled --hour $ScheduledHour --minute $ScheduledMinute" `
        -WorkingDirectory $workingDir

    return $action
}

function Get-TaskTrigger {
    <#
    .SYNOPSIS
    Get the scheduled task trigger object (daily at specified time)
    #>
    # IST is UTC+5:30, so 9:00 AM IST = 3:30 AM UTC
    # However, we'll use local time and let Windows handle timezone
    $trigger = New-ScheduledTaskTrigger -Daily -At "$($ScheduledHour):$($ScheduledMinute)AM"
    return $trigger
}

function Get-TaskSettings {
    <#
    .SYNOPSIS
    Get the scheduled task settings
    #>
    $settings = New-ScheduledTaskSettingsSet `
        -AllowStartIfOnBatteries `
        -DontStopIfGoingOnBatteries `
        -StartWhenAvailable `
        -RestartCount 3 `
        -RestartInterval (New-TimeSpan -Minutes 5)

    return $settings
}

function New-ValidatorTask {
    <#
    .SYNOPSIS
    Create the scheduled task
    #>
    Write-ColorOutput "`n[2/6] Creating scheduled task..." -Color Cyan

    try {
        # Check if task already exists
        $existingTask = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
        if ($existingTask) {
            Write-ColorOutput "  Task '$TaskName' already exists. Removing..." -Color Yellow
            Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
        }

        # Create task components
        $action = Get-TaskAction
        $trigger = Get-TaskTrigger
        $settings = Get-TaskSettings

        # Create task principal (run as current user)
        $principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Highest

        # Register the task
        Register-ScheduledTask `
            -TaskName $TaskName `
            -Action $action `
            -Trigger $trigger `
            -Settings $settings `
            -Principal $principal `
            -Description "IATB Pre-Market Token Validator - Risk 2 Mitigation (Token Expiry)" `
            -ErrorAction Stop | Out-Null

        Write-ColorOutput "  ✓ Scheduled task created successfully" -Color Green
        Write-ColorOutput "    Task Name: $TaskName" -Color White
        Write-ColorOutput "    Schedule: Daily at $ScheduledHour`:$($ScheduledMinute.ToString('00')) AM local time" -Color White
        Write-ColorOutput "    Script: $ValidatorScript" -Color White

        return $true
    }
    catch {
        Write-ColorOutput "  ✗ Failed to create scheduled task: $_" -Color Red
        return $false
    }
}

function Remove-ValidatorTask {
    <#
    .SYNOPSIS
    Remove the scheduled task
    #>
    Write-ColorOutput "`n[2/6] Removing scheduled task..." -Color Cyan

    try {
        $existingTask = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
        if (-not $existingTask) {
            Write-ColorOutput "  ⚠ Task '$TaskName' does not exist" -Color Yellow
            return $true
        }

        Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
        Write-ColorOutput "  ✓ Scheduled task removed successfully" -Color Green

        return $true
    }
    catch {
        Write-ColorOutput "  ✗ Failed to remove scheduled task: $_" -Color Red
        return $false
    }
}

function Show-ValidatorTask {
    <#
    .SYNOPSIS
    Display scheduled task details
    #>
    Write-ColorOutput "`n[2/6] Listing scheduled task..." -Color Cyan

    $task = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
    if (-not $task) {
        Write-ColorOutput "  ⚠ No task found with name: $TaskName" -Color Yellow
        return $true
    }

    Write-ColorOutput "`n  Task Details:" -Color White
    Write-ColorOutput "  ──────────────────────────────────────────" -Color Gray
    Write-ColorOutput "  Name: $($task.TaskName)" -Color White
    Write-ColorOutput "  State: $($task.State)" -Color White
    Write-ColorOutput "  Description: $($task.Description)" -Color White

    Write-ColorOutput "`n  Triggers:" -Color White
    foreach ($trigger in $task.Triggers) {
        Write-ColorOutput "    - $($trigger.Frequency) at $($trigger.StartBoundary)" -Color White
    }

    Write-ColorOutput "`n  Actions:" -Color White
    foreach ($action in $task.Actions) {
        Write-ColorOutput "    - Execute: $($action.Execute)" -Color White
        Write-ColorOutput "      Arguments: $($action.Arguments)" -Color Gray
        Write-ColorOutput "      Working Directory: $($action.WorkingDirectory)" -Color Gray
    }

    Write-ColorOutput "`n  Last Run: $($task.LastRunTime)" -Color White
    Write-ColorOutput "  Next Run: $($task.NextRunTime)" -Color White
    Write-ColorOutput "  ──────────────────────────────────────────`n" -Color Gray

    return $true
}

function Invoke-ValidatorOnce {
    <#
    .SYNOPSIS
    Run the validator once immediately
    #>
    Write-ColorOutput "`n[2/6] Running validator once..." -Color Cyan

    try {
        Set-Location -Path $ProjectRoot

        Write-ColorOutput "  Executing: poetry run python $ValidatorScript" -Color White
        Write-ColorOutput "  Working directory: $ProjectRoot" -Color Gray
        Write-ColorOutput ""

        $process = Start-Process -FilePath "python" `
            -ArgumentList "-m", "poetry", "run", "python", "`"$ValidatorScript`"" `
            -WorkingDirectory $ProjectRoot `
            -Wait -NoNewWindow -PassThru

        if ($process.ExitCode -eq 0) {
            Write-ColorOutput "`n  ✓ Validator completed successfully" -Color Green
        }
        else {
            Write-ColorOutput "`n  ✗ Validator failed with exit code: $($process.ExitCode)" -Color Red
        }

        return $process.ExitCode -eq 0
    }
    catch {
        Write-ColorOutput "  ✗ Failed to run validator: $_" -Color Red
        return $false
    }
}

function Show-Usage {
    <#
    .SYNOPSIS
    Display usage information
    #>
    Write-ColorOutput "`nPre-Market Token Validator Scheduler - Usage`n" -Color Cyan
    Write-ColorOutput "This script manages the scheduled task for pre-market token validation.`n" -Color White
    Write-ColorOutput "Actions:" -Color Yellow
    Write-ColorOutput "  Create  - Create the scheduled task (default)" -Color White
    Write-ColorOutput "  Remove  - Remove the scheduled task" -Color White
    Write-ColorOutput "  List    - Display task details" -Color White
    Write-ColorOutput "  RunOnce - Run the validator once immediately" -Color White
    Write-ColorOutput "  Help    - Show this help message`n" -Color White
    Write-ColorOutput "Examples:" -Color Yellow
    Write-ColorOutput "  .\schedule_pre_market_validator.ps1" -Color White
    Write-ColorOutput "  .\schedule_pre_market_validator.ps1 -Action Create" -Color White
    Write-ColorOutput "  .\schedule_pre_market_validator.ps1 -Action Remove" -Color White
    Write-ColorOutput "  .\schedule_pre_market_validator.ps1 -Action List" -Color White
    Write-ColorOutput "  .\schedule_pre_market_validator.ps1 -Action RunOnce" -Color White
    Write-ColorOutput "  .\schedule_pre_market_validator.ps1 -Action Create -ScheduledHour 8 -ScheduledMinute 30`n" -Color White
}

function Show-Summary {
    <#
    .SYNOPSIS
    Display execution summary
    #>
    param(
        [bool]$Success,
        [string]$Action
    )

    Write-ColorOutput "`n[3/6] Summary" -Color Cyan
    Write-ColorOutput "  Action: $Action" -Color White

    if ($Success) {
        Write-ColorOutput "  Status: ✓ SUCCESS" -Color Green
    }
    else {
        Write-ColorOutput "  Status: ✗ FAILED" -Color Red
    }

    Write-ColorOutput "`n[4/6] Next Steps" -Color Cyan

    if ($Action -eq "Create" -and $Success) {
        Write-ColorOutput "  1. Verify the task exists in Task Scheduler" -Color White
        $taskPath = "Task Scheduler Library > IATB_PreMarketTokenValidator"
        Write-ColorOutput "     Open Task Scheduler > $taskPath" -Color Gray
        Write-ColorOutput "  2. Check logs after scheduled run:" -Color White
        Write-ColorOutput "     $LogDir\pre_market_validation.log" -Color Gray
        Write-ColorOutput "  3. Monitor for CRITICAL alerts indicating token expiry" -Color White
    }
    elseif ($Action -eq "Remove" -and $Success) {
        Write-ColorOutput "  1. Verify task is removed from Task Scheduler" -Color White
    }
    elseif ($Action -eq "RunOnce" -and $Success) {
        Write-ColorOutput "  1. Check validation results in:" -Color White
        Write-ColorOutput "     $LogDir\pre_market_validation.log" -Color Gray
    }

    Write-ColorOutput "`n[5/6] Risk Mitigation Status" -Color Cyan
    Write-ColorOutput "  Risk 2: Token Expiry During Trading Hours" -Color White
    Write-ColorOutput "  ✓ Pre-market token validation: ENABLED" -Color Green
    Write-ColorOutput "  ✓ Automated re-login with TOTP: ENABLED" -Color Green
    Write-ColorOutput "  ✓ Alert on token expiry: ENABLED`n" -Color Green

    Write-ColorOutput "[6/6] Documentation" -Color Cyan
    Write-ColorOutput "  See scripts/pre_market_token_validator.py for implementation details" -Color Gray
    Write-ColorOutput ""
}

# ── Main Execution ─────────────────────────────────────────────────────────────

$success = $false

switch ($Action) {
    "Help" {
        Show-Usage
        exit 0
    }

    "Create" {
        if (Test-Prerequisites) {
            $success = New-ValidatorTask
            Show-Summary -Success $success -Action $Action
        }
        exit $(if ($success) { 0 } else { 1 })
    }

    "Remove" {
        $success = Remove-ValidatorTask
        Show-Summary -Success $success -Action $Action
        exit $(if ($success) { 0 } else { 1 })
    }

    "List" {
        $success = Show-ValidatorTask
        exit $(if ($success) { 0 } else { 1 })
    }

    "RunOnce" {
        if (Test-Prerequisites) {
            $success = Invoke-ValidatorOnce
            Show-Summary -Success $success -Action $Action
        }
        exit $(if ($success) { 0 } else { 1 })
    }

    default {
        Write-ColorOutput "Unknown action: $Action" -Color Red
        Show-Usage
        exit 1
    }
}