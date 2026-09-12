# Requirement Analysis Schema Test
# PowerShell 5 compatible deterministic contract test

[CmdletBinding()]
param()

if (-not $PSScriptRoot) { $PSScriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path }
$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $PSScriptRoot
$BaseDir = $Root
$SchemaDir = Join-Path $BaseDir "schemas"
$TestDir = Join-Path $BaseDir "evals\fixtures\unit\schema"

function Read-JsonFile {
    param([string]$Path)
    return (Get-Content -Raw -Encoding UTF8 -Path $Path | ConvertFrom-Json)
}

function Get-PropertyNames {
    param($Object)
    if ($null -eq $Object) { return @() }
    return @($Object.PSObject.Properties.Name)
}

function Is-JsonObject {
    param($Value)
    return ($null -ne $Value -and $Value -is [pscustomobject])
}

function Is-JsonArray {
    param($Value)
    if ($null -eq $Value) { return $false }
    return ($Value -is [System.Array] -or $Value -is [System.Collections.IList])
}

function Resolve-SchemaNode {
    param(
        $SchemaRoot,
        $Node
    )

    if ($null -eq $Node) { return $null }

    if ($Node.PSObject.Properties.Name -contains '$ref') {
        $ref = $Node.'$ref'
        if ($ref -notmatch '^#/definitions/(?<name>.+)$') {
            throw "Unsupported ref format: $ref"
        }
        $name = $Matches['name']
        return $SchemaRoot.definitions.$name
    }

    return $Node
}

function Add-Error {
    param(
        [System.Collections.Generic.List[string]]$Errors,
        [string]$Message
    )
    $Errors.Add($Message) | Out-Null
}

function Validate-Node {
    param(
        $Value,
        $SchemaRoot,
        $SchemaNode,
        [string]$Path,
        [System.Collections.Generic.List[string]]$Errors
    )

    $Resolved = Resolve-SchemaNode -SchemaRoot $SchemaRoot -Node $SchemaNode
    if ($null -eq $Resolved) { return }

    if ($Resolved.PSObject.Properties.Name -contains 'const') {
        if ($Value -ne $Resolved.const) {
            Add-Error -Errors $Errors -Message "$Path must equal '$($Resolved.const)'"
            return
        }
    }

    if ($Resolved.PSObject.Properties.Name -contains 'enum') {
        $allowed = @($Resolved.enum)
        if ($allowed -notcontains $Value) {
            Add-Error -Errors $Errors -Message "$Path must be one of [$($allowed -join ', ')]"
            return
        }
    }

    if (-not ($Resolved.PSObject.Properties.Name -contains 'type')) {
        return
    }

    switch ($Resolved.type) {
        "object" {
            if (-not (Is-JsonObject -Value $Value)) {
                Add-Error -Errors $Errors -Message "$Path must be an object"
                return
            }

            $required = @()
            if ($Resolved.PSObject.Properties.Name -contains 'required') {
                $required = @($Resolved.required)
            }

            $actualNames = Get-PropertyNames -Object $Value
            foreach ($req in $required) {
                if ($actualNames -notcontains $req) {
                    Add-Error -Errors $Errors -Message "$Path.$req is required"
                }
            }

            $allowedNames = @()
            if ($Resolved.PSObject.Properties.Name -contains 'properties') {
                $allowedNames = Get-PropertyNames -Object $Resolved.properties
            }

            if (($Resolved.PSObject.Properties.Name -contains 'additionalProperties') -and ($Resolved.additionalProperties -eq $false)) {
                foreach ($actual in $actualNames) {
                    if ($allowedNames -notcontains $actual) {
                        Add-Error -Errors $Errors -Message "$Path.$actual is not allowed"
                    }
                }
            }

            foreach ($propName in $allowedNames) {
                if ($actualNames -contains $propName) {
                    $childValue = $Value.$propName
                    $childSchema = $Resolved.properties.$propName
                    Validate-Node -Value $childValue -SchemaRoot $SchemaRoot -SchemaNode $childSchema -Path "$Path.$propName" -Errors $Errors
                }
            }
        }
        "array" {
            if (-not (Is-JsonArray -Value $Value)) {
                Add-Error -Errors $Errors -Message "$Path must be an array"
                return
            }

            $items = @($Value)
            if (($Resolved.PSObject.Properties.Name -contains 'minItems') -and ($items.Count -lt [int]$Resolved.minItems)) {
                Add-Error -Errors $Errors -Message "$Path must contain at least $($Resolved.minItems) item(s)"
            }

            if ($Resolved.PSObject.Properties.Name -contains 'items') {
                for ($i = 0; $i -lt $items.Count; $i++) {
                    Validate-Node -Value $items[$i] -SchemaRoot $SchemaRoot -SchemaNode $Resolved.items -Path "$Path[$i]" -Errors $Errors
                }
            }
        }
        "string" {
            if ($Value -isnot [string]) {
                Add-Error -Errors $Errors -Message "$Path must be a string"
                return
            }

            if (($Resolved.PSObject.Properties.Name -contains 'minLength') -and ($Value.Length -lt [int]$Resolved.minLength)) {
                Add-Error -Errors $Errors -Message "$Path must have at least $($Resolved.minLength) character(s)"
            }
        }
        "number" {
            if (($Value -isnot [double]) -and ($Value -isnot [float]) -and ($Value -isnot [decimal]) -and ($Value -isnot [int]) -and ($Value -isnot [long])) {
                Add-Error -Errors $Errors -Message "$Path must be a number"
                return
            }

            $numberValue = [double]$Value
            if (($Resolved.PSObject.Properties.Name -contains 'minimum') -and ($numberValue -lt [double]$Resolved.minimum)) {
                Add-Error -Errors $Errors -Message "$Path must be >= $($Resolved.minimum)"
            }
            if (($Resolved.PSObject.Properties.Name -contains 'maximum') -and ($numberValue -gt [double]$Resolved.maximum)) {
                Add-Error -Errors $Errors -Message "$Path must be <= $($Resolved.maximum)"
            }
        }
        "boolean" {
            if ($Value -isnot [bool]) {
                Add-Error -Errors $Errors -Message "$Path must be a boolean"
            }
        }
        default {
            throw "Unsupported schema type: $($Resolved.type)"
        }
    }
}

function Test-JsonAgainstSchema {
    param(
        [string]$SchemaPath,
        [string]$JsonPath
    )

    $schema = Read-JsonFile -Path $SchemaPath
    $json = Read-JsonFile -Path $JsonPath
    $errors = New-Object 'System.Collections.Generic.List[string]'

    Validate-Node -Value $json -SchemaRoot $schema -SchemaNode $schema -Path '$' -Errors $errors

    return $errors
}

$inputSchemaPath = Join-Path $SchemaDir "input.schema.json"
$outputSchemaPath = Join-Path $SchemaDir "output.schema.json"

$cases = @(
    @{
        Name = "input.valid"
        Schema = $inputSchemaPath
        Json = (Join-Path $TestDir "input.valid.json")
        ShouldPass = $true
    },
    @{
        Name = "input.invalid"
        Schema = $inputSchemaPath
        Json = (Join-Path $TestDir "input.invalid.json")
        ShouldPass = $false
    },
    @{
        Name = "output.valid"
        Schema = $outputSchemaPath
        Json = (Join-Path $TestDir "output.valid.json")
        ShouldPass = $true
    },
    @{
        Name = "output.invalid"
        Schema = $outputSchemaPath
        Json = (Join-Path $TestDir "output.invalid.json")
        ShouldPass = $false
    }
)

$failedCases = @()

Write-Host ""
Write-Host "==============================================" -ForegroundColor Magenta
Write-Host " Requirement Analysis Schema Test" -ForegroundColor Magenta
Write-Host "==============================================" -ForegroundColor Magenta
Write-Host ""

foreach ($case in $cases) {
    $errors = Test-JsonAgainstSchema -SchemaPath $case.Schema -JsonPath $case.Json
    $passed = ($errors.Count -eq 0)

    if ($case.ShouldPass -and $passed) {
        Write-Host "[PASS] $($case.Name)" -ForegroundColor Green
        continue
    }

    if ((-not $case.ShouldPass) -and (-not $passed)) {
        Write-Host "[EXPECTED FAIL] $($case.Name)" -ForegroundColor Yellow
        foreach ($err in $errors) {
            Write-Host "  - $err" -ForegroundColor DarkYellow
        }
        continue
    }

    $failedCases += $case.Name
    Write-Host "[FAIL] $($case.Name)" -ForegroundColor Red
    if ($errors.Count -eq 0) {
        Write-Host "  - expected validation failure but got none" -ForegroundColor DarkRed
    } else {
        foreach ($err in $errors) {
            Write-Host "  - $err" -ForegroundColor DarkRed
        }
    }
}

Write-Host ""
if ($failedCases.Count -gt 0) {
    Write-Host "Schema test failed: $($failedCases -join ', ')" -ForegroundColor Red
    exit 1
}

Write-Host "All schema tests passed." -ForegroundColor Green
exit 0
