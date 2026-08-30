param(
    [string]$BackendRoot = (Split-Path -Parent $PSScriptRoot)
)

$ErrorActionPreference = 'Stop'

function Assert-FrontendContract {
    param([bool]$Condition, [string]$Message)
    if (-not $Condition) { throw "Frappe frontend contract failed: $Message" }
}

$appRoot = Join-Path $BackendRoot 'apps\rayher_crm\rayher_crm'
$buildRoot = Join-Path $appRoot 'public\crm'
$indexPath = Join-Path $buildRoot 'index.html'
$entryPath = Join-Path $appRoot 'www\crm.py'

Assert-FrontendContract (Test-Path -LiteralPath $indexPath -PathType Leaf) 'public/crm/index.html is missing; run npm.cmd run build:frappe'
Assert-FrontendContract (Test-Path -LiteralPath $entryPath -PathType Leaf) 'authenticated /crm web entry is missing'

$indexText = Get-Content -LiteralPath $indexPath -Raw -Encoding UTF8
$entryText = Get-Content -LiteralPath $entryPath -Raw -Encoding UTF8
Assert-FrontendContract ($indexText -match '<title>PLANCK CRM</title>') 'browser title is not PLANCK CRM'
Assert-FrontendContract ($indexText -match '/assets/rayher_crm/crm/assets/.+\.js') 'built index does not use the deploy-safe Frappe asset prefix'
Assert-FrontendContract ($entryText -match '/assets/rayher_crm/crm/index\.html') '/crm does not target the packaged frontend entry'
Assert-FrontendContract ($entryText -match '\?v=\{build_token\}#/dashboard') '/crm does not version the packaged hash-router entry'
Assert-FrontendContract ($entryText -match 'frappe\.session\.user == "Guest"') '/crm does not enforce a Guest login redirect'

$assetReferences = [regex]::Matches($indexText, '(?:src|href)="/assets/rayher_crm/crm/([^"#?]+)"') | ForEach-Object { $_.Groups[1].Value }
Assert-FrontendContract ($assetReferences.Count -ge 3) 'built index has an incomplete asset reference set'
foreach ($relativePath in $assetReferences) {
    Assert-FrontendContract (Test-Path -LiteralPath (Join-Path $buildRoot $relativePath) -PathType Leaf) "missing built asset: $relativePath"
}

$javascriptFiles = @(Get-ChildItem -LiteralPath (Join-Path $buildRoot 'assets') -Filter '*.js' -File)
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

$mockGuardBytes = ($javascriptFiles | Where-Object Name -Like 'mock-identity-switch*.js' | Measure-Object Length -Sum).Sum
Assert-FrontendContract ($mockGuardBytes -le 1024) "Mock identity guard chunk is too large: $mockGuardBytes bytes"

$allFiles = @(Get-ChildItem -LiteralPath $buildRoot -Recurse -File)
$totalBytes = ($allFiles | Measure-Object Length -Sum).Sum
Assert-FrontendContract ($totalBytes -le 10MB) "Frappe frontend exceeds the 10 MiB Stage 1 budget: $totalBytes bytes"

Write-Output "Frappe frontend contract passed: files=$($allFiles.Count), bytes=$totalBytes, mockGuardBytes=$mockGuardBytes."
