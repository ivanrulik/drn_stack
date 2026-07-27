param([switch]$Force)

$Arguments = @('clean')
if ($Force) {
    $Arguments += '-Force'
}
& (Join-Path $PSScriptRoot 'simctl.ps1') @Arguments
exit $LASTEXITCODE
