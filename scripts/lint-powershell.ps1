[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$ParseErrors = @()

Get-ChildItem -Path $PSScriptRoot -Recurse -File -Filter '*.ps1' |
    ForEach-Object {
        $Tokens = $null
        [void][System.Management.Automation.Language.Parser]::ParseFile(
            $_.FullName,
            [ref]$Tokens,
            [ref]$ParseErrors
        )
    }

if ($ParseErrors.Count -gt 0) {
    $ParseErrors | ForEach-Object {
        Write-Error "$($_.Extent.File):$($_.Extent.StartLineNumber): $($_.Message)"
    }
    exit 1
}

Write-Host 'PowerShell syntax checks passed.'
