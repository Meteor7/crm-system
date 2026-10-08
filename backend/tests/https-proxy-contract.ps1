#Requires -Version 7.0

[CmdletBinding()]
param(
    [string]$Template = (Join-Path (Split-Path -Parent (Split-Path -Parent $PSScriptRoot)) 'deploy/nginx/crm-https.conf.template'),
    [string]$ComposeFile = (Join-Path (Split-Path -Parent $PSScriptRoot) 'compose.yaml')
)

$ErrorActionPreference = 'Stop'

function Assert-Contract {
    param(
        [bool]$Condition,
        [string]$Message
    )

    if (-not $Condition) {
        throw "HTTPS proxy contract failed: $Message"
    }
}

Assert-Contract (Test-Path -LiteralPath $Template -PathType Leaf) 'deploy/nginx/crm-https.conf.template must exist'
Assert-Contract (Test-Path -LiteralPath $ComposeFile -PathType Leaf) 'backend/compose.yaml must exist'

$templateText = ('' + (Get-Content -LiteralPath $Template -Raw -Encoding UTF8)).Replace("`r`n", "`n")
$composeText = ('' + (Get-Content -LiteralPath $ComposeFile -Raw -Encoding UTF8)).Replace("`r`n", "`n")
$directives = (($templateText -split "`n") | Where-Object { $_ -notmatch '^\s*#' }) -join "`n"

$expectedVariables = @('CRM_DOMAIN', 'CRM_UPSTREAM', 'TLS_CERTIFICATE', 'TLS_CERTIFICATE_KEY')
$foundVariables = @([regex]::Matches($directives, '\$\{([A-Za-z_][A-Za-z0-9_]*)\}') | ForEach-Object { $_.Groups[1].Value } | Select-Object -Unique)
$unexpectedVariables = @($foundVariables | Where-Object { $_ -notin $expectedVariables })
$missingVariables = @($expectedVariables | Where-Object { $_ -notin $foundVariables })
Assert-Contract ($unexpectedVariables.Count -eq 0 -and $missingVariables.Count -eq 0) "the template must substitute exactly $($expectedVariables -join ', '); unexpected: $($unexpectedVariables -join ', '); missing: $($missingVariables -join ', ')"

Assert-Contract ($directives -match '(?m)^\s+listen 80;$') 'the HTTP listener is missing'
Assert-Contract ($directives -match '(?m)^\s+return 308 https://\$host\$request_uri;$') 'HTTP must redirect permanently to HTTPS'
Assert-Contract ($directives -match '(?m)^\s+listen 443 ssl;$') 'the TLS listener is missing'
Assert-Contract ($directives -match '(?m)^\s+http2 on;$') 'HTTP/2 must be enabled with the http2 directive'
Assert-Contract ($directives -notmatch 'listen [^;\n]*\bhttp2\b') 'the listen ... http2 parameter is deprecated since nginx 1.25.1'
Assert-Contract ($directives -match '(?m)^\s+ssl_protocols TLSv1\.2 TLSv1\.3;$') 'only TLS 1.2 and 1.3 may be enabled'
Assert-Contract ($directives -match '(?m)^\s+server \$\{CRM_UPSTREAM\};$') 'the upstream must be the parameterised loopback frontend'
Assert-Contract ($directives -notmatch '192\.168\.') 'the template must not hard-code a LAN address'
Assert-Contract ([regex]::Matches($directives, '(?m)^\s+proxy_set_header X-Forwarded-Proto https;$').Count -eq 2) 'both locations must forward the HTTPS scheme'
Assert-Contract ($directives -match '(?m)^\s+proxy_set_header Upgrade \$http_upgrade;$') 'the WebSocket Upgrade header is missing'
Assert-Contract ($directives -match '(?m)^\s+proxy_set_header Connection \$connection_upgrade;$') 'the WebSocket Connection header is missing'
Assert-Contract ($directives -notmatch 'Strict-Transport-Security') 'HSTS stays off while the internal certificate is renewed by hand'

# The host proxy must not refuse or cut off what the Compose frontend accepts.
$composeBodySize = [regex]::Match($composeText, '(?m)^\s+CLIENT_MAX_BODY_SIZE:\s*"?([0-9]+[kKmMgG]?)"?\s*$').Groups[1].Value
Assert-Contract ($composeBodySize -ne '') 'backend/compose.yaml must set CLIENT_MAX_BODY_SIZE for the frontend'
Assert-Contract ($directives -match "(?m)^\s+client_max_body_size $([regex]::Escape($composeBodySize));`$") "client_max_body_size must match the frontend's $composeBodySize"
$composeReadTimeout = [regex]::Match($composeText, '(?m)^\s+PROXY_READ_TIMEOUT:\s*"?([0-9]+)"?\s*$').Groups[1].Value
Assert-Contract ($composeReadTimeout -ne '') 'backend/compose.yaml must set PROXY_READ_TIMEOUT for the frontend'
Assert-Contract ([regex]::Matches($directives, "(?m)^\s+proxy_read_timeout $($composeReadTimeout)s;`$").Count -eq 2) "both locations must wait as long as the frontend does ($($composeReadTimeout)s)"

Write-Output 'HTTPS proxy contract passed.'
