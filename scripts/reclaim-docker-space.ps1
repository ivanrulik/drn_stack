[CmdletBinding()]
param(
    [switch]$Force
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
trap {
    [Console]::Error.WriteLine($_.Exception.Message)
    exit 1
}

if (-not $Force) {
    throw (
        'Refusing without -Force. This stops Docker Desktop and every WSL distribution, ' +
        'but does not delete images, containers, volumes, or build cache.'
    )
}

foreach ($Command in @('docker', 'wsl.exe')) {
    if (-not (Get-Command $Command -ErrorAction SilentlyContinue)) {
        throw "$Command was not found."
    }
}

& docker info *> $null
if ($LASTEXITCODE -ne 0) {
    throw 'Docker Desktop is not running.'
}

$RunningContainers = @(& docker ps --format '{{.Names}}')
if ($LASTEXITCODE -ne 0) {
    throw 'Could not inspect running Docker containers.'
}
if ($RunningContainers.Count -gt 0) {
    throw (
        "Stop all Docker containers before reclaiming space. Running: " +
        ($RunningContainers -join ', ')
    )
}

$VhdPath = Join-Path $env:LOCALAPPDATA 'Docker\wsl\disk\docker_data.vhdx'
if (-not (Test-Path -LiteralPath $VhdPath)) {
    throw "Docker's WSL data disk was not found at $VhdPath."
}

$DockerDesktopExe = Join-Path $env:ProgramFiles 'Docker\Docker\Docker Desktop.exe'
$DockerCliExe = Join-Path $env:ProgramFiles 'Docker\Docker\DockerCli.exe'
if (-not (Test-Path -LiteralPath $DockerDesktopExe) -or -not (Test-Path -LiteralPath $DockerCliExe)) {
    throw 'Docker Desktop executables were not found in the standard installation directory.'
}

function Get-FreeGiB {
    $DriveRoot = [System.IO.Path]::GetPathRoot($VhdPath)
    $Drive = Get-CimInstance Win32_LogicalDisk -Filter "DeviceID='$($DriveRoot.TrimEnd('\'))'"
    return [Math]::Round($Drive.FreeSpace / 1GB, 1)
}

$BeforeVhdGiB = [Math]::Round((Get-Item -LiteralPath $VhdPath).Length / 1GB, 1)
$BeforeFreeGiB = Get-FreeGiB
Write-Host "Before: Docker VHDX $BeforeVhdGiB GiB; host free $BeforeFreeGiB GiB"
Write-Host 'Discarding unused blocks inside Docker''s WSL data filesystem...'

& wsl.exe -d docker-desktop -u root -- /sbin/fstrim -v /mnt/docker-desktop-disk
if ($LASTEXITCODE -ne 0) {
    throw "fstrim failed with exit code $LASTEXITCODE."
}

Write-Host 'Stopping Docker Desktop and WSL so Windows can compact the managed VHDX...'
& $DockerCliExe -Shutdown
if ($LASTEXITCODE -ne 0) {
    throw "Docker Desktop shutdown failed with exit code $LASTEXITCODE."
}
& wsl.exe --shutdown
if ($LASTEXITCODE -ne 0) {
    throw "WSL shutdown failed with exit code $LASTEXITCODE."
}

$PreviousSize = -1
for ($Attempt = 0; $Attempt -lt 30; $Attempt++) {
    Start-Sleep -Seconds 1
    $CurrentSize = (Get-Item -LiteralPath $VhdPath).Length
    if ($CurrentSize -eq $PreviousSize) {
        break
    }
    $PreviousSize = $CurrentSize
}

$AfterVhdGiB = [Math]::Round((Get-Item -LiteralPath $VhdPath).Length / 1GB, 1)
$AfterFreeGiB = Get-FreeGiB
Write-Host "After:  Docker VHDX $AfterVhdGiB GiB; host free $AfterFreeGiB GiB"

Write-Host 'Restarting Docker Desktop...'
Start-Process -FilePath $DockerDesktopExe -WindowStyle Hidden
for ($Attempt = 0; $Attempt -lt 60; $Attempt++) {
    Start-Sleep -Seconds 2
    $PreviousPreference = $ErrorActionPreference
    $ErrorActionPreference = 'SilentlyContinue'
    try {
        & docker info *> $null
        $Ready = $LASTEXITCODE -eq 0
    }
    finally {
        $ErrorActionPreference = $PreviousPreference
    }
    if ($Ready) {
        Write-Host 'Docker Desktop is ready. No Docker data was pruned.'
        exit 0
    }
}

throw 'Docker Desktop did not become ready within 120 seconds. Open it manually and check its diagnostics.'
