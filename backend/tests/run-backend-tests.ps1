param(
    [string]$ProjectName = 'rayher-crm-stage1-tests',
    [string]$SiteName = 'rayher-crm.test',
    [string]$EnvFile = 'backend/test.env.example',
    [string]$ComposeFile = 'backend/compose.yaml',
    [string]$Module = ''
)

$ErrorActionPreference = 'Stop'

if (-not $SiteName.EndsWith('.test', [StringComparison]::OrdinalIgnoreCase)) {
    throw "Backend tests require a dedicated site ending in .test; refused site '$SiteName'."
}
if ([IO.Path]::GetFileName($EnvFile) -ne 'test.env.example') {
    throw "Backend tests require backend/test.env.example; refused env file '$EnvFile'."
}

function Write-TrustedUtf8File {
    param([string]$Path, [string]$Content)

    $directory = Split-Path -Parent $Path
    if ($directory -and -not (Test-Path -LiteralPath $directory)) {
        New-Item -ItemType Directory -Path $directory -Force | Out-Null
    }

    if ($env:OS -ne 'Windows_NT') {
        [IO.File]::WriteAllText($Path, $Content, [Text.UTF8Encoding]::new($false))
        return
    }

    $encoded = [Convert]::ToBase64String([Text.UTF8Encoding]::new($false).GetBytes($Content))
    $base64Path = "$Path.b64"
    $plainPath = "$Path.plain"
    $first = $true
    for ($offset = 0; $offset -lt $encoded.Length; $offset += 3000) {
        $chunk = $encoded.Substring($offset, [Math]::Min(3000, $encoded.Length - $offset))
        $redirect = if ($first) { '>' } else { '>>' }
        & cmd.exe /d /c "echo $chunk$redirect`"$base64Path`"" | Out-Null
        if ($LASTEXITCODE -ne 0) { throw "Failed to write JUnit base64 payload." }
        $first = $false
    }

    & certutil.exe -f -decode $base64Path $plainPath | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "Failed to decode JUnit XML." }
    & cmd.exe /d /c "move /Y `"$plainPath`" `"$Path`"" | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "Failed to publish JUnit XML." }
    Remove-Item -LiteralPath $base64Path -Force
}

$composeArgs = @('--project-name', $ProjectName, '--env-file', $EnvFile, '-f', $ComposeFile)
$benchArgs = @(
    'compose'
) + $composeArgs + @(
    'exec', '-T', 'backend',
    'bench', '--site', $SiteName, 'run-tests', '--app', 'rayher_crm'
)
if (-not [string]::IsNullOrWhiteSpace($Module)) {
    $benchArgs += @('--module', $Module)
}

$previousErrorActionPreference = $ErrorActionPreference
$ErrorActionPreference = 'Continue'
$output = & docker @benchArgs 2>&1
$benchExit = $LASTEXITCODE
$ErrorActionPreference = $previousErrorActionPreference
$output | ForEach-Object { Write-Output $_ }
$text = $output -join "`n"

$ran = [regex]::Match($text, '(?m)^Ran\s+(\d+)\s+tests?\s+in\s+')
$ok = [regex]::IsMatch($text, '(?m)^OK(?:\s|$)')
$failed = [regex]::IsMatch($text, '(?m)^FAILED\s+\(')
$traceback = $text.Contains('Traceback (most recent call last):')
$failureMatch = [regex]::Match($text, '(?m)^FAILED\s+\([^\r\n]*failures=(\d+)')
$errorMatch = [regex]::Match($text, '(?m)^FAILED\s+\([^\r\n]*errors=(\d+)')
$skippedMatch = [regex]::Match($text, '(?m)^(?:OK|FAILED)\s+\([^\r\n]*skipped=(\d+)')
$tests = if ($ran.Success) { [int]$ran.Groups[1].Value } else { 0 }
$failures = if ($failureMatch.Success) { [int]$failureMatch.Groups[1].Value } else { 0 }
$errors = if ($errorMatch.Success) { [int]$errorMatch.Groups[1].Value } else { 0 }
$skipped = if ($skippedMatch.Success) { [int]$skippedMatch.Groups[1].Value } else { 0 }
$executed = $tests - $skipped
if (($benchExit -ne 0 -or -not $ran.Success -or $traceback -or $tests -le 0 -or $executed -le 0) -and ($failures + $errors -eq 0)) {
    $errors = 1
}
$passed = $benchExit -eq 0 -and $ran.Success -and $tests -gt 0 -and $executed -gt 0 -and $ok -and -not $failed -and -not $traceback -and $failures -eq 0 -and $errors -eq 0

$moduleLabel = if ([string]::IsNullOrWhiteSpace($Module)) { 'rayher_crm' } else { $Module }
$escapedModule = [Security.SecurityElement]::Escape($moduleLabel)
$escapedSite = [Security.SecurityElement]::Escape($SiteName)
$timestamp = [DateTime]::UtcNow.ToString('o')
$junitText = "<?xml version=`"1.0`" encoding=`"utf-8`"?>`n<testsuite name=`"$escapedModule`" tests=`"$tests`" failures=`"$failures`" errors=`"$errors`" skipped=`"$skipped`" timestamp=`"$timestamp`"><properties><property name=`"site`" value=`"$escapedSite`" /><property name=`"benchExit`" value=`"$benchExit`" /></properties></testsuite>`n"
$junitPath = Join-Path ([IO.Path]::GetTempPath()) "rayher-crm-junit-$([Guid]::NewGuid().ToString('N')).xml"

try {
    Write-TrustedUtf8File -Path $junitPath -Content $junitText
    [xml]$junit = Get-Content -LiteralPath $junitPath -Raw -Encoding UTF8
    $suite = $junit.testsuite
    $xmlTests = [int]$suite.tests
    $xmlFailures = [int]$suite.failures
    $xmlErrors = [int]$suite.errors
    $xmlSkipped = [int]$suite.skipped
    if ($xmlTests -ne $tests -or $xmlFailures -ne $failures -or $xmlErrors -ne $errors -or $xmlSkipped -ne $skipped) {
        throw 'JUnit XML summary does not match the parsed unittest output.'
    }
}
finally {
    if (Test-Path -LiteralPath $junitPath) {
        Remove-Item -LiteralPath $junitPath -Force
    }
}

Write-Output "Backend test gate: tests=$tests executed=$executed skipped=$skipped passed=$passed failures=$failures errors=$errors traceback=$traceback benchExit=$benchExit junit=parsed"
if (-not $passed -or $xmlFailures -ne 0 -or $xmlErrors -ne 0) {
    exit 1
}
