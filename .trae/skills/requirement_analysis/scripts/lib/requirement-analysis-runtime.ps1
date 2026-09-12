# Requirement Analysis Runtime Library
# Production-safe wrapper for invoking sub-scripts with:
#   1) Explicit Bypass of ExecutionPolicy (no & call that inherits Restricted)
#   2) Strong validation of output JSON before returning to caller
#   3) Clear error messages that name the offending script + output path

if (-not $PSScriptRoot) { $PSScriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path }
if ([string]::IsNullOrWhiteSpace($env:TEMP)) { $env:TEMP = [System.IO.Path]::GetTempPath() }

function Build-ArgumentList {
    param([hashtable]$Arguments)
    $list = New-Object System.Collections.Generic.List[string]
    if ($null -eq $Arguments) { return ,$list }
    foreach ($key in $Arguments.Keys) {
        $list.Add("-$key")
        $list.Add([string]$Arguments[$key])
    }
    return ,$list
}

function Invoke-RaScriptRaw {
    param(
        [Parameter(Mandatory=$true)][string]$ScriptPath,
        [hashtable]$Arguments
    )
    if (-not (Test-Path -LiteralPath $ScriptPath)) {
        throw "Invoke-RaScriptRaw: script not found: $ScriptPath"
    }
    $argList = Build-ArgumentList -Arguments $Arguments
    $stdout = & powershell -NoProfile -ExecutionPolicy Bypass -File $ScriptPath @argList 2>&1 | Out-String
    if ($LASTEXITCODE -ne 0) {
        throw "Invoke-RaScriptRaw failed (exit=$LASTEXITCODE): $ScriptPath`n$stdout"
    }
    return $stdout
}

function Invoke-RaScriptToObject {
    param(
        [Parameter(Mandatory=$true)][string]$ScriptPath,
        [hashtable]$Arguments,
        [string]$ExpectedTopLevelProperty = ""
    )
    $raw = Invoke-RaScriptRaw -ScriptPath $ScriptPath -Arguments $Arguments
    if ([string]::IsNullOrWhiteSpace($raw)) {
        throw "Invoke-RaScriptToObject: empty output from $ScriptPath"
    }
    try {
        $obj = ($raw | ConvertFrom-Json)
    } catch {
        throw "Invoke-RaScriptToObject: invalid JSON from $ScriptPath : $($_.Exception.Message)`n-----RAW-----$raw"
    }
    if ($null -eq $obj) {
        throw "Invoke-RaScriptToObject: null JSON object from $ScriptPath"
    }
    if (-not [string]::IsNullOrWhiteSpace($ExpectedTopLevelProperty)) {
        $prop = $obj | Get-Member -Name $ExpectedTopLevelProperty -MemberType NoteProperty,Properties -ErrorAction SilentlyContinue
        if ($null -eq $prop) {
            throw "Invoke-RaScriptToObject: missing expected top-level property '$ExpectedTopLevelProperty' from $ScriptPath"
        }
    }
    return $obj
}

function Invoke-RaScriptToFile {
    param(
        [Parameter(Mandatory=$true)][string]$ScriptPath,
        [hashtable]$Arguments,
        [Parameter(Mandatory=$true)][string]$OutputJsonPath,
        [switch]$ValidateMinSize,
        [int]$MinSizeBytes = 200
    )
    if (Test-Path -LiteralPath $OutputJsonPath) {
        Remove-Item -LiteralPath $OutputJsonPath -Force -ErrorAction SilentlyContinue
    }
    $raw = Invoke-RaScriptRaw -ScriptPath $ScriptPath -Arguments $Arguments
    if (-not (Test-Path -LiteralPath $OutputJsonPath)) {
        throw "Invoke-RaScriptToFile: output not created at $OutputJsonPath by $ScriptPath`n-----RAW-----$raw"
    }
    $fi = Get-Item -LiteralPath $OutputJsonPath
    if ($ValidateMinSize -and $fi.Length -lt $MinSizeBytes) {
        $content = Get-Content -LiteralPath $OutputJsonPath -Raw -Encoding UTF8
        throw "Invoke-RaScriptToFile: output too small ($($fi.Length) < $MinSizeBytes bytes) from $ScriptPath -> $OutputJsonPath`n-----CONTENT-----$content"
    }
    try {
        $null = (Get-Content -LiteralPath $OutputJsonPath -Raw -Encoding UTF8 | ConvertFrom-Json)
    } catch {
        $content = Get-Content -LiteralPath $OutputJsonPath -Raw -Encoding UTF8
        throw "Invoke-RaScriptToFile: invalid JSON output from $ScriptPath -> $OutputJsonPath : $($_.Exception.Message)`n-----CONTENT-----$content"
    }
    return $OutputJsonPath
}
