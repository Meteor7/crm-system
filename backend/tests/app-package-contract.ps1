param(
    [string]$BackendRoot = (Split-Path -Parent $PSScriptRoot)
)

$ErrorActionPreference = 'Stop'

function Assert-PackageContract {
    param(
        [bool]$Condition,
        [string]$Message
    )

    if (-not $Condition) {
        throw "App package contract failed: $Message"
    }
}

$composeFile = Join-Path $BackendRoot 'compose.yaml'
$envFile = Join-Path $BackendRoot '.env.example'
$appRoot = Join-Path $BackendRoot 'apps\rayher_crm'
$prepareScript = Join-Path $BackendRoot 'scripts\prepare-app-build-context.ps1'
$restoreDrillScript = Join-Path $BackendRoot 'scripts\backup-restore-drill.sh'
$frontendContractScript = Join-Path $BackendRoot 'tests\frappe-frontend-contract.ps1'

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
    Assert-PackageContract (Test-Path -LiteralPath (Join-Path $appRoot $relativePath) -PathType Leaf) "missing app file: $relativePath"
}

$textExtensions = @('.py', '.toml', '.in', '.rst', '.txt', '.json', '.csv', '.md', '.html', '.css', '.js', '.svg')
Get-ChildItem -LiteralPath $appRoot -Recurse -File | ForEach-Object {
    $bytes = [IO.File]::ReadAllBytes($_.FullName)
    $prefixLength = [Math]::Min(18, $bytes.Length)
    $prefix = if ($prefixLength -gt 0) { [Text.Encoding]::ASCII.GetString($bytes, 0, $prefixLength) } else { '' }
    Assert-PackageContract (-not $prefix.StartsWith('%TSD-Header-###%')) "protected wrapper detected: $($_.FullName)"
    if ($textExtensions -contains $_.Extension.ToLowerInvariant()) {
        Assert-PackageContract (-not ($bytes -contains 0)) "null byte detected in text app source: $($_.FullName)"
    }
}

$composeText = Get-Content -LiteralPath $composeFile -Raw -Encoding UTF8
$envText = Get-Content -LiteralPath $envFile -Raw -Encoding UTF8
$pyprojectText = Get-Content -LiteralPath (Join-Path $appRoot 'pyproject.toml') -Raw -Encoding UTF8

Assert-PackageContract ($composeText -match '(?m)^\s+dockerfile_inline:\s*\|\s*$') 'Compose must contain an auditable inline Dockerfile'
Assert-PackageContract ($composeText -match 'ARG FRAPPE_BASE_IMAGE') 'inline Dockerfile must accept the pinned base image'
Assert-PackageContract ($composeText -match 'FROM \$\$\{FRAPPE_BASE_IMAGE\}') 'inline Dockerfile must build from FRAPPE_BASE_IMAGE'
Assert-PackageContract ($composeText -match 'COPY --chown=frappe:frappe build/rayher_crm\.zip') 'the verified rehydrated archive must be copied into the image'
Assert-PackageContract ($composeText -notmatch 'COPY --chown=frappe:frappe apps/rayher_crm') 'raw protected app source must not be copied by BuildKit'
Assert-PackageContract ($composeText -match 'USER frappe') 'final app installation must run as the frappe user'
Assert-PackageContract ($composeText -match 'libreoffice-writer' -and $composeText -match 'libreoffice-calc' -and $composeText -match 'libreoffice-impress') 'RFQ Office preview dependencies must be installed'
Assert-PackageContract ($composeText -match 'pip install') 'the Python app must be installed into the bench environment'
Assert-PackageContract (Test-Path -LiteralPath $prepareScript -PathType Leaf) 'byte-rehydrating build-context script must exist'
Assert-PackageContract (Test-Path -LiteralPath $restoreDrillScript -PathType Leaf) 'backup restore drill script must exist'
Assert-PackageContract (Test-Path -LiteralPath $frontendContractScript -PathType Leaf) 'Frappe frontend contract script must exist'
Assert-PackageContract (Test-Path -LiteralPath (Join-Path $BackendRoot 'tests\http-stage5e-demo-evaluation-acceptance.ps1') -PathType Leaf) 'Stage 5E HTTP acceptance script must exist'
Assert-PackageContract (Test-Path -LiteralPath (Join-Path $BackendRoot 'tests\http-stage5f-files-reports-notifications-acceptance.ps1') -PathType Leaf) 'Stage 5F HTTP acceptance script must exist'
$prepareText = Get-Content -LiteralPath $prepareScript -Raw -Encoding UTF8
Assert-PackageContract ($prepareText -match 'ZipArchive') 'build-context script must use .NET ZipArchive'
Assert-PackageContract ($prepareText -match '%TSD-Header-###%') 'build-context script must reject protected wrappers'
$restoreDrillText = Get-Content -LiteralPath $restoreDrillScript -Raw -Encoding UTF8
Assert-PackageContract ($restoreDrillText -match 'bench --site "\$\{source_site\}" backup --with-files --compress') 'restore drill must create a database and file backup'
Assert-PackageContract ($restoreDrillText -match 'bench --site "\$\{restore_site\}" restore') 'restore drill must restore into an isolated site'
Assert-PackageContract ($restoreDrillText -match 'bench drop-site "\$\{restore_site\}"') 'restore drill must clean its exact temporary site'
Assert-PackageContract ($restoreDrillText -match 'if ! bench drop-site') 'restore drill must tolerate the known search-index cleanup race'

Assert-PackageContract ($envText -match '(?m)^FRAPPE_BASE_IMAGE=frappe/erpnext:v15@sha256:[0-9a-f]{64}$') 'FRAPPE_BASE_IMAGE must be v15 and digest-pinned'
Assert-PackageContract ($envText -match '(?m)^CLAMAV_IMAGE=clamav/clamav:1\.4\.5@sha256:[0-9a-f]{64}$') 'CLAMAV_IMAGE must use the pinned official 1.4.5 amd64 digest'
Assert-PackageContract ($envText -match '(?m)^CRM_IMAGE=rayher-crm-stage1:v15-local$') 'CRM_IMAGE must use the new local image name'
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
