[CmdletBinding()]
param(
    [Parameter(Mandatory = $true, Position = 0)]
    [ValidateSet('run', 'stop', 'restart', 'status', 'logs', 'clean', 'smoke')]
    [string]$Action,

    [Parameter(Position = 1)]
    [ValidateSet('px4-sitl', 'ros-viz')]
    [string]$Service,

    [string]$Profile = 'x500-basic',

    [switch]$Force
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
trap {
    [Console]::Error.WriteLine($_.Exception.Message)
    exit 1
}

$RepoRoot = Split-Path -Parent $PSScriptRoot
if ($Profile -notmatch '^[a-z0-9][a-z0-9-]*$') {
    throw "Invalid profile name '$Profile'. Use lowercase letters, digits, and hyphens."
}
$ProfileDirectory = Join-Path $RepoRoot "profiles\$Profile"
$ProfileCompose = Join-Path $ProfileDirectory 'compose.yaml'
if (-not (Test-Path -LiteralPath $ProfileCompose -PathType Leaf)) {
    throw "Unknown profile '$Profile': $ProfileCompose does not exist."
}
if ([string]::IsNullOrWhiteSpace($env:COMPOSE_PARALLEL_LIMIT)) {
    $env:COMPOSE_PARALLEL_LIMIT = '1'
}
$ComposeArgs = @(
    'compose',
    '--project-name', 'drn-stack',
    '--project-directory', $RepoRoot,
    '-f', (Join-Path $RepoRoot 'compose.yaml'),
    '-f', $ProfileCompose
)
$GpuAcceleration = 'software'

function Invoke-Docker {
    param([Parameter(ValueFromRemainingArguments = $true)][string[]]$Arguments)
    $PreviousPreference = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try {
        & docker @Arguments
        $ExitCode = $LASTEXITCODE
    }
    finally {
        $ErrorActionPreference = $PreviousPreference
    }
    if ($ExitCode -ne 0) {
        throw "Docker command failed with exit code $ExitCode."
    }
}

function Invoke-Compose {
    param([Parameter(ValueFromRemainingArguments = $true)][string[]]$Arguments)
    Invoke-Docker @ComposeArgs @Arguments
}

function Get-Setting {
    param(
        [Parameter(Mandatory = $true)][string]$Name,
        [Parameter(Mandatory = $true)][string]$Default
    )
    $Value = [Environment]::GetEnvironmentVariable($Name)
    if ([string]::IsNullOrWhiteSpace($Value)) {
        return $Default
    }
    return $Value
}

function Get-StorageStatus {
    $DriveRoot = [System.IO.Path]::GetPathRoot($RepoRoot)
    $Drive = Get-CimInstance Win32_LogicalDisk -Filter "DeviceID='$($DriveRoot.TrimEnd('\'))'"
    if (-not $Drive) {
        throw "Could not determine free space for $DriveRoot."
    }

    $VhdPath = Join-Path $env:LOCALAPPDATA 'Docker\wsl\disk\docker_data.vhdx'
    $VhdSizeBytes = if (Test-Path -LiteralPath $VhdPath) {
        (Get-Item -LiteralPath $VhdPath).Length
    }
    else {
        $null
    }

    [pscustomobject]@{
        Drive = $Drive.DeviceID
        FreeGiB = [Math]::Round($Drive.FreeSpace / 1GB, 1)
        VhdPath = $VhdPath
        VhdGiB = if ($null -ne $VhdSizeBytes) {
            [Math]::Round($VhdSizeBytes / 1GB, 1)
        }
        else {
            $null
        }
    }
}

function Show-StorageStatus {
    $Storage = Get-StorageStatus
    $VhdText = if ($null -ne $Storage.VhdGiB) {
        "; Docker VHDX: $($Storage.VhdGiB) GiB"
    }
    else {
        ''
    }
    Write-Host "Host storage: $($Storage.Drive) has $($Storage.FreeGiB) GiB free$VhdText"
    return $Storage
}

function Assert-StorageAvailable {
    $MinimumText = Get-Setting -Name 'DRN_MIN_HOST_FREE_GB' -Default '50'
    $MinimumGiB = 0.0
    if (-not [double]::TryParse(
        $MinimumText,
        [Globalization.NumberStyles]::Float,
        [Globalization.CultureInfo]::InvariantCulture,
        [ref]$MinimumGiB
    ) -or $MinimumGiB -lt 0) {
        throw "DRN_MIN_HOST_FREE_GB must be a non-negative number; got '$MinimumText'."
    }

    $Storage = Show-StorageStatus
    if ($Storage.FreeGiB -lt $MinimumGiB) {
        throw (
            "Refusing to start with only $($Storage.FreeGiB) GiB free on $($Storage.Drive). " +
            "The safety minimum is $MinimumGiB GiB. Stop all containers, then run " +
            "'.\scripts\reclaim-docker-space.ps1 -Force', or free space another way. " +
            'Override only when intentional with DRN_MIN_HOST_FREE_GB.'
        )
    }
}

function Assert-Docker {
    if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
        throw 'Docker CLI was not found. Install or start Docker Desktop.'
    }
    $PreviousPreference = $ErrorActionPreference
    $ErrorActionPreference = 'SilentlyContinue'
    try {
        & docker compose version *> $null
        $ComposeExitCode = $LASTEXITCODE
        & docker info *> $null
        $InfoExitCode = $LASTEXITCODE
    }
    finally {
        $ErrorActionPreference = $PreviousPreference
    }
    if ($ComposeExitCode -ne 0) {
        throw 'Docker Compose v2 is required.'
    }
    if ($InfoExitCode -ne 0) {
        throw 'Docker Desktop is not running or its Linux daemon is unavailable.'
    }
    $OsType = (& docker info --format '{{.OSType}}').Trim()
    if ($OsType -ne 'linux') {
        throw "The DRN stack requires Docker's Linux container engine; current engine is '$OsType'."
    }
}

function Enable-ProfileGpu {
    $GpuCompose = Join-Path $ProfileDirectory 'compose.gpu.yaml'
    $SoftwareCompose = Join-Path $ProfileDirectory 'compose.software.yaml'
    $HasGpuCompose = Test-Path -LiteralPath $GpuCompose -PathType Leaf
    $HasSoftwareCompose = Test-Path -LiteralPath $SoftwareCompose -PathType Leaf
    if (-not $HasGpuCompose -and -not $HasSoftwareCompose) {
        return
    }
    if (-not $HasGpuCompose -or -not $HasSoftwareCompose) {
        throw "Profile '$Profile' must provide both compose.gpu.yaml and compose.software.yaml."
    }

    $Mode = (Get-Setting -Name 'DRN_GPU_MODE' -Default 'auto').ToLowerInvariant()
    if ($Mode -notin @('auto', 'on', 'off')) {
        throw "DRN_GPU_MODE must be auto, on, or off; got '$Mode'."
    }
    if ($Mode -eq 'off') {
        $script:ComposeArgs += @(
            '-f', $SoftwareCompose
        )
        Write-Host 'GPU acceleration: disabled; using balanced software sensor rates'
        return
    }

    $PreviousPreference = $ErrorActionPreference
    $ErrorActionPreference = 'SilentlyContinue'
    try {
        & docker run --rm --gpus all `
            --env NVIDIA_DRIVER_CAPABILITIES=compute,graphics,utility `
            --env NVIDIA_VISIBLE_DEVICES=all `
            --entrypoint /usr/local/bin/drn-gpu-renderer-check `
            drn-stack/px4-sitl:v1.17.0 *> $null
        $GpuProbeExitCode = $LASTEXITCODE
    }
    finally {
        $ErrorActionPreference = $PreviousPreference
    }

    if ($GpuProbeExitCode -ne 0) {
        if ($Mode -eq 'on') {
            throw (
                'DRN_GPU_MODE=on was requested, but Docker could not initialize ' +
                'a hardware EGL renderer for Gazebo.'
            )
        }
        $script:ComposeArgs += @(
            '-f', $SoftwareCompose
        )
        Write-Host (
            'GPU acceleration: no hardware EGL renderer; ' +
            'using balanced software sensor rates'
        )
        return
    }

    $script:ComposeArgs += @(
        '-f', $GpuCompose
    )
    $script:GpuAcceleration = 'hardware (EGL)'
    Write-Host 'GPU acceleration: hardware EGL renderer enabled'
}

function Assert-PortsAvailable {
    $AllowedPrefix = 'drn-stack-'
    $Ports = @(
        (Get-Setting -Name 'FOXGLOVE_PORT' -Default '8765')
        (Get-Setting -Name 'QGC_PORT' -Default '14550')
    )
    foreach ($Port in $Ports) {
        $Owners = @(
            @(& docker ps --filter "publish=$Port" --format '{{.Names}}') |
                Where-Object { $_ -and -not $_.StartsWith($AllowedPrefix) }
        )
        if ($Owners.Count -gt 0) {
            throw "Port $Port is already published by Docker container: $($Owners -join ', ')"
        }
    }
}

function Show-Failure {
    Write-Host "`nDRN stack did not become ready. Current state:"
    try { Invoke-Compose ps } catch {}
    Write-Host "`nRecent logs:"
    try { Invoke-Compose logs --tail=100 } catch {}
}

function Invoke-FullSmoke {
    Invoke-Compose exec -T ros-viz /usr/local/bin/drn-smoke-test full
}

function Invoke-QuickSmoke {
    Invoke-Compose exec -T ros-viz /usr/local/bin/drn-smoke-test quick
}

function Show-Summary {
    Invoke-Compose ps
    $FoxglovePort = Get-Setting -Name 'FOXGLOVE_PORT' -Default '8765'
    $QgcPort = Get-Setting -Name 'QGC_PORT' -Default '14550'
    Write-Host ''
    Write-Host 'DRN simulation is ready.'
    Write-Host "Profile: $Profile"
    if (Test-Path -LiteralPath (Join-Path $ProfileDirectory 'compose.gpu.yaml')) {
        Write-Host "Rendering: $GpuAcceleration"
    }
    Write-Host "Foxglove: ws://localhost:$FoxglovePort"
    $LayoutPath = Join-Path $RepoRoot "foxglove\drn-simulation-$Profile.json"
    if (Test-Path -LiteralPath $LayoutPath -PathType Leaf) {
        Write-Host "Foxglove layout: foxglove\drn-simulation-$Profile.json"
    }
    Write-Host "QGroundControl: UDP localhost:$QgcPort"
    Write-Host 'Logs: .\scripts\logs.ps1'
    Write-Host 'Status: .\scripts\status.ps1'
    Write-Host 'Stop: .\scripts\stop.ps1'
}

if ($Action -eq 'stop') {
    $DockerCommand = Get-Command docker -ErrorAction SilentlyContinue
    if (-not $DockerCommand) {
        Write-Host 'DRN simulation is already stopped (Docker CLI is unavailable).'
        exit 0
    }

    $PreviousPreference = $ErrorActionPreference
    $ErrorActionPreference = 'SilentlyContinue'
    try {
        & docker info *> $null
        $DockerInfoExitCode = $LASTEXITCODE
    }
    finally {
        $ErrorActionPreference = $PreviousPreference
    }

    if ($DockerInfoExitCode -ne 0) {
        Write-Host 'DRN simulation is already stopped (Docker engine is unavailable).'
        exit 0
    }

    Invoke-Compose down --remove-orphans --timeout 30
    exit 0
}

Assert-Docker

switch ($Action) {
    'run' {
        Assert-StorageAvailable
        Assert-PortsAvailable
        Invoke-Compose config --quiet
        try {
            Invoke-Compose build ros-viz
            Invoke-Compose build px4-sitl
            Enable-ProfileGpu
            Invoke-Compose config --quiet
            Invoke-Compose up -d --no-build --remove-orphans --wait --wait-timeout 300
            Invoke-FullSmoke
            Show-Summary
        }
        catch {
            Show-Failure
            throw
        }
    }
    'restart' {
        Assert-StorageAvailable
        try {
            Enable-ProfileGpu
            Invoke-Compose config --quiet
            Invoke-Compose stop --timeout 30
            Invoke-Compose up -d --no-build --remove-orphans --wait --wait-timeout 300
            Invoke-FullSmoke
            Show-Summary
        }
        catch {
            Show-Failure
            throw
        }
    }
    'status' {
        Show-StorageStatus | Out-Null
        Invoke-Compose ps
        Invoke-QuickSmoke
        Write-Host "`n$Profile profile, Foxglove, and PX4 odometry checks passed."
    }
    'logs' {
        if ($Service) {
            Invoke-Compose logs --follow --tail=200 $Service
        }
        else {
            Invoke-Compose logs --follow --tail=200
        }
    }
    'clean' {
        if (-not $Force) {
            throw 'Refusing cleanup without -Force. This removes only drn-stack resources.'
        }
        Invoke-Compose down --remove-orphans --volumes --rmi local --timeout 30
    }
    'smoke' {
        Invoke-FullSmoke
    }
}
