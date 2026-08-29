$ErrorActionPreference = 'Stop'

$QgcHost = if ($env:QGC_HOST) { $env:QGC_HOST } else { 'host.docker.internal' }
$QgcPortText = if ($env:QGC_PORT) { $env:QGC_PORT } else { '14550' }
$QgcPort = 0
if (-not [int]::TryParse($QgcPortText, [ref]$QgcPort) -or
    $QgcPort -lt 1 -or $QgcPort -gt 65535) {
    throw "Invalid QGC_PORT '$QgcPortText'; expected an integer from 1 through 65535."
}

Write-Host 'QGroundControl connectivity diagnostic'
Write-Host "Configured PX4 destination: ${QgcHost}:$QgcPort/udp"
Write-Host ''

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    throw 'Docker CLI was not found.'
}
& docker info *> $null
if ($LASTEXITCODE -ne 0) {
    throw "Docker's Linux daemon is unavailable."
}

$ContainerId = @(
    & docker ps `
        --filter 'label=com.docker.compose.project=drn-stack' `
        --filter 'label=com.docker.compose.service=ros-viz' `
        --format '{{.ID}}'
) | Select-Object -First 1
if (-not $ContainerId) {
    throw 'The drn-stack ros-viz container is not running. Start it with .\scripts\run-sim.ps1.'
}
Write-Host "PASS: drn-stack ros-viz container is running ($ContainerId)."

$Container = @(& docker inspect $ContainerId | ConvertFrom-Json)[0]
$NetworkProperty = $Container.NetworkSettings.Networks.PSObject.Properties |
    Select-Object -First 1
if (-not $NetworkProperty) {
    throw 'Could not resolve the container network path.'
}
$NetworkName = $NetworkProperty.Name
$ContainerIp = $NetworkProperty.Value.IPAddress
$GatewayIp = $NetworkProperty.Value.Gateway
$Network = @(& docker network inspect $NetworkName | ConvertFrom-Json)[0]
$NetworkSubnet = $Network.IPAM.Config[0].Subnet
Write-Host "Docker path: $ContainerIp -> $GatewayIp on $NetworkName ($NetworkSubnet)"

if ($QgcHost -ne 'host.docker.internal') {
    Write-Host ''
    Write-Host 'INFO: QGC_HOST is remote or custom, so local listener checks are skipped.'
    Write-Host "Verify UDP $QgcPort on '$QgcHost' from that host."
    exit 0
}

$Listener = Get-NetUDPEndpoint -LocalPort $QgcPort -ErrorAction SilentlyContinue
$ReachableListener = $Listener | Where-Object {
    $_.LocalAddress -in @('0.0.0.0', '::', $GatewayIp)
}
if ($ReachableListener) {
    Write-Host "PASS: a host process is listening on UDP $QgcPort."
    Write-Host 'No locally observable QGroundControl connectivity problem was found.'
    exit 0
}

if ($Listener) {
    Write-Error "UDP $QgcPort is listening only on an address Docker cannot reach. Enable QGroundControl UDP autoconnect so it binds a wildcard or $GatewayIp."
}
Write-Error "No host process is listening on UDP $QgcPort. Start QGroundControl and keep UDP autoconnect enabled on that port."
