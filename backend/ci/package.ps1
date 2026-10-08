#Requires -Version 7.0
$ErrorActionPreference = 'Stop'
function Checked([string]$Script, [string[]]$Arguments = @()) {
    & (Join-Path $PSHOME 'pwsh') -NoProfile -File $Script @Arguments
    if ($LASTEXITCODE -ne 0) { throw "$Script failed with exit code $LASTEXITCODE." }
}
Checked backend/tests/compose-contract.ps1
Checked backend/tests/https-proxy-contract.ps1
Checked backend/tests/frappe-frontend-contract.ps1
Checked backend/tests/app-package-contract.ps1
Checked backend/tests/backend-test-report-contract.ps1
Checked backend/tests/http-request-contract.ps1
Checked backend/scripts/prepare-app-build-context.ps1 @('-OutputArchive', 'backend/build/rayher_crm.zip')
Checked backend/tests/app-archive-contract.ps1 @('-ArchivePath', 'backend/build/rayher_crm.zip')
Checked backend/scripts/prepare-app-build-context.ps1 @('-OutputArchive', 'backend/build/rayher_crm-tests.zip', '-IncludeTests')
Checked backend/tests/app-archive-contract.ps1 @('-ArchivePath', 'backend/build/rayher_crm-tests.zip', '-IncludeTests')
$commit = (& git rev-parse HEAD).Trim()
if ($LASTEXITCODE -ne 0) { throw 'Could not resolve source commit.' }
@{
    commit = $commit
    archives = @('rayher_crm.zip', 'rayher_crm-tests.zip') | ForEach-Object {
        @{name=$_; sha256=(Get-FileHash -Algorithm SHA256 -LiteralPath "backend/build/$_").Hash.ToLowerInvariant()}
    }
} | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath backend/build/manifest.json -Encoding utf8
