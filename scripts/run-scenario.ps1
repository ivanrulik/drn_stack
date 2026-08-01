[CmdletBinding()]
param(
    [Parameter(Mandatory = $true, Position = 0)]
    [string]$Project,

    [Parameter(Mandatory = $true, Position = 1)]
    [ValidatePattern('^[a-z][a-z0-9]*(?:-[a-z0-9]+)*$')]
    [string]$Scenario
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

function Invoke-Docker {
    param([Parameter(ValueFromRemainingArguments = $true)][string[]]$Arguments)
    & docker @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "Docker command failed with exit code $LASTEXITCODE."
    }
}

function Invoke-DockerOutput {
    param([Parameter(ValueFromRemainingArguments = $true)][string[]]$Arguments)
    $Output = @(& docker @Arguments)
    if ($LASTEXITCODE -ne 0) {
        throw "Docker command failed with exit code $LASTEXITCODE."
    }
    return ($Output -join "`n").Trim()
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
    & docker compose version *> $null
    if ($LASTEXITCODE -ne 0) {
        throw 'Docker Compose v2 is required.'
    }
    & docker info *> $null
    if ($LASTEXITCODE -ne 0) {
        throw 'Docker Desktop is not running or its Linux daemon is unavailable.'
    }
    $OsType = (& docker info --format '{{.OSType}}').Trim()
    if ($OsType -ne 'linux') {
        throw "The DRN stack requires Docker's Linux container engine; current engine is '$OsType'."
    }
}

function Assert-StorageAvailable {
    $RepoDriveRoot = [System.IO.Path]::GetPathRoot($RepoRoot)
    $Drive = Get-CimInstance Win32_LogicalDisk -Filter "DeviceID='$($RepoDriveRoot.TrimEnd('\'))'"
    if (-not $Drive) {
        throw "Could not determine free space for $RepoDriveRoot."
    }
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
    $FreeGiB = [Math]::Round($Drive.FreeSpace / 1GB, 1)
    Write-Host "Host storage: $($Drive.DeviceID) has $FreeGiB GiB free"
    if ($FreeGiB -lt $MinimumGiB) {
        throw "Refusing to start with less than $MinimumGiB GiB free."
    }
}

function Assert-PortsAvailable {
    foreach ($Port in @(
        (Get-Setting -Name 'FOXGLOVE_PORT' -Default '8765')
        (Get-Setting -Name 'QGC_PORT' -Default '14550')
    )) {
        $Owners = @(
            @(& docker ps --filter "publish=$Port" --format '{{.Names}}') |
                Where-Object { $_ -and -not $_.StartsWith('drn-stack-') }
        )
        if ($Owners.Count -gt 0) {
            throw "Port $Port is already published by Docker container: $($Owners -join ', ')"
        }
    }
}

function Restore-EnvironmentValue {
    param(
        [Parameter(Mandatory = $true)][string]$Name,
        [AllowNull()][string]$Value
    )
    if ($null -eq $Value) {
        Remove-Item "Env:$Name" -ErrorAction SilentlyContinue
    }
    else {
        [Environment]::SetEnvironmentVariable($Name, $Value)
    }
}

$RepoRoot = Split-Path -Parent $PSScriptRoot
$ProjectRoot = (Resolve-Path -LiteralPath $Project).Path
if (-not (Test-Path -LiteralPath $ProjectRoot -PathType Container)) {
    throw "Project directory was not found: $Project"
}

$ManifestPath = Join-Path $ProjectRoot 'project.yaml'
$OverridePath = Join-Path $ProjectRoot 'compose.override.yaml'
$ScenarioPath = Join-Path (Join-Path $ProjectRoot 'scenarios') "$Scenario.yaml"
foreach ($RequiredPath in @($ManifestPath, $OverridePath, $ScenarioPath)) {
    if (-not (Test-Path -LiteralPath $RequiredPath -PathType Leaf)) {
        throw "Required project file was not found: $RequiredPath"
    }
}

$BaseCompose = @(
    'compose', '--project-name', 'drn-stack',
    '--project-directory', $RepoRoot,
    '--file', (Join-Path $RepoRoot 'compose.yaml')
)
$ProjectCompose = $BaseCompose + @('--file', $OverridePath)
$ProjectMount = "type=bind,src=$ProjectRoot,dst=/opt/drn_project,readonly"
$ContainerManifest = '/opt/drn_project/project.yaml'
$ContainerScenario = "/opt/drn_project/scenarios/$Scenario.yaml"
$BaseImage = 'drn-stack/ros-viz:humble'

$PreviousProjectDir = [Environment]::GetEnvironmentVariable('DRN_PROJECT_DIR')
$PreviousModel = [Environment]::GetEnvironmentVariable('PX4_SIM_MODEL')
$PreviousWorld = [Environment]::GetEnvironmentVariable('PX4_GZ_WORLD')
$StackOwned = $false
$Succeeded = $false

try {
    Assert-Docker
    Assert-StorageAvailable
    Assert-PortsAvailable

    $ExistingContainers = Invoke-DockerOutput @BaseCompose ps --all --quiet
    if (-not [string]::IsNullOrWhiteSpace($ExistingContainers)) {
        throw 'The drn-stack Compose project is already running. Stop it before running an isolated scenario.'
    }

    Write-Host 'Building the pinned DRN base image...'
    Invoke-Docker @BaseCompose build ros-viz

    $Validator = @(
        'run', '--rm', '--mount', $ProjectMount,
        '--entrypoint', '/usr/local/bin/drn-project', $BaseImage
    )
    Invoke-Docker @Validator validate $ContainerManifest $ContainerScenario
    $ResolvedModel = Invoke-DockerOutput @Validator get $ContainerManifest vehicle
    $ResolvedWorld = Invoke-DockerOutput @Validator get $ContainerManifest world

    $env:DRN_PROJECT_DIR = $ProjectRoot
    $env:PX4_SIM_MODEL = $ResolvedModel
    $env:PX4_GZ_WORLD = $ResolvedWorld

    Invoke-Docker @ProjectCompose config --quiet
    Write-Host "Building project overlay for $ProjectRoot..."
    Invoke-Docker @BaseCompose build px4-sitl
    Invoke-Docker @ProjectCompose build ros-viz

    $StackOwned = $true
    Invoke-Docker @ProjectCompose up -d --no-build --remove-orphans --wait --wait-timeout 300
    $ScenarioCommand = @'
source /usr/local/bin/drn-ros-environment
set -u
exec "$@"
'@
    $ScenarioCommand = $ScenarioCommand -replace "`r`n", "`n"
    Invoke-Docker @ProjectCompose exec -T ros-viz bash -lc $ScenarioCommand bash `
        /usr/local/bin/drn-project run $ContainerManifest $ContainerScenario
    $Succeeded = $true
    Write-Host "Scenario '$Scenario' passed; stopping the isolated stack."
}
finally {
    $CleanupError = $null
    if ($StackOwned) {
        if (-not $Succeeded) {
            Write-Host "`nScenario failed. Recent project logs:"
            try { Invoke-Docker @ProjectCompose logs --no-color --tail=200 } catch {}
        }
        try {
            Invoke-Docker @ProjectCompose down --remove-orphans --timeout 30
        }
        catch {
            $CleanupError = $_
        }
    }
    Restore-EnvironmentValue -Name 'DRN_PROJECT_DIR' -Value $PreviousProjectDir
    Restore-EnvironmentValue -Name 'PX4_SIM_MODEL' -Value $PreviousModel
    Restore-EnvironmentValue -Name 'PX4_GZ_WORLD' -Value $PreviousWorld
    if ($null -ne $CleanupError) {
        throw $CleanupError
    }
}
