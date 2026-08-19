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

$PreviousPreference = $ErrorActionPreference
$ErrorActionPreference = 'SilentlyContinue'
try {
    & docker info *> $null
    $DockerWasRunning = $LASTEXITCODE -eq 0
}
finally {
    $ErrorActionPreference = $PreviousPreference
}

if ($DockerWasRunning) {
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
}
else {
    Write-Host 'Docker Desktop is already stopped; mounting its data disk only for trimming.'
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

function Test-IsAdministrator {
    $Identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $Principal = [Security.Principal.WindowsPrincipal]::new($Identity)
    return $Principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

function Wait-VhdUnlocked {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [int]$TimeoutSeconds = 120
    )

    # Docker Desktop may compact the VHDX asynchronously just after WSL exits.
    Start-Sleep -Seconds 5
    for ($Attempt = 0; $Attempt -lt $TimeoutSeconds; $Attempt++) {
        try {
            $Stream = [IO.File]::Open(
                $Path,
                [IO.FileMode]::Open,
                [IO.FileAccess]::ReadWrite,
                [IO.FileShare]::None
            )
            $Stream.Dispose()
            return
        }
        catch [IO.IOException] {
            Start-Sleep -Seconds 1
        }
    }

    throw "Docker's VHDX remained locked for more than $TimeoutSeconds seconds."
}

function Invoke-VhdCompaction {
    param([Parameter(Mandatory = $true)][string]$Path)

    Wait-VhdUnlocked -Path $Path
    if (-not (Test-IsAdministrator)) {
        Write-Warning (
            'Skipping explicit DiskPart compaction because this PowerShell session is not elevated. ' +
            'Run the command from an Administrator PowerShell window for deterministic compaction.'
        )
        return
    }
    if (-not (Get-Command diskpart.exe -ErrorAction SilentlyContinue)) {
        throw 'diskpart.exe was not found.'
    }

    $DiskPartScript = New-TemporaryFile
    try {
        [IO.File]::WriteAllLines(
            $DiskPartScript.FullName,
            @(
                "select vdisk file=`"$Path`""
                'compact vdisk'
                'exit'
            ),
            [Text.Encoding]::ASCII
        )

        for ($Attempt = 1; $Attempt -le 3; $Attempt++) {
            if ($Attempt -gt 1) {
                Wait-VhdUnlocked -Path $Path
            }
            $PreviousPreference = $ErrorActionPreference
            $ErrorActionPreference = 'Continue'
            try {
                $Output = @(& diskpart.exe /s $DiskPartScript.FullName 2>&1)
                $ExitCode = $LASTEXITCODE
            }
            finally {
                $ErrorActionPreference = $PreviousPreference
            }
            if ($ExitCode -eq 0) {
                return
            }
            if ($Attempt -lt 3) {
                Write-Host 'The VHDX was still busy; retrying explicit compaction...'
            }
        }

        throw "DiskPart compaction failed: $($Output -join ' ')"
    }
    finally {
        Remove-Item -LiteralPath $DiskPartScript.FullName -Force -ErrorAction SilentlyContinue
    }
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
if ($DockerWasRunning) {
    & $DockerCliExe -Shutdown
    if ($LASTEXITCODE -ne 0) {
        throw "Docker Desktop shutdown failed with exit code $LASTEXITCODE."
    }
}
& wsl.exe --shutdown
if ($LASTEXITCODE -ne 0) {
    throw "WSL shutdown failed with exit code $LASTEXITCODE."
}

Write-Host 'Compacting Docker''s dynamically expanding VHDX...'
Invoke-VhdCompaction -Path $VhdPath

$AfterVhdGiB = [Math]::Round((Get-Item -LiteralPath $VhdPath).Length / 1GB, 1)
$AfterFreeGiB = Get-FreeGiB
Write-Host "After:  Docker VHDX $AfterVhdGiB GiB; host free $AfterFreeGiB GiB"

if ($DockerWasRunning) {
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
}

Write-Host 'Docker Desktop remains stopped, matching its initial state. No Docker data was pruned.'
