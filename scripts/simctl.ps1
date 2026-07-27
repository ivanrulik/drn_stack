[CmdletBinding()]
param(
    [Parameter(Mandatory = $true, Position = 0)]
    [ValidateSet('run', 'stop', 'restart', 'status', 'logs', 'clean', 'smoke')]
    [string]$Action,

    [Parameter(Position = 1)]
    [ValidateSet('px4-sitl', 'ros-viz')]
    [string]$Service,

    [switch]$Force
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
trap {
    [Console]::Error.WriteLine($_.Exception.Message)
    exit 1
}

$RepoRoot = Split-Path -Parent $PSScriptRoot
if ([string]::IsNullOrWhiteSpace($env:COMPOSE_PARALLEL_LIMIT)) {
    $env:COMPOSE_PARALLEL_LIMIT = '1'
}
$ComposeArgs = @(
    'compose',
    '--project-name', 'drn-stack',
    '--project-directory', $RepoRoot,
    '-f', (Join-Path $RepoRoot 'compose.yaml')
)

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
    Write-Host "Foxglove: ws://localhost:$FoxglovePort"
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
        Assert-PortsAvailable
        Invoke-Compose config --quiet
        try {
            Invoke-Compose build ros-viz
            Invoke-Compose build px4-sitl
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
        try {
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
        Invoke-Compose ps
        Invoke-QuickSmoke
        Write-Host "`nFoxglove and PX4 odometry checks passed."
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
