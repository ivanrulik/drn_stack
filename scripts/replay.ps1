[CmdletBinding()]
param(
    [Parameter(Mandatory = $true, Position = 0)]
    [string]$EvidenceDirectory,

    [Parameter(Position = 1)]
    [string]$Image = 'drn-stack/ros-viz:humble',

    [ValidateRange(1, 65535)]
    [int]$Port = $(if ($env:FOXGLOVE_PORT) { $env:FOXGLOVE_PORT } else { 8765 })
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    throw 'Docker CLI was not found. Install or start Docker Desktop.'
}
& docker info *> $null
if ($LASTEXITCODE -ne 0) {
    throw 'Docker Desktop is not running or its Linux daemon is unavailable.'
}
$EvidenceRoot = (Resolve-Path -LiteralPath $EvidenceDirectory).Path
if (-not (Test-Path -LiteralPath $EvidenceRoot -PathType Container)) {
    throw "Evidence directory was not found: $EvidenceDirectory"
}
& docker image inspect $Image *> $null
if ($LASTEXITCODE -ne 0) {
    throw "Replay image was not found: $Image. Run an evidence-enabled scenario first."
}
$Owners = @(& docker ps --filter "publish=$Port" --format '{{.Names}}')
if ($Owners.Count -gt 0) {
    throw "Port $Port is already published by Docker container: $($Owners -join ', ')"
}

$Command = @'
source /usr/local/bin/drn-ros-environment
set -u
exec /usr/local/bin/drn-evidence "$@"
'@
$Command = $Command -replace "`r`n", "`n"
$Mount = "type=bind,src=$EvidenceRoot,dst=/evidence,readonly"
Write-Host "Open Foxglove at ws://localhost:$Port; replay exits when the bag ends."
& docker run --rm --init `
    --publish "127.0.0.1`:$Port`:$Port/tcp" `
    --mount $Mount `
    --entrypoint bash `
    $Image -lc $Command bash replay /evidence --port $Port
if ($LASTEXITCODE -ne 0) {
    throw "Evidence replay failed with exit code $LASTEXITCODE."
}
