#Requires -Version 7.0

[CmdletBinding()]
param(
    [string]$BackendRoot = (Split-Path -Parent $PSScriptRoot)
)

$ErrorActionPreference = 'Stop'
$BackendRoot = (Resolve-Path -LiteralPath $BackendRoot).Path
$repositoryRoot = Split-Path -Parent $BackendRoot

function Assert-PackageContract {
    param(
        [bool]$Condition,
        [string]$Message
    )

    if (-not $Condition) {
        throw "App package contract failed: $Message"
    }
}

function Join-BackendPath {
    param([string]$RelativePath)

    return Join-Path $BackendRoot ($RelativePath -replace '[\\/]', [IO.Path]::DirectorySeparatorChar)
}

$composeFile = Join-Path $BackendRoot 'compose.yaml'
$envFile = Join-Path $BackendRoot '.env.example'
$backendReadmeFile = Join-Path $BackendRoot 'README.md'
$appRoot = Join-BackendPath 'apps/rayher_crm'
$prepareScript = Join-BackendPath 'scripts/prepare-app-build-context.ps1'
$archiveContractScript = Join-BackendPath 'tests/app-archive-contract.ps1'
$dockerIgnoreFile = Join-Path $BackendRoot '.dockerignore'
$restoreDrillScript = Join-BackendPath 'scripts/backup-restore-drill.sh'
$frontendContractScript = Join-BackendPath 'tests/frappe-frontend-contract.ps1'
$stagingDocuments = @(
    (Join-Path $repositoryRoot 'docs/CRM-Ubuntu-Staging部署与回滚清单-2026-08-04.md'),
    (Join-Path $repositoryRoot 'docs/CRM-Stage6-本地完成与Staging交接-2026-08-04.md')
)
$stage5cHandoffFile = Join-Path $repositoryRoot 'docs/CRM-Stage5C-安全断点交接-2026-08-04.md'

$requiredAppFiles = @(
    'pyproject.toml',
    'MANIFEST.in',
    'README.rst',
    'rayher_crm\__init__.py',
    'rayher_crm\hooks.py',
    'rayher_crm\www\__init__.py',
    'rayher_crm\www\crm.py',
    'rayher_crm\www\crm.html',
    'rayher_crm\public\crm\index.html',
    'rayher_crm\modules.txt',
    'rayher_crm\patches.txt',
    'rayher_crm\rayher_crm\__init__.py',
    'rayher_crm\rayher_crm\doctype\__init__.py',
    'rayher_crm\rayher_crm\doctype\crm_account_engineer_assignment\__init__.py',
    'rayher_crm\rayher_crm\doctype\crm_account_engineer_assignment\crm_account_engineer_assignment.json',
    'rayher_crm\rayher_crm\doctype\crm_account_engineer_assignment\crm_account_engineer_assignment.py',
    'rayher_crm\rayher_crm\doctype\crm_opportunity\__init__.py',
    'rayher_crm\rayher_crm\doctype\crm_opportunity\crm_opportunity.json',
    'rayher_crm\rayher_crm\doctype\crm_opportunity\crm_opportunity.py',
    'rayher_crm\rayher_crm\doctype\crm_opportunity_stakeholder\__init__.py',
    'rayher_crm\rayher_crm\doctype\crm_opportunity_stakeholder\crm_opportunity_stakeholder.json',
    'rayher_crm\rayher_crm\doctype\crm_opportunity_stakeholder\crm_opportunity_stakeholder.py',
    'rayher_crm\rayher_crm\doctype\crm_opportunity_action\__init__.py',
    'rayher_crm\rayher_crm\doctype\crm_opportunity_action\crm_opportunity_action.json',
    'rayher_crm\rayher_crm\doctype\crm_opportunity_action\crm_opportunity_action.py',
    'rayher_crm\rayher_crm\doctype\crm_opportunity_history\__init__.py',
    'rayher_crm\rayher_crm\doctype\crm_opportunity_history\crm_opportunity_history.json',
    'rayher_crm\rayher_crm\doctype\crm_opportunity_history\crm_opportunity_history.py',
    'rayher_crm\rayher_crm\doctype\crm_rfq\__init__.py',
    'rayher_crm\rayher_crm\doctype\crm_rfq\crm_rfq.json',
    'rayher_crm\rayher_crm\doctype\crm_rfq\crm_rfq.py',
    'rayher_crm\rayher_crm\doctype\crm_rfq_version\__init__.py',
    'rayher_crm\rayher_crm\doctype\crm_rfq_version\crm_rfq_version.json',
    'rayher_crm\rayher_crm\doctype\crm_rfq_version\crm_rfq_version.py',
    'rayher_crm\rayher_crm\doctype\crm_booking\__init__.py',
    'rayher_crm\rayher_crm\doctype\crm_booking\crm_booking.json',
    'rayher_crm\rayher_crm\doctype\crm_booking\crm_booking.py',
    'rayher_crm\rayher_crm\doctype\crm_installed_tool\__init__.py',
    'rayher_crm\rayher_crm\doctype\crm_installed_tool\crm_installed_tool.json',
    'rayher_crm\rayher_crm\doctype\crm_installed_tool\crm_installed_tool.py',
    'rayher_crm\rayher_crm\doctype\crm_demo_request\__init__.py',
    'rayher_crm\rayher_crm\doctype\crm_demo_request\crm_demo_request.json',
    'rayher_crm\rayher_crm\doctype\crm_demo_request\crm_demo_request.py',
    'rayher_crm\rayher_crm\doctype\crm_demo_request_history\__init__.py',
    'rayher_crm\rayher_crm\doctype\crm_demo_request_history\crm_demo_request_history.json',
    'rayher_crm\rayher_crm\doctype\crm_demo_request_history\crm_demo_request_history.py',
    'rayher_crm\rayher_crm\doctype\crm_demo_comment\__init__.py',
    'rayher_crm\rayher_crm\doctype\crm_demo_comment\crm_demo_comment.json',
    'rayher_crm\rayher_crm\doctype\crm_demo_comment\crm_demo_comment.py',
    'rayher_crm\rayher_crm\doctype\crm_evaluation\__init__.py',
    'rayher_crm\rayher_crm\doctype\crm_evaluation\crm_evaluation.json',
    'rayher_crm\rayher_crm\doctype\crm_evaluation\crm_evaluation.py',
    'rayher_crm\rayher_crm\doctype\crm_test_run\__init__.py',
    'rayher_crm\rayher_crm\doctype\crm_test_run\crm_test_run.json',
    'rayher_crm\rayher_crm\doctype\crm_test_run\crm_test_run.py',
    'rayher_crm\rayher_crm\doctype\crm_contact_file\__init__.py',
    'rayher_crm\rayher_crm\doctype\crm_contact_file\crm_contact_file.json',
    'rayher_crm\rayher_crm\doctype\crm_contact_file\crm_contact_file.py',
    'rayher_crm\rayher_crm\doctype\crm_demo_artifact\__init__.py',
    'rayher_crm\rayher_crm\doctype\crm_demo_artifact\crm_demo_artifact.json',
    'rayher_crm\rayher_crm\doctype\crm_demo_artifact\crm_demo_artifact.py',
    'rayher_crm\rayher_crm\doctype\crm_file_access_audit\__init__.py',
    'rayher_crm\rayher_crm\doctype\crm_file_access_audit\crm_file_access_audit.json',
    'rayher_crm\rayher_crm\doctype\crm_file_access_audit\crm_file_access_audit.py',
    'rayher_crm\rayher_crm\doctype\crm_notification_event\__init__.py',
    'rayher_crm\rayher_crm\doctype\crm_notification_event\crm_notification_event.json',
    'rayher_crm\rayher_crm\doctype\crm_notification_event\crm_notification_event.py',
    'rayher_crm\api\__init__.py',
    'rayher_crm\api\v1\__init__.py',
    'rayher_crm\api\v1\errors.py',
    'rayher_crm\api\v1\accounts.py',
    'rayher_crm\api\v1\contacts.py',
    'rayher_crm\api\v1\leads.py',
    'rayher_crm\api\v1\opportunities.py',
    'rayher_crm\api\v1\rfqs.py',
    'rayher_crm\api\v1\bookings.py',
    'rayher_crm\api\v1\installed_tools.py',
    'rayher_crm\api\v1\demo_requests.py',
    'rayher_crm\api\v1\evaluations.py',
    'rayher_crm\api\v1\contact_files.py',
    'rayher_crm\api\v1\demo_artifacts.py',
    'rayher_crm\api\v1\notifications.py',
    'rayher_crm\permissions\__init__.py',
    'rayher_crm\permissions\scope.py',
    'rayher_crm\services\__init__.py',
    'rayher_crm\services\common.py',
    'rayher_crm\services\concurrency.py',
    'rayher_crm\services\accounts.py',
    'rayher_crm\services\contacts.py',
    'rayher_crm\services\leads.py',
    'rayher_crm\services\opportunities.py',
    'rayher_crm\services\rfqs.py',
    'rayher_crm\services\bookings.py',
    'rayher_crm\services\installed_tools.py',
    'rayher_crm\services\demo_requests.py',
    'rayher_crm\services\evaluations.py',
    'rayher_crm\services\file_security.py',
    'rayher_crm\services\contact_files.py',
    'rayher_crm\services\demo_artifacts.py',
    'rayher_crm\services\demo_reports.py',
    'rayher_crm\services\notifications.py',
    'rayher_crm\services\sites.py',
    'rayher_crm\setup\__init__.py',
    'rayher_crm\setup\custom_fields.py',
    'rayher_crm\setup\indexes.py',
    'rayher_crm\tests\__init__.py',
    'rayher_crm\tests\test_demo_request_api.py',
    'rayher_crm\tests\test_evaluation_api.py',
    'rayher_crm\tests\test_stage5f_schema.py',
    'rayher_crm\tests\test_contact_file_api.py',
    'rayher_crm\tests\test_demo_artifact_api.py',
    'rayher_crm\tests\stage5f_probes.py',
    'rayher_crm\tests\test_demo_report_api.py',
    'rayher_crm\tests\test_notification_api.py',
    'rayher_crm\tests\test_stage6_web_entry.py'
)

foreach ($relativePath in $requiredAppFiles) {
    $portableRelativePath = $relativePath -replace '[\\/]', [IO.Path]::DirectorySeparatorChar
    Assert-PackageContract (Test-Path -LiteralPath (Join-Path $appRoot $portableRelativePath) -PathType Leaf) "missing app file: $relativePath"
}

$composeText = ('' + (Get-Content -LiteralPath $composeFile -Raw -Encoding UTF8)).Replace("`r`n", "`n")
$envText = ('' + (Get-Content -LiteralPath $envFile -Raw -Encoding UTF8)).Replace("`r`n", "`n")
$backendReadmeText = ('' + (Get-Content -LiteralPath $backendReadmeFile -Raw -Encoding UTF8)).Replace("`r`n", "`n")
$pyprojectText = ('' + (Get-Content -LiteralPath (Join-Path $appRoot 'pyproject.toml') -Raw -Encoding UTF8)).Replace("`r`n", "`n")

Assert-PackageContract ($composeText -match '(?m)^\s+dockerfile_inline:\s*\|\s*$') 'Compose must contain an auditable inline Dockerfile'
Assert-PackageContract ($composeText -match 'ARG FRAPPE_BASE_IMAGE') 'inline Dockerfile must accept the pinned base image'
Assert-PackageContract ($composeText -match 'FROM \$\$\{FRAPPE_BASE_IMAGE\}') 'inline Dockerfile must build from FRAPPE_BASE_IMAGE'
Assert-PackageContract ($composeText -match '(?ms)FROM \$\$\{FRAPPE_BASE_IMAGE\}.*?^\s+ARG CRM_APP_ARCHIVE=build/rayher_crm\.zip$') 'the build stage must declare and default CRM_APP_ARCHIVE'
Assert-PackageContract ($composeText -match 'COPY --chown=frappe:frappe \$\$\{CRM_APP_ARCHIVE\}') 'the selected verified archive must be copied into the image'
Assert-PackageContract ($composeText -match '(?m)^\s+CRM_APP_ARCHIVE: build/rayher_crm\.zip$') 'Compose must hard-code the production archive build argument'
Assert-PackageContract ($composeText -match 'sha256sum -c -') 'the image build must verify the selected archive hash before extraction'
Assert-PackageContract ($composeText -notmatch 'COPY --chown=frappe:frappe apps/rayher_crm') 'raw protected app source must not be copied by BuildKit'
Assert-PackageContract ($composeText -match 'USER frappe') 'final app installation must run as the frappe user'
Assert-PackageContract ($composeText -match 'libreoffice-writer' -and $composeText -match 'libreoffice-calc' -and $composeText -match 'libreoffice-impress') 'RFQ Office preview dependencies must be installed'
Assert-PackageContract ($composeText -match 'pip install') 'the Python app must be installed into the bench environment'
Assert-PackageContract (Test-Path -LiteralPath $prepareScript -PathType Leaf) 'byte-rehydrating build-context script must exist'
Assert-PackageContract (Test-Path -LiteralPath $archiveContractScript -PathType Leaf) 'Git HEAD archive contract must exist'
Assert-PackageContract (Test-Path -LiteralPath $dockerIgnoreFile -PathType Leaf) 'backend/.dockerignore must restrict the build context'
Assert-PackageContract (Test-Path -LiteralPath $restoreDrillScript -PathType Leaf) 'backup restore drill script must exist'
Assert-PackageContract (Test-Path -LiteralPath $frontendContractScript -PathType Leaf) 'Frappe frontend contract script must exist'
Assert-PackageContract (Test-Path -LiteralPath (Join-BackendPath 'tests/http-stage5e-demo-evaluation-acceptance.ps1') -PathType Leaf) 'Stage 5E HTTP acceptance script must exist'
Assert-PackageContract (Test-Path -LiteralPath (Join-BackendPath 'tests/http-stage5f-files-reports-notifications-acceptance.ps1') -PathType Leaf) 'Stage 5F HTTP acceptance script must exist'
$prepareText = Get-Content -LiteralPath $prepareScript -Raw -Encoding UTF8
Assert-PackageContract ($prepareText -match 'ZipArchive') 'build-context script must use .NET ZipArchive'
Assert-PackageContract ($prepareText -match '%TSD-Header-###%') 'build-context script must reject protected wrappers'
Assert-PackageContract ($prepareText -match 'git -C \$repositoryRoot -c core\.quotePath=false ls-files -z -- \$sourceRepositoryPath') 'build-context script must enumerate Git-tracked source with a null-delimited command'
Assert-PackageContract ($prepareText -match 'Assert-SafeSourceFile') 'build-context script must scan tracked files even when tests are excluded from production'
Assert-PackageContract ($prepareText -match 'VerifyRebuild') 'build-context script must independently rebuild and compare generated frontend assets'
Assert-PackageContract ($prepareText -match 'LastWriteTime = \[DateTimeOffset\]::new\(1980, 1, 1') 'build-context script must freeze ZIP timestamps for reproducibility'
$dockerIgnoreText = ('' + (Get-Content -LiteralPath $dockerIgnoreFile -Raw -Encoding UTF8)).Replace("`r`n", "`n")
$expectedDockerIgnore = "**`n!build/`nbuild/**`n!build/rayher_crm.zip`n!build/rayher_crm-tests.zip"
Assert-PackageContract ($dockerIgnoreText.Trim() -eq $expectedDockerIgnore) 'Docker build context must allow only the verified production and test archives'
foreach ($stagingDocument in $stagingDocuments) {
    Assert-PackageContract (Test-Path -LiteralPath $stagingDocument -PathType Leaf) "staging deployment document must exist: $stagingDocument"
    $stagingText = ('' + (Get-Content -LiteralPath $stagingDocument -Raw -Encoding UTF8)).Replace("`r`n", "`n")
    Assert-PackageContract ($stagingText -match 'set -euo pipefail') "staging deployment must stop before startup when archive verification or image build fails: $stagingDocument"
    Assert-PackageContract ($stagingText -match 'archive_hash="\$\(sha256sum backend/build/rayher_crm\.zip') "staging deployment must calculate the app archive hash: $stagingDocument"
    Assert-PackageContract ($stagingText -match 'build --build-arg "CRM_APP_ARCHIVE_SHA256=\$archive_hash" backend') "staging deployment must bind the calculated archive hash to the image build: $stagingDocument"
    Assert-PackageContract ($stagingText -notmatch '(?m)^docker compose .* build backend\s*$') "staging deployment must not document an unverified app image build: $stagingDocument"
    Assert-PackageContract ($stagingText -match 'up -d --no-build') "staging deployment must start the image that passed the verified build: $stagingDocument"
}
Assert-PackageContract ($backendReadmeText -match '(?s)build --build-arg "CRM_APP_ARCHIVE_SHA256=\$archiveHash" backend\nif \(\$LASTEXITCODE -ne 0\) \{ throw .*? \}\ndocker compose .*? up -d --no-build') 'local lifecycle must stop before startup when the verified image build fails'
foreach ($command in @(
    'docker compose --env-file backend/.env.example -f backend/compose.yaml config',
    'pwsh -NoProfile -File backend/tests/compose-contract.ps1',
    'pnpm build:frappe',
    'pwsh -NoProfile -File backend/scripts/prepare-app-build-context.ps1'
)) {
    $checkedCommand = [regex]::Escape($command) + '\nif \(\$LASTEXITCODE -ne 0\) \{ throw '
    Assert-PackageContract ($backendReadmeText -match $checkedCommand) "local lifecycle must stop when this prerequisite fails: $command"
}
Assert-PackageContract (Test-Path -LiteralPath $stage5cHandoffFile -PathType Leaf) 'Stage 5C handoff document must exist'
$stage5cHandoffText = ('' + (Get-Content -LiteralPath $stage5cHandoffFile -Raw -Encoding UTF8)).Replace("`r`n", "`n")
Assert-PackageContract ($stage5cHandoffText -notmatch '(?m)^powershell\.exe .*prepare-app-build-context') 'Stage 5C handoff must use the required PowerShell 7 archive builder'
Assert-PackageContract ([regex]::Matches($stage5cHandoffText, 'build --build-arg "CRM_APP_ARCHIVE_SHA256=\$archiveHash" backend').Count -eq 2) 'every Stage 5C image build must bind the current archive hash'
Assert-PackageContract ([regex]::Matches($stage5cHandoffText, 'build --build-arg .* backend\nif \(\$LASTEXITCODE -ne 0\) \{ throw ').Count -eq 2) 'every Stage 5C image build must stop the workflow on failure'
$topLevelDeploymentDocuments = Get-ChildItem -LiteralPath (Join-Path $repositoryRoot 'docs') -File -Filter '*.md'
foreach ($deploymentDocument in $topLevelDeploymentDocuments) {
    $deploymentText = ('' + (Get-Content -LiteralPath $deploymentDocument.FullName -Raw -Encoding UTF8)).Replace("`r`n", "`n")
    Assert-PackageContract ($deploymentText -notmatch '(?m)^docker compose .* build backend\s*$') "top-level deployment documentation must not contain an unverified backend build: $($deploymentDocument.FullName)"
    Assert-PackageContract ($deploymentText -notmatch '(?m)^docker compose .* up -d --build(?:\s|$)') "top-level deployment documentation must not combine an unverified build with startup: $($deploymentDocument.FullName)"
}
$restoreDrillText = Get-Content -LiteralPath $restoreDrillScript -Raw -Encoding UTF8
Assert-PackageContract ($restoreDrillText -match 'bench --site "\$\{source_site\}" backup --with-files --compress') 'restore drill must create a database and file backup'
Assert-PackageContract ($restoreDrillText -match 'bench --site "\$\{restore_site\}" restore') 'restore drill must restore into an isolated site'
Assert-PackageContract ($restoreDrillText -match 'bench drop-site "\$\{restore_site\}"') 'restore drill must clean its exact temporary site'
Assert-PackageContract ($restoreDrillText -match 'if ! bench drop-site') 'restore drill must tolerate the known search-index cleanup race'

Assert-PackageContract ($envText -match '(?m)^FRAPPE_BASE_IMAGE=frappe/erpnext:v15@sha256:[0-9a-f]{64}$') 'FRAPPE_BASE_IMAGE must be v15 and digest-pinned'
Assert-PackageContract ($envText -match '(?m)^CLAMAV_IMAGE=clamav/clamav:1\.4\.5@sha256:[0-9a-f]{64}$') 'CLAMAV_IMAGE must use the pinned official 1.4.5 amd64 digest'
Assert-PackageContract ($envText -match '(?m)^CRM_IMAGE=rayher-crm-stage1:v15-local$') 'CRM_IMAGE must use the new local image name'
Assert-PackageContract ($envText -notmatch '(?m)^CRM_APP_ARCHIVE=') 'the production archive path must not be environment-overridable'
Assert-PackageContract ($envText -match '(?m)^ALLOW_TESTS=false$') 'the documented LAN environment must disable Frappe tests'
Assert-PackageContract ($composeText -match 'allow_tests_value=True') 'Compose must translate local true to a parsed Python boolean'
Assert-PackageContract ($composeText -match 'allow_tests_value=False') 'Compose must translate deployment false to a parsed Python boolean'
Assert-PackageContract ($envText -notmatch 'rayher-crm:v16\.28\.0-local') 'the old CRM image is forbidden'

foreach ($service in @('install-app', 'migrate')) {
    Assert-PackageContract ($composeText -match "(?m)^  ${service}:\s*$") "Compose service '$service' is required"
}
Assert-PackageContract ($composeText -match '(?m)^\s+build:\s*$') 'Compose must build the custom image'
Assert-PackageContract ($composeText -notmatch '(?m)^\s+-\s+\./apps/rayher_crm:') 'source bind mounts are forbidden as the deployment result'
Assert-PackageContract ($composeText -match '(?m)^  clamav:\s*$') 'internal ClamAV service is required for fail-closed uploads'
Assert-PackageContract ($composeText -match 'CRM_CLAMD_HOST: clamav') 'backend must scan through the internal ClamAV service'
Assert-PackageContract ($composeText -notmatch '(?ms)^  clamav:[ \t]*\r?\n(?:(?!^  \S).)*^\s+ports:') 'ClamAV must not publish a host port'
Assert-PackageContract ($composeText -match 'bench build --app rayher_crm') 'frontend must link packaged CRM assets before nginx starts'
Assert-PackageContract ($composeText -match 'REALTIME_AUTH_ORIGIN: http://frontend:8080') 'WebSocket auth callbacks must use the Docker-resolvable frontend origin'
Assert-PackageContract ($composeText -match 'REALTIME_AUTH_HOST: frontend:8080') 'WebSocket Host must match the internal auth origin'
Assert-PackageContract ($composeText -match '/tmp/frappe\.conf\.template') 'frontend must patch a writable copy of the read-only nginx template'
Assert-PackageContract ($composeText -match 'exec nginx -g') 'frontend must run nginx in the foreground'

Assert-PackageContract ($pyprojectText -match '(?m)^name = "rayher_crm"$') 'pyproject package name must be rayher_crm'
Assert-PackageContract ($pyprojectText -match '(?m)^requires-python = ">=3\.10"$') 'app must retain Python >=3.10 compatibility'
Assert-PackageContract ($pyprojectText -match 'frappe.*>=15.*<16') 'Frappe v15 compatibility must be declared'

Write-Output 'App package contract passed.'
