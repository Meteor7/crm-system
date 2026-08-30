param(
    [string]$ComposeFile = (Join-Path $PSScriptRoot '..\compose.yaml'),
    [string]$EnvFile = (Join-Path $PSScriptRoot '..\.env.example'),
    [string]$LanEnvFile = (Join-Path $PSScriptRoot '..\.env.lan'),
    [string]$TestEnvFile = (Join-Path $PSScriptRoot '..\test.env.example')
)

$ErrorActionPreference = 'Stop'

function Assert-Contract {
    param(
        [bool]$Condition,
        [string]$Message
    )

    if (-not $Condition) {
        throw "Compose contract failed: $Message"
    }
}

Assert-Contract (Test-Path -LiteralPath $ComposeFile -PathType Leaf) 'backend/compose.yaml must exist'
Assert-Contract (Test-Path -LiteralPath $EnvFile -PathType Leaf) 'backend/.env.example must exist'
Assert-Contract (Test-Path -LiteralPath $LanEnvFile -PathType Leaf) 'backend/.env.lan must exist for explicit company LAN access'
Assert-Contract (Test-Path -LiteralPath $TestEnvFile -PathType Leaf) 'backend/test.env.example must exist for isolated backend tests'

$composeText = Get-Content -LiteralPath $ComposeFile -Raw -Encoding UTF8
$envText = Get-Content -LiteralPath $EnvFile -Raw -Encoding UTF8

Assert-Contract ($composeText -match 'rayher-crm-stage1-local') 'the new default project name must be frozen'
Assert-Contract ($composeText -notmatch 'rayher-crm:v16\.28\.0-local') 'the old local CRM image is forbidden'
Assert-Contract ($composeText -notmatch 'rayher-crm_(db-data|sites|logs|redis|local-secrets)') 'old rayher-crm volumes are forbidden'
Assert-Contract ($composeText -notmatch '(?m)^\s*external:\s*true\s*$') 'external volumes are forbidden for the isolated local stack'
Assert-Contract ($composeText -match "Host: \$\$\{SITE_NAME\}") 'backend healthcheck must send the Frappe site Host header'
Assert-Contract ($composeText -notmatch "--header 'Host: \$\$\{SITE_NAME\}'") 'site Host variable must not be trapped in shell single quotes'

foreach ($service in @('secrets-init', 'db', 'redis-cache', 'redis-queue', 'configurator', 'create-site', 'backend', 'frontend', 'websocket', 'scheduler', 'queue-short', 'queue-long')) {
    Assert-Contract ($composeText -match "(?m)^  $([regex]::Escape($service)):\s*$") "required service '$service' is missing"
}

foreach ($imageVariable in @('FRAPPE_BASE_IMAGE', 'MARIADB_IMAGE', 'REDIS_IMAGE')) {
    $line = ($envText -split "`r?`n" | Where-Object { $_ -like "$imageVariable=*" } | Select-Object -First 1)
    Assert-Contract (-not [string]::IsNullOrWhiteSpace($line)) "$imageVariable must be present in .env.example"
    Assert-Contract ($line -match '@sha256:[0-9a-f]{64}$') "$imageVariable must be pinned by digest"
}
Assert-Contract ($envText -match '(?m)^CRM_IMAGE=rayher-crm-stage1:v15-local$') 'CRM_IMAGE must use the new custom app image'

Assert-Contract ($envText -notmatch '(?im)^(.*PASSWORD|.*SECRET|.*TOKEN)=.+$') '.env.example must not contain secret values'

$renderedJson = & docker compose --env-file $EnvFile -f $ComposeFile config --format json
if ($LASTEXITCODE -ne 0) {
    throw 'Compose contract failed: docker compose config did not render successfully'
}

$rendered = $renderedJson | ConvertFrom-Json
Assert-Contract ($rendered.name -eq 'rayher-crm-stage1-local') 'rendered project name is not isolated'
Assert-Contract ($null -eq $rendered.services.db.ports) 'MariaDB must not publish host ports'
Assert-Contract ($null -eq $rendered.services.'redis-cache'.ports) 'Redis cache must not publish host ports'
Assert-Contract ($null -eq $rendered.services.'redis-queue'.ports) 'Redis queue must not publish host ports'
Assert-Contract ($rendered.services.frontend.ports.Count -eq 1) 'only one frontend port mapping is expected'
Assert-Contract ($rendered.services.frontend.ports[0].host_ip -eq '0.0.0.0') 'the documented local environment must remain reachable on the company LAN'
Assert-Contract ($composeText -match 'bench build --app rayher_crm') 'frontend must link packaged assets before nginx starts'
Assert-Contract ($composeText -match 'REALTIME_AUTH_ORIGIN: http://frontend:8080') 'WebSocket auth callbacks must use the Docker-resolvable frontend origin'
Assert-Contract ($composeText -match 'REALTIME_AUTH_HOST: frontend:8080') 'WebSocket Host must match the internal auth origin'
Assert-Contract ($composeText -match '/tmp/frappe\.conf\.template') 'frontend must patch a writable copy of the read-only nginx template'
Assert-Contract ($composeText -match 'exec nginx -g') 'frontend must run nginx in the foreground'

$volumeNames = @($rendered.volumes.PSObject.Properties.Value.name)
Assert-Contract ($volumeNames.Count -ge 6) 'independent persistent volumes are incomplete'
foreach ($volumeName in $volumeNames) {
    Assert-Contract ($volumeName -like 'rayher-crm-stage1-local_*') "volume '$volumeName' is outside the new project namespace"
    Assert-Contract ($volumeName -notlike 'rayher-crm_*') "volume '$volumeName' collides with the old project"
}

$lanRenderedJson = & docker compose --env-file $LanEnvFile -f $ComposeFile config --format json
if ($LASTEXITCODE -ne 0) {
    throw 'Compose contract failed: LAN compose config did not render successfully'
}
$lanRendered = $lanRenderedJson | ConvertFrom-Json
Assert-Contract ($lanRendered.services.frontend.ports.Count -eq 1) 'LAN mode must publish only the frontend port'
Assert-Contract ($lanRendered.services.frontend.ports[0].host_ip -eq '0.0.0.0') 'LAN mode must listen on all local IPv4 interfaces'
Assert-Contract ($lanRendered.services.frontend.ports[0].published -eq '2224') 'LAN mode must publish TCP port 2224'
Assert-Contract ($lanRendered.services.migrate.environment.ALLOW_TESTS -eq 'false') 'LAN mode must disable Frappe tests'
Assert-Contract ($lanRendered.services.migrate.environment.CRM_TEST_SITE -eq 'false') 'LAN mode must never be marked as a CRM test site'

$testRenderedJson = & docker compose --env-file $TestEnvFile -f $ComposeFile config --format json
if ($LASTEXITCODE -ne 0) {
    throw 'Compose contract failed: test compose config did not render successfully'
}
$testRendered = $testRenderedJson | ConvertFrom-Json
Assert-Contract ($testRendered.name -eq 'rayher-crm-stage1-tests') 'backend tests must use a dedicated Compose project'
Assert-Contract ($testRendered.services.migrate.environment.SITE_NAME -eq 'rayher-crm.test') 'backend tests must use a dedicated Frappe site'
Assert-Contract ($testRendered.services.migrate.environment.ALLOW_TESTS -eq 'true') 'dedicated test site must enable Frappe tests'
Assert-Contract ($testRendered.services.migrate.environment.CRM_TEST_SITE -eq 'true') 'dedicated test site must carry the CRM test-site marker'
Assert-Contract ($testRendered.services.frontend.ports[0].host_ip -eq '127.0.0.1') 'test frontend must only bind to loopback'
$testVolumeNames = @($testRendered.volumes.PSObject.Properties.Value.name)
foreach ($volumeName in $testVolumeNames) {
    Assert-Contract ($volumeName -like 'rayher-crm-stage1-tests_*') "test volume '$volumeName' is outside the dedicated test project"
    Assert-Contract ($volumeName -notlike 'rayher-crm-stage1-local_*') "test volume '$volumeName' collides with operational data"
}

Write-Output 'Compose contract passed.'
