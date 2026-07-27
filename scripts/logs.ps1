param(
    [ValidateSet('px4-sitl', 'ros-viz')]
    [string]$Service
)

$Arguments = @('logs')
if ($Service) {
    $Arguments += @('-Service', $Service)
}
& (Join-Path $PSScriptRoot 'simctl.ps1') @Arguments
exit $LASTEXITCODE
