[CmdletBinding()]
param(
    [Parameter(Mandatory = $true, Position = 0)]
    [string]$Project,

    [Parameter(Mandatory = $true, Position = 1)]
    [ValidatePattern('^[a-z][a-z0-9]*(?:-[a-z0-9]+)*$')]
    [string]$Scenario,

    [switch]$Evidence,

    [switch]$AllowOperatorActions
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

function Invoke-DockerToFile {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [Parameter(ValueFromRemainingArguments = $true)][string[]]$Arguments
    )
    $Output = @(& docker @Arguments 2>&1)
    $ExitCode = $LASTEXITCODE
    [IO.File]::WriteAllLines(
        $Path,
        [string[]]$Output,
        [Text.UTF8Encoding]::new($false)
    )
    if ($ExitCode -ne 0) {
        throw "Docker command failed with exit code $ExitCode."
    }
}

function Invoke-DockerTee {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [switch]$Append,
        [Parameter(ValueFromRemainingArguments = $true)][string[]]$Arguments
    )
    & docker @Arguments 2>&1 | Tee-Object -FilePath $Path -Append:$Append
    if ($LASTEXITCODE -ne 0) {
        throw "Docker command failed with exit code $LASTEXITCODE."
    }
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

function Invoke-EvidenceExec {
    param([Parameter(ValueFromRemainingArguments = $true)][string[]]$Arguments)
    $Command = @'
source /usr/local/bin/drn-ros-environment
set -u
exec /usr/local/bin/drn-evidence "$@"
'@
    $Command = $Command -replace "`r`n", "`n"
    $DockerArguments = $ProjectCompose + @(
        'exec', '-T', 'ros-viz', 'bash', '-lc', $Command, 'bash'
    ) + $Arguments
    Invoke-Docker -Arguments $DockerArguments
}

function Invoke-EvidenceRun {
    param(
        [Parameter(Mandatory = $true)][string]$MountSource,
        [Parameter(Mandatory = $true)][string]$MountTarget,
        [Parameter(Mandatory = $true)][string[]]$EvidenceArguments
    )
    $Command = @'
source /usr/local/bin/drn-ros-environment
set -u
exec /usr/local/bin/drn-evidence "$@"
'@
    $Command = $Command -replace "`r`n", "`n"
    $Mount = "type=bind,src=$MountSource,dst=$MountTarget"
    $DockerArguments = @(
        'run', '--rm', '--mount', $Mount, '--entrypoint', 'bash', $BaseImage,
        '-lc', $Command, 'bash'
    ) + $EvidenceArguments
    Invoke-Docker -Arguments $DockerArguments
}

function Invoke-ScenarioProject {
    param([Parameter(Mandatory = $true)][string[]]$ProjectArguments)
    $Command = @'
source /usr/local/bin/drn-ros-environment
set -u
exec "$@"
'@
    $Command = $Command -replace "`r`n", "`n"
    $DockerArguments = $ProjectCompose + @(
        'exec', '-T', 'ros-viz', 'bash', '-lc', $Command, 'bash',
        '/usr/local/bin/drn-project'
    ) + $ProjectArguments
    Invoke-DockerLogged -Arguments $DockerArguments
}

function Invoke-Px4Failure {
    param([Parameter(Mandatory = $true)][string[]]$FailureArguments)
    $DockerArguments = $ProjectCompose + @(
        'exec', '-T', '-e', 'DRN_OPERATOR_ACTIONS=1', 'px4-sitl',
        '/usr/local/bin/drn-px4-failure'
    ) + $FailureArguments
    Invoke-DockerLogged -Arguments $DockerArguments
}

function Invoke-DockerLogged {
    param([Parameter(Mandatory = $true)][string[]]$Arguments)
    if ($EvidenceInitialized) {
        Invoke-DockerTee -Path (Join-Path $RunDir 'logs/scenario.log') `
            -Append -Arguments $Arguments
    }
    else {
        Invoke-Docker -Arguments $Arguments
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
$Px4Image = 'drn-stack/px4-sitl:v1.17.0'

$EvidenceSetting = Get-Setting -Name 'DRN_EVIDENCE' -Default '0'
if ($EvidenceSetting -notin @('0', '1')) {
    throw "DRN_EVIDENCE must be 0 or 1; got '$EvidenceSetting'."
}
$EvidenceEnabled = $Evidence.IsPresent -or $EvidenceSetting -eq '1'
$EvidenceMaxText = Get-Setting -Name 'DRN_EVIDENCE_MAX_BYTES' -Default '1073741824'
$EvidenceMaxBytes = 0L
if (-not [long]::TryParse($EvidenceMaxText, [ref]$EvidenceMaxBytes) -or $EvidenceMaxBytes -le 0) {
    throw 'DRN_EVIDENCE_MAX_BYTES must be a positive integer.'
}
$RetentionText = Get-Setting -Name 'DRN_EVIDENCE_RETENTION_COUNT' -Default '5'
$RetentionCount = 0
if (-not [int]::TryParse($RetentionText, [ref]$RetentionCount) -or
    $RetentionCount -lt 1 -or $RetentionCount -gt 100) {
    throw 'DRN_EVIDENCE_RETENTION_COUNT must be an integer from 1 to 100.'
}

$PreviousProjectDir = [Environment]::GetEnvironmentVariable('DRN_PROJECT_DIR')
$PreviousModel = [Environment]::GetEnvironmentVariable('PX4_SIM_MODEL')
$PreviousWorld = [Environment]::GetEnvironmentVariable('PX4_GZ_WORLD')
$PreviousArtifactDir = [Environment]::GetEnvironmentVariable('DRN_ARTIFACT_DIR')
$StackOwned = $false
$Succeeded = $false
$RecordingStarted = $false
$FailureActionsStarted = $false
$EvidenceInitialized = $false
$WorkflowError = $null
$EvidenceRoot = $null
$RunDir = $null
$RunId = $null
$StartedAt = $null
$ProjectName = $null
$ResolvedModel = $null
$ResolvedWorld = $null
$RosImage = 'unavailable'
$RosImageId = 'unavailable'
$Px4ImageId = 'unavailable'
$OperatorGate = 'inert'
$ScenarioTimeout = 0
$OperatorActions = @()
$FailureRestorations = @()

try {
    Assert-Docker
    Assert-StorageAvailable
    Assert-PortsAvailable

    $ExistingContainers = Invoke-DockerOutput -Arguments (
        $BaseCompose + @('ps', '--all', '--quiet')
    )
    if (-not [string]::IsNullOrWhiteSpace($ExistingContainers)) {
        throw 'The drn-stack Compose project is already running. Stop it before running an isolated scenario.'
    }

    Write-Host 'Building the pinned DRN base image...'
    Invoke-Docker -Arguments ($BaseCompose + @('build', 'ros-viz'))

    $Validator = @(
        'run', '--rm', '--mount', $ProjectMount,
        '--entrypoint', '/usr/local/bin/drn-project', $BaseImage
    )
    Invoke-Docker -Arguments (
        $Validator + @('validate', $ContainerManifest, $ContainerScenario)
    )
    $OperatorGate = Invoke-DockerOutput -Arguments (
        $Validator + @(
            'inspect', $ContainerManifest, $ContainerScenario, 'operator-gate'
        )
    )
    if ($OperatorGate -eq 'required') {
        if (-not $AllowOperatorActions.IsPresent) {
            throw "Scenario '$Scenario' contains operator actions. Re-run with " +
                '-AllowOperatorActions after confirming disarmed SITL use.'
        }
        $ScenarioTimeoutText = Invoke-DockerOutput -Arguments (
            $Validator + @(
                'inspect', $ContainerManifest, $ContainerScenario, 'timeout-seconds'
            )
        )
        if (-not [int]::TryParse($ScenarioTimeoutText, [ref]$ScenarioTimeout)) {
            throw "Invalid validated scenario timeout: $ScenarioTimeoutText"
        }
        $ActionOutput = Invoke-DockerOutput -Arguments (
            $Validator + @('actions', $ContainerManifest, $ContainerScenario)
        )
        $RestorationOutput = Invoke-DockerOutput -Arguments (
            $Validator + @('restorations', $ContainerManifest, $ContainerScenario)
        )
        $OperatorActions = @($ActionOutput -split '\r?\n' | Where-Object { $_ })
        $FailureRestorations = @(
            $RestorationOutput -split '\r?\n' | Where-Object { $_ }
        )
        Write-Host "Operator gate accepted for disarmed SITL scenario '$Scenario'."
    }
    $ProjectName = Invoke-DockerOutput -Arguments (
        $Validator + @('get', $ContainerManifest, 'name')
    )
    $ResolvedModel = Invoke-DockerOutput -Arguments (
        $Validator + @('get', $ContainerManifest, 'vehicle')
    )
    $ResolvedWorld = Invoke-DockerOutput -Arguments (
        $Validator + @('get', $ContainerManifest, 'world')
    )

    $env:DRN_PROJECT_DIR = $ProjectRoot
    $env:PX4_SIM_MODEL = $ResolvedModel
    $env:PX4_GZ_WORLD = $ResolvedWorld

    if ($EvidenceEnabled) {
        $EvidenceRootInput = Get-Setting -Name 'DRN_EVIDENCE_ROOT' `
            -Default (Join-Path $RepoRoot 'artifacts')
        [void](New-Item -ItemType Directory -Force -Path $EvidenceRootInput)
        $EvidenceRoot = (Resolve-Path -LiteralPath $EvidenceRootInput).Path
        $Timestamp = [DateTime]::UtcNow.ToString("yyyyMMdd'T'HHmmss'Z'")
        $ShortRevision = (& git -C $RepoRoot rev-parse --short=8 HEAD).Trim()
        if ($LASTEXITCODE -ne 0) {
            throw 'Could not resolve the DRN Git revision.'
        }
        $RunId = "$Timestamp-$Scenario-$ShortRevision"
        $RunDir = Join-Path $EvidenceRoot $RunId
        if (Test-Path -LiteralPath $RunDir) {
            throw "Evidence run directory already exists: $RunDir"
        }
        foreach ($Directory in @('logs', 'metadata', 'ulog')) {
            [void](New-Item -ItemType Directory -Path (Join-Path $RunDir $Directory))
        }
        Copy-Item -LiteralPath $ManifestPath -Destination (Join-Path $RunDir 'metadata/project.yaml')
        Copy-Item -LiteralPath $ScenarioPath -Destination (Join-Path $RunDir 'metadata/scenario.yaml')
        Copy-Item -LiteralPath (Join-Path $RepoRoot 'compose.yaml') `
            -Destination (Join-Path $RunDir 'metadata/compose.yaml')
        $env:DRN_ARTIFACT_DIR = $RunDir
        $ProjectCompose += @('--file', (Join-Path $RepoRoot 'compose.evidence.yaml'))
        $StartedAt = [DateTime]::UtcNow.ToString('o')
        $EvidenceInitialized = $true
    }

    Invoke-Docker -Arguments ($ProjectCompose + @('config', '--quiet'))
    Write-Host "Building project overlay for $ProjectRoot..."
    Invoke-Docker -Arguments ($BaseCompose + @('build', 'px4-sitl'))
    Invoke-Docker -Arguments ($ProjectCompose + @('build', 'ros-viz'))
    $RosImage = "drn-stack/$ProjectName`:humble"
    $RosImageId = Invoke-DockerOutput -Arguments @(
        'image', 'inspect', '--format', '{{.Id}}', $RosImage
    )
    $Px4ImageId = Invoke-DockerOutput -Arguments @(
        'image', 'inspect', '--format', '{{.Id}}', $Px4Image
    )

    $StackOwned = $true
    Invoke-Docker -Arguments (
        $ProjectCompose + @(
            'up', '-d', '--no-build', '--remove-orphans', '--wait',
            '--wait-timeout', '300'
        )
    )
    if ($EvidenceEnabled) {
        Invoke-EvidenceExec start /opt/drn_artifacts $ContainerManifest
        $RecordingStarted = $true
    }
    if ($OperatorGate -eq 'required') {
        $DeadlineUnix = [DateTimeOffset]::UtcNow.ToUnixTimeSeconds() + $ScenarioTimeout
        Invoke-ScenarioProject -ProjectArguments @(
            'run-phase', $ContainerManifest, $ContainerScenario, 'setup',
            '--deadline-unix', $DeadlineUnix.ToString()
        )
        foreach ($ActionLine in $OperatorActions) {
            $ActionParts = @($ActionLine -split ' ' | Where-Object { $_ })
            if ($ActionParts.Count -ne 2) {
                throw "Invalid validated action output: $ActionLine"
            }
            $FailureActionsStarted = $true
            Invoke-Px4Failure -FailureArguments @(
                'apply', $ActionParts[0], $ActionParts[1]
            )
        }
        Invoke-ScenarioProject -ProjectArguments @(
            'run-phase', $ContainerManifest, $ContainerScenario, 'assertions',
            '--deadline-unix', $DeadlineUnix.ToString()
        )
    }
    else {
        Invoke-ScenarioProject -ProjectArguments @(
            'run', $ContainerManifest, $ContainerScenario
        )
    }
    $Succeeded = $true
    Write-Host "Scenario '$Scenario' passed; stopping the isolated stack."
}
catch {
    $WorkflowError = $_
}
finally {
    $CleanupMessages = [Collections.Generic.List[string]]::new()
    if ($StackOwned) {
        if ($FailureActionsStarted) {
            $RestorationFailed = $false
            foreach ($Restoration in $FailureRestorations) {
                try {
                    Invoke-Px4Failure -FailureArguments @('restore', $Restoration)
                }
                catch {
                    $RestorationFailed = $true
                    $CleanupMessages.Add(
                        "PX4 failure restoration failed: $($_.Exception.Message)"
                    )
                }
            }
            if (-not $RestorationFailed) {
                $FailureActionsStarted = $false
            }
        }
        if ($RecordingStarted) {
            try {
                Invoke-EvidenceExec stop /opt/drn_artifacts
            }
            catch {
                $CleanupMessages.Add("Evidence recorder failed: $($_.Exception.Message)")
            }
        }
        if ($EvidenceInitialized) {
            try {
                $LogArguments = $ProjectCompose + @(
                    'logs', '--no-color', '--tail=500'
                )
                Invoke-DockerToFile -Path (Join-Path $RunDir 'logs/compose.log') `
                    -Arguments $LogArguments
            }
            catch {
                $CleanupMessages.Add("Compose log capture failed: $($_.Exception.Message)")
            }
        }
        if (-not $Succeeded) {
            Write-Host "`nScenario failed. Recent project logs:"
            try {
                Invoke-Docker -Arguments (
                    $ProjectCompose + @('logs', '--no-color', '--tail=200')
                )
            }
            catch {}
        }
        try {
            Invoke-Docker -Arguments (
                $ProjectCompose + @('down', '--remove-orphans', '--timeout', '30')
            )
        }
        catch {
            $CleanupMessages.Add("Stack cleanup failed: $($_.Exception.Message)")
        }
    }

    if ($EvidenceInitialized) {
        $Verdict = if ($Succeeded -and $null -eq $WorkflowError -and
            $CleanupMessages.Count -eq 0) { 'passed' } else { 'failed' }
        $FinishedAt = [DateTime]::UtcNow.ToString('o')
        $GitRevision = (& git -C $RepoRoot rev-parse HEAD).Trim()
        $FinalizeArguments = @(
            'finalize', '/evidence',
            '--run-id', $RunId,
            '--project', $ProjectName,
            '--scenario', $Scenario,
            '--verdict', $Verdict,
            '--started-at', $StartedAt,
            '--finished-at', $FinishedAt,
            '--git-revision', $GitRevision,
            '--ros-image', $RosImage,
            '--ros-image-id', $RosImageId,
            '--px4-image', $Px4Image,
            '--px4-image-id', $Px4ImageId,
            '--vehicle', $ResolvedModel,
            '--world', $ResolvedWorld,
            '--ros-domain-id', (Get-Setting -Name 'ROS_DOMAIN_ID' -Default '0'),
            '--max-pack-bytes', $EvidenceMaxBytes.ToString()
        )
        if ($Verdict -eq 'failed') {
            $Reason = if ($null -ne $WorkflowError) {
                $WorkflowError.Exception.Message
            }
            elseif ($CleanupMessages.Count -gt 0) {
                $CleanupMessages -join '; '
            }
            else {
                'scenario workflow failed'
            }
            $FinalizeArguments += @('--error', $Reason)
        }
        try {
            Invoke-EvidenceRun -MountSource $RunDir -MountTarget '/evidence' `
                -EvidenceArguments $FinalizeArguments
        }
        catch {
            $CleanupMessages.Add("Evidence finalization failed: $($_.Exception.Message)")
        }
        if (Test-Path -LiteralPath (Join-Path $RunDir 'manifest.json')) {
            try {
                Invoke-EvidenceRun -MountSource $RunDir -MountTarget '/evidence' `
                    -EvidenceArguments @('validate', '/evidence')
            }
            catch {
                $CleanupMessages.Add("Evidence validation failed: $($_.Exception.Message)")
            }
        }
        try {
            Invoke-EvidenceRun -MountSource $EvidenceRoot -MountTarget '/artifacts' `
                -EvidenceArguments @('prune', '/artifacts', '--keep', $RetentionCount.ToString())
        }
        catch {
            $CleanupMessages.Add("Evidence retention failed: $($_.Exception.Message)")
        }
        Write-Host "Evidence pack: $RunDir"
    }

    Restore-EnvironmentValue -Name 'DRN_PROJECT_DIR' -Value $PreviousProjectDir
    Restore-EnvironmentValue -Name 'PX4_SIM_MODEL' -Value $PreviousModel
    Restore-EnvironmentValue -Name 'PX4_GZ_WORLD' -Value $PreviousWorld
    Restore-EnvironmentValue -Name 'DRN_ARTIFACT_DIR' -Value $PreviousArtifactDir

    if ($CleanupMessages.Count -gt 0 -and $null -eq $WorkflowError) {
        $WorkflowError = [InvalidOperationException]::new($CleanupMessages -join '; ')
    }
}

if ($null -ne $WorkflowError) {
    throw $WorkflowError
}
