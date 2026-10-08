#Requires -Version 7.0

[CmdletBinding()]
param(
    [string]$ProjectName = 'rayher-crm-stage1-tests',
    [string]$SiteName = 'rayher-crm.test',
    [string]$EnvFile = 'backend/test.env.example',
    [string]$ComposeFile = 'backend/compose.yaml',
    [ValidateSet('threads', 'forks')]
    [string]$FrontendTestPool = 'threads',
    [ValidateRange(5000, 60000)]
    [int]$FrontendTestTimeout = 5000,
    [switch]$StartBackend
)

$ErrorActionPreference = 'Stop'
$repositoryRoot = (Resolve-Path -LiteralPath (Join-Path (Split-Path -Parent $PSScriptRoot) '..')).Path
$pathComparison = if ($IsWindows) { [StringComparison]::OrdinalIgnoreCase } else { [StringComparison]::Ordinal }
$expectedTestEnvFile = [IO.Path]::GetFullPath((Join-Path $repositoryRoot 'backend/test.env.example'))
$expectedComposeFile = [IO.Path]::GetFullPath((Join-Path $repositoryRoot 'backend/compose.yaml'))
$resolvedEnvFile = [IO.Path]::GetFullPath($EnvFile, $repositoryRoot)
$resolvedComposeFile = [IO.Path]::GetFullPath($ComposeFile, $repositoryRoot)

if ($ProjectName -ne 'rayher-crm-stage1-tests') {
    throw "Release gate requires the isolated project 'rayher-crm-stage1-tests'."
}
if ($SiteName -ne 'rayher-crm.test') {
    throw "Release gate requires the isolated site 'rayher-crm.test'."
}
if (-not $resolvedEnvFile.Equals($expectedTestEnvFile, $pathComparison)) {
    throw 'Release gate requires backend/test.env.example.'
}
if (-not $resolvedComposeFile.Equals($expectedComposeFile, $pathComparison)) {
    throw 'Release gate requires backend/compose.yaml.'
}
if (-not $StartBackend) {
    throw 'Release gate requires -StartBackend so backend tests cannot run against a stale stack.'
}
$EnvFile = $resolvedEnvFile
$ComposeFile = $resolvedComposeFile

function Invoke-CheckedCommand {
    param(
        [string]$Label,
        [string]$Command,
        [string[]]$Arguments
    )

    & $Command @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "$Label failed with exit code $LASTEXITCODE."
    }
}

function Assert-ArchiveHash {
    param(
        [string]$Label,
        [string]$Path,
        [string]$ExpectedHash
    )

    $actualHash = (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash
    if ($actualHash -ne $ExpectedHash) {
        throw "$Label changed after verification: expected $ExpectedHash, got $actualHash."
    }
}

$composeEnvironmentNames = @(
    'ALLOW_TESTS', 'CLAMAV_IMAGE', 'COMPOSE_PROJECT_NAME', 'CRM_APP_ARCHIVE',
    'CRM_APP_ARCHIVE_SHA256', 'CRM_IMAGE', 'CRM_TEST_SITE', 'FRAPPE_BASE_IMAGE',
    'HTTP_BIND_ADDRESS', 'HTTP_PORT', 'MARIADB_IMAGE', 'REDIS_IMAGE', 'SITE_NAME'
)
$savedComposeEnvironment = @{}
foreach ($variableName in $composeEnvironmentNames) {
    $savedComposeEnvironment[$variableName] = [Environment]::GetEnvironmentVariable($variableName, 'Process')
    Remove-Item -LiteralPath "Env:$variableName" -ErrorAction SilentlyContinue
}

$backendStackTouched = $false
$gateSucceeded = $false
$locationPushed = $false
try {
    Push-Location $repositoryRoot
    $locationPushed = $true
    $worktreeStatus = @(& git status --porcelain --untracked-files=normal)
    if ($LASTEXITCODE -ne 0) {
        throw 'Could not inspect the Git worktree.'
    }
    if ($worktreeStatus.Count -gt 0) {
        throw 'Release gate requires a clean Git worktree.'
    }

    $commandExtension = if ($IsWindows) { '.cmd' } else { '' }
    $binDirectory = Join-Path $repositoryRoot 'node_modules/.bin'
    $powerShellCommand = Join-Path $PSHOME $(if ($IsWindows) { 'pwsh.exe' } else { 'pwsh' })
    $composeContract = Join-Path $repositoryRoot 'backend/tests/compose-contract.ps1'
    $httpsProxyContract = Join-Path $repositoryRoot 'backend/tests/https-proxy-contract.ps1'
    $frontendContract = Join-Path $repositoryRoot 'backend/tests/frappe-frontend-contract.ps1'
    $packageContract = Join-Path $repositoryRoot 'backend/tests/app-package-contract.ps1'
    $prepareArchive = Join-Path $repositoryRoot 'backend/scripts/prepare-app-build-context.ps1'
    $archiveContract = Join-Path $repositoryRoot 'backend/tests/app-archive-contract.ps1'
    $backendTests = Join-Path $repositoryRoot 'backend/tests/run-backend-tests.ps1'
    $productionArchive = Join-Path $repositoryRoot 'backend/build/rayher_crm.zip'
    $testArchive = Join-Path $repositoryRoot 'backend/build/rayher_crm-tests.zip'
    $productionEnvFile = Join-Path $repositoryRoot 'backend/.env.example'

    Invoke-CheckedCommand 'TypeScript typecheck' (Join-Path $binDirectory "vue-tsc$commandExtension") @('--noEmit')
    Invoke-CheckedCommand 'Frontend tests' (Join-Path $binDirectory "vitest$commandExtension") @(
        'run', '--silent=passed-only', "--pool=$FrontendTestPool", "--testTimeout=$FrontendTestTimeout"
    )
    Invoke-CheckedCommand 'Production build' (Join-Path $binDirectory "vite$commandExtension") @(
        'build', '--mode', 'frappe',
        '--outDir', 'backend/apps/rayher_crm/rayher_crm/public/crm', '--emptyOutDir'
    )

    Invoke-CheckedCommand 'Compose contract' $powerShellCommand @('-NoProfile', '-File', $composeContract)
    Invoke-CheckedCommand 'HTTPS proxy contract' $powerShellCommand @('-NoProfile', '-File', $httpsProxyContract)
    Invoke-CheckedCommand 'Frappe frontend contract' $powerShellCommand @('-NoProfile', '-File', $frontendContract)
    Invoke-CheckedCommand 'App package contract' $powerShellCommand @('-NoProfile', '-File', $packageContract)
    Invoke-CheckedCommand 'Production archive preparation' $powerShellCommand @('-NoProfile', '-File', $prepareArchive, '-OutputArchive', $productionArchive)
    Invoke-CheckedCommand 'Production archive contract' $powerShellCommand @('-NoProfile', '-File', $archiveContract, '-ArchivePath', $productionArchive)
    $productionArchiveHash = (Get-FileHash -LiteralPath $productionArchive -Algorithm SHA256).Hash

    Invoke-CheckedCommand 'Backend test archive preparation' $powerShellCommand @('-NoProfile', '-File', $prepareArchive, '-OutputArchive', $testArchive, '-IncludeTests')
    Invoke-CheckedCommand 'Backend test archive contract' $powerShellCommand @('-NoProfile', '-File', $archiveContract, '-ArchivePath', $testArchive, '-IncludeTests')
    $testArchiveHash = (Get-FileHash -LiteralPath $testArchive -Algorithm SHA256).Hash
    Invoke-CheckedCommand 'Clean backend test stack' 'docker' @(
        'compose', '--project-name', $ProjectName, '--env-file', $EnvFile,
        '-f', $ComposeFile, 'down', '--volumes', '--remove-orphans'
    )
    Assert-ArchiveHash 'Backend test archive' $testArchive $testArchiveHash
    Invoke-CheckedCommand 'Backend test image build' 'docker' @(
        'compose', '--project-name', $ProjectName, '--env-file', $EnvFile,
        '-f', $ComposeFile, 'build',
        '--build-arg', 'CRM_APP_ARCHIVE=build/rayher_crm-tests.zip',
        '--build-arg', "CRM_APP_ARCHIVE_SHA256=$testArchiveHash", 'backend'
    )
    Invoke-CheckedCommand 'Backend native JUnit tools' 'docker' @(
        'build', '-f', 'backend/ci/Dockerfile.test',
        '--build-arg', 'CRM_TEST_BASE_IMAGE=rayher-crm-stage1:v15-test',
        '--tag', 'rayher-crm-stage1:v15-test', 'backend/ci'
    )
    $backendStackTouched = $true
    Invoke-CheckedCommand 'Backend stack startup' 'docker' @(
        'compose', '--project-name', $ProjectName, '--env-file', $EnvFile,
        '-f', $ComposeFile, 'up', '-d', '--no-build', 'backend'
    )

    Invoke-CheckedCommand 'Backend tests' $powerShellCommand @(
        '-NoProfile', '-File', $backendTests,
        '-ProjectName', $ProjectName, '-SiteName', $SiteName,
        '-EnvFile', $EnvFile, '-ComposeFile', $ComposeFile,
        '-ReportDirectory', 'backend/build/ci-reports'
    )

    Assert-ArchiveHash 'Production archive' $productionArchive $productionArchiveHash
    $previousCrmImage = [Environment]::GetEnvironmentVariable('CRM_IMAGE', 'Process')
    try {
        $env:CRM_IMAGE = 'rayher-crm-release-gate:v15'
        Invoke-CheckedCommand 'Production image build' 'docker' @(
            'compose', '--project-name', 'rayher-crm-production-artifact-check',
            '--env-file', $productionEnvFile, '-f', $ComposeFile, 'build',
            '--build-arg', "CRM_APP_ARCHIVE_SHA256=$productionArchiveHash", 'backend'
        )
    }
    finally {
        if ($null -eq $previousCrmImage) {
            Remove-Item -LiteralPath 'Env:CRM_IMAGE' -ErrorAction SilentlyContinue
        }
        else {
            [Environment]::SetEnvironmentVariable('CRM_IMAGE', $previousCrmImage, 'Process')
        }
    }

    $gateSucceeded = $true
}
finally {
    $cleanupExitCode = 0
    if ($backendStackTouched -and $gateSucceeded) {
        & docker compose --project-name $ProjectName --env-file $EnvFile -f $ComposeFile down --volumes --remove-orphans
        if ($LASTEXITCODE -ne 0) {
            $cleanupExitCode = $LASTEXITCODE
        }
    }
    elseif ($backendStackTouched) {
        Write-Warning "Release gate failed; preserving the isolated test stack for diagnosis. Inspect it with: docker compose --project-name $ProjectName --env-file `"$EnvFile`" -f `"$ComposeFile`" logs"
    }
    if ($locationPushed) {
        Pop-Location
    }
    foreach ($variableName in $composeEnvironmentNames) {
        $savedValue = $savedComposeEnvironment[$variableName]
        if ($null -eq $savedValue) {
            Remove-Item -LiteralPath "Env:$variableName" -ErrorAction SilentlyContinue
        }
        else {
            [Environment]::SetEnvironmentVariable($variableName, $savedValue, 'Process')
        }
    }
    if ($cleanupExitCode -ne 0) {
        throw "Release gate passed, but isolated test stack cleanup failed with exit code $cleanupExitCode."
    }
}

Write-Output "Release gate passed: contracts, typecheck, frontend tests, reproducible production package ($productionArchiveHash), isolated production image, and clean-stack backend tests."
