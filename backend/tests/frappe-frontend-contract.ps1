#Requires -Version 7.0

[CmdletBinding()]
param(
    [string]$BackendRoot = (Split-Path -Parent $PSScriptRoot),
    [switch]$VerifyRebuild
)

$ErrorActionPreference = 'Stop'

function Assert-FrontendContract {
    param([bool]$Condition, [string]$Message)
    if (-not $Condition) { throw "Frappe frontend contract failed: $Message" }
}

$appRoot = Join-Path $BackendRoot 'apps/rayher_crm/rayher_crm'
$buildRoot = Join-Path $appRoot 'public/crm'
$indexPath = Join-Path $buildRoot 'index.html'
$entryPath = Join-Path $appRoot 'www/crm.py'

Assert-FrontendContract (Test-Path -LiteralPath $indexPath -PathType Leaf) 'public/crm/index.html is missing; run npm.cmd run build:frappe'
Assert-FrontendContract (Test-Path -LiteralPath $entryPath -PathType Leaf) 'authenticated /crm web entry is missing'

$indexText = Get-Content -LiteralPath $indexPath -Raw -Encoding UTF8
$entryText = Get-Content -LiteralPath $entryPath -Raw -Encoding UTF8
Assert-FrontendContract ($indexText -match '<title>栖衡 CRM · QIHENG</title>') 'browser title is not QIHENG CRM'
Assert-FrontendContract ($indexText -match '/assets/rayher_crm/crm/assets/.+\.js') 'built index does not use the deploy-safe Frappe asset prefix'
Assert-FrontendContract ($entryText -match '/assets/rayher_crm/crm/index\.html') '/crm does not target the packaged frontend entry'
Assert-FrontendContract ($entryText -match '\?v=\{build_token\}#/dashboard') '/crm does not version the packaged hash-router entry'
Assert-FrontendContract ($entryText -match 'frappe\.session\.user == "Guest"') '/crm does not enforce a Guest login redirect'

$assetReferences = [regex]::Matches($indexText, '(?:src|href)="/assets/rayher_crm/crm/([^"#?]+)"') | ForEach-Object { $_.Groups[1].Value }
Assert-FrontendContract ($assetReferences.Count -ge 3) 'built index has an incomplete asset reference set'
foreach ($relativePath in $assetReferences) {
    Assert-FrontendContract (Test-Path -LiteralPath (Join-Path $buildRoot $relativePath) -PathType Leaf) "missing built asset: $relativePath"
}

$javascriptFiles = @(Get-ChildItem -LiteralPath (Join-Path $buildRoot 'assets') -Filter '*.js' -Recurse -File -Force)
Assert-FrontendContract ($javascriptFiles.Count -gt 0) 'no JavaScript chunks were built'
$endpointHit = $javascriptFiles | Select-String -SimpleMatch 'bootstrap.get_bootstrap' -List
Assert-FrontendContract ($null -ne $endpointHit) 'Frappe bootstrap endpoint is absent from the bundle'

$forbiddenCustomer = [Text.Encoding]::UTF8.GetString([Convert]::FromBase64String('5Y+w56ev55S177yI5Lit5Zu977yJ5pyJ6ZmQ5YWs5Y+4'))
$forbiddenRuntimeMarkers = @(
    $forbiddenCustomer,
    'REQ-001',
    'createMockApi',
    'Mock 数据',
    'Mock 模式',
    'Mock Demo 权限契约',
    'localhost',
    '127.0.0.1',
    '0.0.0.0'
)
$forbiddenSeedHits = $javascriptFiles | Select-String -SimpleMatch $forbiddenRuntimeMarkers -List
Assert-FrontendContract ($null -eq $forbiddenSeedHits) 'known Mock customer/requirement seed leaked into the Frappe bundle'

$mockGuardMeasurement = $javascriptFiles | Where-Object Name -Like 'mock-identity-switch*.js' | Measure-Object Length -Sum
$mockGuardBytes = if ($null -eq $mockGuardMeasurement.Sum) { 0L } else { [long]$mockGuardMeasurement.Sum }
Assert-FrontendContract ($mockGuardBytes -le 1024) "Mock identity guard chunk is too large: $mockGuardBytes bytes"

$allFiles = @(Get-ChildItem -LiteralPath $buildRoot -Recurse -File -Force)
$totalBytes = ($allFiles | Measure-Object Length -Sum).Sum
Assert-FrontendContract ($totalBytes -le 10MB) "Frappe frontend exceeds the 10 MiB Stage 1 budget: $totalBytes bytes"

if ($VerifyRebuild) {
    $repositoryRoot = (Resolve-Path -LiteralPath (Join-Path $BackendRoot '..')).Path
    $scratchRoot = [IO.Path]::GetFullPath((Join-Path $BackendRoot 'build'))
    New-Item -ItemType Directory -Path $scratchRoot -Force | Out-Null
    $comparisonRoot = Join-Path $scratchRoot ("frontend-contract-{0}" -f [Guid]::NewGuid().ToString('N'))
    $comparisonPath = [IO.Path]::GetFullPath($comparisonRoot)
    $pathComparison = if ($IsWindows) { [StringComparison]::OrdinalIgnoreCase } else { [StringComparison]::Ordinal }
    Assert-FrontendContract ($comparisonPath.StartsWith($scratchRoot + [IO.Path]::DirectorySeparatorChar, $pathComparison)) 'temporary rebuild path escaped backend/build'
    $commandExtension = if ($IsWindows) { '.cmd' } else { '' }
    $viteCommand = Join-Path $repositoryRoot "node_modules/.bin/vite$commandExtension"
    $primaryError = $null
    try {
        Push-Location $repositoryRoot
        try {
            & $viteCommand build --mode frappe --outDir $comparisonPath --emptyOutDir --logLevel error
            Assert-FrontendContract ($LASTEXITCODE -eq 0) "independent Vite rebuild failed with exit code $LASTEXITCODE"
        }
        finally {
            Pop-Location
        }

        $builtFiles = @($allFiles | ForEach-Object {
            [pscustomobject]@{
                RelativePath = $_.FullName.Substring($buildRoot.Length + 1).Replace('\', '/')
                FullName = $_.FullName
            }
        })
        $comparisonFiles = @(Get-ChildItem -LiteralPath $comparisonPath -Recurse -File -Force | ForEach-Object {
            [pscustomobject]@{
                RelativePath = $_.FullName.Substring($comparisonPath.Length + 1).Replace('\', '/')
                FullName = $_.FullName
            }
        })
        Assert-FrontendContract ($builtFiles.Count -eq $comparisonFiles.Count) "frontend rebuild file count differs: packaged=$($builtFiles.Count), rebuilt=$($comparisonFiles.Count)"
        $comparisonMap = [Collections.Generic.Dictionary[string, string]]::new([StringComparer]::Ordinal)
        foreach ($file in $comparisonFiles) {
            $comparisonMap.Add($file.RelativePath, $file.FullName)
        }
        foreach ($file in $builtFiles) {
            Assert-FrontendContract ($comparisonMap.ContainsKey($file.RelativePath)) "packaged frontend contains a file absent from a clean rebuild: $($file.RelativePath)"
            $packagedBytes = [IO.File]::ReadAllBytes($file.FullName)
            $rebuiltBytes = [IO.File]::ReadAllBytes($comparisonMap[$file.RelativePath])
            Assert-FrontendContract ([Collections.StructuralComparisons]::StructuralEqualityComparer.Equals($packagedBytes, $rebuiltBytes)) "packaged frontend differs from a clean rebuild: $($file.RelativePath)"
        }
    }
    catch {
        $primaryError = $_
        throw
    }
    finally {
        if (Test-Path -LiteralPath $comparisonPath -PathType Container) {
            try {
                [IO.Directory]::Delete($comparisonPath, $true)
            }
            catch {
                if ($null -eq $primaryError) {
                    throw
                }
                Write-Warning "Could not remove frontend comparison directory '$comparisonPath': $($_.Exception.Message)"
            }
        }
    }
}

Write-Output "Frappe frontend contract passed: files=$($allFiles.Count), bytes=$totalBytes, mockGuardBytes=$mockGuardBytes."
