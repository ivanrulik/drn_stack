[CmdletBinding()]
param(
    [Parameter(Mandatory = $true, Position = 0)]
    [ValidateSet('run', 'stop', 'restart', 'status', 'logs', 'smoke')]
    [string]$Action,

    [string]$BindAddress = $env:DRN_HARDWARE_BIND_ADDRESS,

    [string]$Profile = 'x500-basic'
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
trap {
    [Console]::Error.WriteLine($_.Exception.Message)
    exit 1
}

$RepoRoot = Split-Path -Parent $PSScriptRoot
$ProfileCompose = Join-Path $RepoRoot "profiles\$Profile\compose.yaml"
$ConnectionCompose = Join-Path $RepoRoot 'connections\hardware-udp\compose.yaml'
if ($Profile -notmatch '^[a-z0-9][a-z0-9-]*$') {
    throw "Invalid profile name '$Profile'."
}

function Assert-BindAddress {
    $ParsedAddress = $null
    if (
        [string]::IsNullOrWhiteSpace($BindAddress) -or
        -not [Net.IPAddress]::TryParse($BindAddress, [ref]$ParsedAddress) -or
        $ParsedAddress.AddressFamily -ne [Net.Sockets.AddressFamily]::InterNetwork -or
        [Net.IPAddress]::IsLoopback($ParsedAddress) -or
        $ParsedAddress.Equals([Net.IPAddress]::Any)
    ) {
        throw (
            'Set -BindAddress (or DRN_HARDWARE_BIND_ADDRESS) to the explicit ' +
            'non-loopback IPv4 address of the trusted bench interface.'
        )
    }
}

function Invoke-Docker {
    param([Parameter(ValueFromRemainingArguments = $true)][string[]]$Arguments)
    & docker @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "Docker command failed with exit code $LASTEXITCODE."
    }
}

function Invoke-Compose {
    param([Parameter(ValueFromRemainingArguments = $true)][string[]]$Arguments)
    Invoke-Docker @script:ComposeArgs @Arguments
}

function Assert-Docker {
    if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
        throw 'Docker CLI was not found. Install or start Docker Desktop.'
    }
    & docker compose version *> $null
    if ($LASTEXITCODE -ne 0) { throw 'Docker Compose v2 is required.' }
    & docker info *> $null
    if ($LASTEXITCODE -ne 0) { throw 'Docker Desktop is not running.' }
    if ((& docker info --format '{{.OSType}}').Trim() -ne 'linux') {
        throw "The DRN stack requires Docker's Linux container engine."
    }
}

function Get-Setting {
    param([string]$Name, [string]$Default)
    $Value = [Environment]::GetEnvironmentVariable($Name)
    if ([string]::IsNullOrWhiteSpace($Value)) { return $Default }
    return $Value
}

function Assert-StorageAvailable {
    $DriveRoot = [IO.Path]::GetPathRoot($RepoRoot)
    $Drive = Get-CimInstance Win32_LogicalDisk -Filter "DeviceID='$($DriveRoot.TrimEnd('\'))'"
    if (-not $Drive) { throw "Could not determine free space for $DriveRoot." }
    $MinimumGiB = [double](Get-Setting -Name 'DRN_MIN_HOST_FREE_GB' -Default '50')
    $FreeGiB = [Math]::Round($Drive.FreeSpace / 1GB, 1)
    Write-Host "Host storage: $($Drive.DeviceID) has $FreeGiB GiB free"
    if ($FreeGiB -lt $MinimumGiB) {
        throw "Refusing to start with less than $MinimumGiB GiB free."
    }
}

function Assert-PortsAvailable {
    $Ports = @(
        (Get-Setting -Name 'FOXGLOVE_PORT' -Default '8765')
        (Get-Setting -Name 'XRCE_PORT' -Default '8888')
        (Get-Setting -Name 'DRN_HARDWARE_MAVLINK_PORT' -Default '14580')
    )
    foreach ($Port in $Ports) {
        $Owners = @(& docker ps --filter "publish=$Port" --format '{{.Names}}') |
            Where-Object { $_ -and -not $_.StartsWith('drn-stack-') }
        if ($Owners.Count -gt 0) {
            throw "Port $Port is already published by Docker container: $($Owners -join ', ')"
        }
    }
}

function Invoke-HardwareSmoke {
    Invoke-Compose exec -T ros-viz /usr/local/bin/drn-hardware-smoke
}

function Show-Summary {
    Invoke-Compose ps
    $XrcePort = Get-Setting -Name 'XRCE_PORT' -Default '8888'
    $MavlinkPort = Get-Setting -Name 'DRN_HARDWARE_MAVLINK_PORT' -Default '14580'
    $FoxglovePort = Get-Setting -Name 'FOXGLOVE_PORT' -Default '8765'
    Write-Host ''
    Write-Host 'DRN hardware UDP companion is ready (read-only, disarmed acceptance passed).'
    Write-Host "Trusted interface: $BindAddress"
    Write-Host "XRCE-DDS Agent: UDP $BindAddress`:$XrcePort"
    Write-Host "MAVLink verifier: UDP $BindAddress`:$MavlinkPort"
    Write-Host "Foxglove: ws://localhost:$FoxglovePort (publish/services denied)"
    Write-Host 'Reports: artifacts\hardware'
}

if (-not (Test-Path -LiteralPath $ProfileCompose -PathType Leaf)) {
    throw "Unknown profile '$Profile'."
}
Assert-BindAddress
Assert-Docker

$Artifacts = Join-Path $RepoRoot 'artifacts\hardware'
[IO.Directory]::CreateDirectory($Artifacts) | Out-Null
$env:DRN_HARDWARE_BIND_ADDRESS = $BindAddress
$env:DRN_HARDWARE_ARTIFACTS = $Artifacts
$env:DRN_GIT_REVISION = (& git -C $RepoRoot rev-parse HEAD).Trim()
$env:DRN_GIT_DIRTY = if (& git -C $RepoRoot status --porcelain) {
    'true'
}
else {
    'false'
}
$ImageId = & docker image inspect drn-stack/ros-viz:humble --format '{{.Id}}' 2>$null
if ($LASTEXITCODE -eq 0) { $env:DRN_IMAGE_ID = $ImageId.Trim() }
$script:ComposeArgs = @(
    'compose', '--project-name', 'drn-stack', '--project-directory', $RepoRoot,
    '-f', (Join-Path $RepoRoot 'compose.yaml'),
    '-f', $ProfileCompose,
    '-f', $ConnectionCompose
)

switch ($Action) {
    'run' {
        Assert-StorageAvailable
        Assert-PortsAvailable
        Invoke-Compose config --quiet
        Invoke-Compose build ros-viz
        $ImageId = & docker image inspect `
            drn-stack/ros-viz:humble --format '{{.Id}}'
        $env:DRN_IMAGE_ID = $ImageId.Trim()
        Invoke-Compose up -d --no-build --remove-orphans --wait --wait-timeout 300 ros-viz
        Invoke-HardwareSmoke
        Show-Summary
    }
    'restart' {
        Assert-StorageAvailable
        Invoke-Compose stop --timeout 30 ros-viz
        Invoke-Compose up -d --no-build --remove-orphans --wait --wait-timeout 300 ros-viz
        Invoke-HardwareSmoke
        Show-Summary
    }
    'status' { Invoke-Compose ps; Invoke-HardwareSmoke }
    'smoke' { Invoke-HardwareSmoke }
    'logs' { Invoke-Compose logs --follow --tail=200 ros-viz }
    'stop' { Invoke-Compose down --remove-orphans --timeout 30 }
}
