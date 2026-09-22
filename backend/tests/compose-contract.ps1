#Requires -Version 7.0

[CmdletBinding()]
param(
    [string]$ComposeFile = (Join-Path (Split-Path -Parent $PSScriptRoot) 'compose.yaml'),
    [string]$EnvFile = (Join-Path (Split-Path -Parent $PSScriptRoot) '.env.example'),
    [string]$LanEnvFile = (Join-Path (Split-Path -Parent $PSScriptRoot) 'lan.env.example'),
    [string]$TestEnvFile = (Join-Path (Split-Path -Parent $PSScriptRoot) 'test.env.example')
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
Assert-Contract (Test-Path -LiteralPath $LanEnvFile -PathType Leaf) 'backend/lan.env.example must exist for opt-in company LAN access'
Assert-Contract (Test-Path -LiteralPath $TestEnvFile -PathType Leaf) 'backend/test.env.example must exist for isolated backend tests'

$composeText = ('' + (Get-Content -LiteralPath $ComposeFile -Raw -Encoding UTF8)).Replace("`r`n", "`n")
$envText = ('' + (Get-Content -LiteralPath $EnvFile -Raw -Encoding UTF8)).Replace("`r`n", "`n")
$lanEnvText = ('' + (Get-Content -LiteralPath $LanEnvFile -Raw -Encoding UTF8)).Replace("`r`n", "`n")
$testEnvText = ('' + (Get-Content -LiteralPath $TestEnvFile -Raw -Encoding UTF8)).Replace("`r`n", "`n")

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
Assert-Contract ($envText -notmatch '(?m)^CRM_APP_ARCHIVE=') 'the LAN archive path must not be environment-overridable'
Assert-Contract ($testEnvText -notmatch '(?m)^CRM_APP_ARCHIVE=') 'the test archive path must only be selected by the release gate build command'
Assert-Contract ($composeText -match '(?m)^\s+CRM_APP_ARCHIVE: build/rayher_crm\.zip$') 'Compose must hard-code the production archive'

Assert-Contract ($envText -notmatch '(?im)^(.*PASSWORD|.*SECRET|.*TOKEN)=.+$') '.env.example must not contain secret values'
Assert-Contract ($lanEnvText -notmatch '(?im)^(.*PASSWORD|.*SECRET|.*TOKEN)=.+$') 'lan.env.example must not contain secret values'
Assert-Contract ($envText -match '(?m)^HTTP_BIND_ADDRESS=127\.0\.0\.1$') 'the default template must bind loopback only'
Assert-Contract ($lanEnvText -match '(?m)^HTTP_BIND_ADDRESS=0\.0\.0\.0$') 'the opt-in LAN template must bind every local IPv4 interface'
$normalisedLocalEnv = ($envText -replace '(?m)^HTTP_BIND_ADDRESS=.*$', 'HTTP_BIND_ADDRESS=')
$normalisedLanEnv = ($lanEnvText -replace '(?m)^HTTP_BIND_ADDRESS=.*$', 'HTTP_BIND_ADDRESS=')
Assert-Contract ($normalisedLocalEnv -eq $normalisedLanEnv) 'lan.env.example must differ from .env.example only in HTTP_BIND_ADDRESS'

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
try {
    $env:CRM_APP_ARCHIVE = 'build/rayher_crm-tests.zip'
    $localRenderedJson = & docker compose --env-file $EnvFile -f $ComposeFile config --format json
    if ($LASTEXITCODE -ne 0) {
        throw 'Compose contract failed: documented local compose config did not render successfully'
    }
    $lanRenderedJson = & docker compose --env-file $LanEnvFile -f $ComposeFile config --format json
    if ($LASTEXITCODE -ne 0) {
        throw 'Compose contract failed: opt-in LAN compose config did not render successfully'
    }
    Remove-Item -LiteralPath 'Env:CRM_APP_ARCHIVE' -ErrorAction SilentlyContinue
    $testRenderedJson = & docker compose --env-file $TestEnvFile -f $ComposeFile config --format json
    if ($LASTEXITCODE -ne 0) {
        throw 'Compose contract failed: test compose config did not render successfully'
    }
}
finally {
    foreach ($variableName in $composeEnvironmentNames) {
        $savedValue = $savedComposeEnvironment[$variableName]
        if ($null -eq $savedValue) {
            Remove-Item -LiteralPath "Env:$variableName" -ErrorAction SilentlyContinue
        }
        else {
            [Environment]::SetEnvironmentVariable($variableName, $savedValue, 'Process')
        }
    }
}

$localRendered = $localRenderedJson | ConvertFrom-Json
Assert-Contract ($localRendered.name -eq 'rayher-crm-stage1-local') 'rendered project name is not isolated'
Assert-Contract ($null -eq $localRendered.services.db.ports) 'MariaDB must not publish host ports'
Assert-Contract ($null -eq $localRendered.services.'redis-cache'.ports) 'Redis cache must not publish host ports'
Assert-Contract ($null -eq $localRendered.services.'redis-queue'.ports) 'Redis queue must not publish host ports'
Assert-Contract ($localRendered.services.frontend.ports.Count -eq 1) 'the local template must publish only the frontend port'
Assert-Contract ($composeText -match 'bench build --app rayher_crm') 'frontend must link packaged assets before nginx starts'
Assert-Contract ($composeText -match 'REALTIME_AUTH_ORIGIN: http://frontend:8080') 'WebSocket auth callbacks must use the Docker-resolvable frontend origin'
Assert-Contract ($composeText -match 'REALTIME_AUTH_HOST: frontend:8080') 'WebSocket Host must match the internal auth origin'
Assert-Contract ($composeText -match '/tmp/frappe\.conf\.template') 'frontend must patch a writable copy of the read-only nginx template'
Assert-Contract ($composeText -match 'exec nginx -g') 'frontend must run nginx in the foreground'

$volumeNames = @($localRendered.volumes.PSObject.Properties.Value.name)
Assert-Contract ($volumeNames.Count -ge 6) 'independent persistent volumes are incomplete'
foreach ($volumeName in $volumeNames) {
    Assert-Contract ($volumeName -like 'rayher-crm-stage1-local_*') "volume '$volumeName' is outside the new project namespace"
    Assert-Contract ($volumeName -notlike 'rayher-crm_*') "volume '$volumeName' collides with the old project"
}

Assert-Contract ($localRendered.services.frontend.ports[0].host_ip -eq '127.0.0.1') 'the default template must bind loopback only'
Assert-Contract ($localRendered.services.frontend.ports[0].published -eq '2224') 'the local template must publish TCP port 2224'
Assert-Contract ($localRendered.services.backend.build.args.CRM_APP_ARCHIVE -eq 'build/rayher_crm.zip') 'the local template must build from the production app archive'
Assert-Contract ([string]::IsNullOrEmpty($localRendered.services.backend.build.args.CRM_APP_ARCHIVE_SHA256)) 'the local template must require a package hash at build time'
Assert-Contract ($localRendered.services.migrate.environment.ALLOW_TESTS -eq 'false') 'the local template must disable Frappe tests'
Assert-Contract ($localRendered.services.migrate.environment.CRM_TEST_SITE -eq 'false') 'the local template must never be marked as a CRM test site'

$lanRendered = $lanRenderedJson | ConvertFrom-Json
Assert-Contract ($lanRendered.name -eq 'rayher-crm-stage1-local') 'the opt-in LAN template must stay inside the isolated project namespace'
Assert-Contract ($null -eq $lanRendered.services.db.ports) 'the LAN template must not publish MariaDB'
Assert-Contract ($null -eq $lanRendered.services.'redis-cache'.ports) 'the LAN template must not publish the Redis cache'
Assert-Contract ($null -eq $lanRendered.services.'redis-queue'.ports) 'the LAN template must not publish the Redis queue'
Assert-Contract ($lanRendered.services.frontend.ports.Count -eq 1) 'the LAN template must publish only the frontend port'
Assert-Contract ($lanRendered.services.frontend.ports[0].host_ip -eq '0.0.0.0') 'the opt-in LAN template must listen on all local IPv4 interfaces'
Assert-Contract ($lanRendered.services.frontend.ports[0].published -eq '2224') 'the LAN template must publish TCP port 2224'
Assert-Contract ($lanRendered.services.migrate.environment.ALLOW_TESTS -eq 'false') 'the LAN template must disable Frappe tests'
Assert-Contract ($lanRendered.services.migrate.environment.CRM_TEST_SITE -eq 'false') 'the LAN template must never be marked as a CRM test site'

$testRendered = $testRenderedJson | ConvertFrom-Json
Assert-Contract ($testRendered.name -eq 'rayher-crm-stage1-tests') 'backend tests must use a dedicated Compose project'
Assert-Contract ($testRendered.services.migrate.environment.SITE_NAME -eq 'rayher-crm.test') 'backend tests must use a dedicated Frappe site'
Assert-Contract ($testRendered.services.migrate.environment.ALLOW_TESTS -eq 'true') 'dedicated test site must enable Frappe tests'
Assert-Contract ($testRendered.services.migrate.environment.CRM_TEST_SITE -eq 'true') 'dedicated test site must carry the CRM test-site marker'
Assert-Contract ($testRendered.services.backend.image -eq 'rayher-crm-stage1:v15-test') 'backend tests must use a dedicated image tag'
Assert-Contract ($testRendered.services.backend.build.args.CRM_APP_ARCHIVE -eq 'build/rayher_crm.zip') 'test config must remain production-safe until the gate explicitly supplies the test build argument'
Assert-Contract ($testRendered.services.frontend.ports.Count -eq 1) 'test mode must publish only the frontend port'
Assert-Contract ($testRendered.services.frontend.ports[0].host_ip -eq '127.0.0.1') 'test frontend must only bind to loopback'
Assert-Contract ($testRendered.services.frontend.ports[0].published -eq '2225') 'test frontend must publish TCP port 2225'
$testVolumeNames = @($testRendered.volumes.PSObject.Properties.Value.name)
foreach ($volumeName in $testVolumeNames) {
    Assert-Contract ($volumeName -like 'rayher-crm-stage1-tests_*') "test volume '$volumeName' is outside the dedicated test project"
    Assert-Contract ($volumeName -notlike 'rayher-crm-stage1-local_*') "test volume '$volumeName' collides with operational data"
}

Write-Output 'Compose contract passed.'
