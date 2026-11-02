<#
.SYNOPSIS
    One-command setup for Socra.

.DESCRIPTION
    Builds the web client, registers the MCP server with Claude Code,
    and pre-downloads speech models.

.PARAMETER Shortcut
    Install desktop shortcut after setup.

.PARAMETER SkipModels
    Skip model pre-downloading.

.PARAMETER SkipWeb
    Skip building the web client.

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File setup.ps1
#>
param(
    [switch]$Shortcut,
    [switch]$SkipModels,
    [switch]$SkipWeb
)

$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot

$argsList = @('run', '--project', 'server', 'socra-server', 'setup')
if ($Shortcut) { $argsList += '--shortcut' }
if ($SkipModels) { $argsList += '--skip-models' }
if ($SkipWeb) { $argsList += '--skip-web' }

uv @argsList
if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}
