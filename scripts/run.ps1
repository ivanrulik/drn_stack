[CmdletBinding()]
param(
    [Parameter(Mandatory = $true, Position = 0, ValueFromRemainingArguments = $true)]
    [AllowEmptyString()]
    [string[]]$Command
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

function ConvertTo-NativeArgument {
    param(
        [Parameter(Mandatory = $true)]
        [AllowEmptyString()]
        [string]$Argument
    )

    if ($Argument.Length -gt 0 -and $Argument -notmatch '[\s"]') {
        return $Argument
    }

    $Builder = New-Object System.Text.StringBuilder
    [void]$Builder.Append('"')
    $Backslashes = 0

    foreach ($Character in $Argument.ToCharArray()) {
        if ($Character -eq '\') {
            $Backslashes++
            continue
        }

        if ($Character -eq '"') {
            [void]$Builder.Append(('\' * (($Backslashes * 2) + 1)))
            [void]$Builder.Append('"')
            $Backslashes = 0
            continue
        }

        if ($Backslashes -gt 0) {
            [void]$Builder.Append(('\' * $Backslashes))
            $Backslashes = 0
        }

        [void]$Builder.Append($Character)
    }

    if ($Backslashes -gt 0) {
        [void]$Builder.Append(('\' * ($Backslashes * 2)))
    }

    [void]$Builder.Append('"')
    return $Builder.ToString()
}

$RepoRoot = Split-Path -Parent $PSScriptRoot
$ComposeArgs = @(
    'compose',
    '--project-name', 'drn-stack',
    '--project-directory', $RepoRoot,
    '--file', (Join-Path $RepoRoot 'compose.yaml')
)
$ContainerScript = @'
set -Eeo pipefail
source /opt/ros/humble/setup.bash
source /opt/drn_ws/install/setup.bash
set -u
exec "$@"
'@
$ContainerScript = $ContainerScript -replace "`r`n", "`n"

$ContainerCommand = @(
    'exec', '-T', 'ros-viz',
    'bash', '-lc',
    $ContainerScript,
    'bash'
) + $Command

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    throw 'Docker CLI was not found. Install or start Docker Desktop.'
}

$Docker = Get-Command docker -ErrorAction Stop
$DockerArguments = ($ComposeArgs + $ContainerCommand |
    ForEach-Object { ConvertTo-NativeArgument $_ }) -join ' '
$StartInfo = New-Object System.Diagnostics.ProcessStartInfo
$StartInfo.FileName = $Docker.Source
$StartInfo.Arguments = $DockerArguments
$StartInfo.UseShellExecute = $false

$Process = [System.Diagnostics.Process]::Start($StartInfo)
$Process.WaitForExit()
if ($Process.ExitCode -ne 0) {
    throw "Container command failed with exit code $($Process.ExitCode)."
}
