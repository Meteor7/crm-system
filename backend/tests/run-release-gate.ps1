param(
    [string]$ProjectName = 'rayher-crm-stage1-tests',
    [string]$SiteName = 'rayher-crm.test',
    [string]$EnvFile = 'backend/test.env.example',
    [string]$ComposeFile = 'backend/compose.yaml',
    [switch]$StartBackend
)

$ErrorActionPreference = 'Stop'
$repositoryRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..\..')).Path

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

Push-Location $repositoryRoot
try {
    $worktreeStatus = @(& git status --porcelain --untracked-files=normal)
    if ($LASTEXITCODE -ne 0) {
        throw 'Could not inspect the Git worktree.'
    }
    if ($worktreeStatus.Count -gt 0) {
        throw 'Release gate requires a clean Git worktree.'
    }

    $commandExtension = if ($env:OS -eq 'Windows_NT') { '.cmd' } else { '' }
    $binDirectory = Join-Path $repositoryRoot 'node_modules/.bin'
    Invoke-CheckedCommand 'TypeScript typecheck' (Join-Path $binDirectory "vue-tsc$commandExtension") @('--noEmit')
    Invoke-CheckedCommand 'Frontend tests' (Join-Path $binDirectory "vitest$commandExtension") @('run')
    Invoke-CheckedCommand 'Production build' (Join-Path $binDirectory "vite$commandExtension") @(
        'build', '--mode', 'frappe',
        '--outDir', 'backend/apps/rayher_crm/rayher_crm/public/crm', '--emptyOutDir'
    )

    if ($StartBackend) {
        & (Join-Path $repositoryRoot 'backend/scripts/prepare-app-build-context.ps1') -IncludeTests
        if ($LASTEXITCODE -ne 0) {
            throw "Backend build context failed with exit code $LASTEXITCODE."
        }
        Invoke-CheckedCommand 'Backend stack startup' 'docker' @(
            'compose', '--project-name', $ProjectName, '--env-file', $EnvFile,
            '-f', $ComposeFile, 'up', '-d', '--build', 'backend'
        )
    }

    & (Join-Path $repositoryRoot 'backend/tests/run-backend-tests.ps1') `
        -ProjectName $ProjectName -SiteName $SiteName -EnvFile $EnvFile -ComposeFile $ComposeFile
    if ($LASTEXITCODE -ne 0) {
        throw "Backend tests failed with exit code $LASTEXITCODE."
    }

    Write-Output 'Release gate passed: typecheck, frontend tests, production build, and backend tests.'
}
finally {
    Pop-Location
}
