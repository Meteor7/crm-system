#Requires -Version 7.0
param(
    [string]$ProjectName = 'rayher-crm-stage1-tests',
    [string]$SiteName = 'rayher-crm.test',
    [string]$EnvFile = 'backend/test.env.example',
    [string]$ComposeFile = 'backend/compose.yaml',
    [string]$Module = '',
    [string]$ReportDirectory = ''
)
$ErrorActionPreference = 'Stop'
if (-not $SiteName.EndsWith('.test', [StringComparison]::OrdinalIgnoreCase)) {
    throw "Backend tests require a dedicated site ending in .test; refused '$SiteName'."
}
if ([IO.Path]::GetFileName($EnvFile) -ne 'test.env.example') {
    throw "Backend tests require backend/test.env.example; refused '$EnvFile'."
}
$keepReport = -not [string]::IsNullOrWhiteSpace($ReportDirectory)
$runId = [guid]::NewGuid().ToString('N')
if (-not $keepReport) { $ReportDirectory = Join-Path ([IO.Path]::GetTempPath()) "crm-tests-$runId" }
$ReportDirectory = [IO.Path]::GetFullPath($ReportDirectory)
[void][IO.Directory]::CreateDirectory($ReportDirectory)
$logPath = Join-Path $ReportDirectory 'backend-tests.log'
$junitPath = Join-Path $ReportDirectory 'backend-tests.xml'
$remoteReport = "/tmp/crm-tests-$runId.xml"
$composeArgs = @('compose', '--project-name', $ProjectName, '--env-file', $EnvFile, '-f', $ComposeFile)
$benchArgs = $composeArgs + @('exec', '-T', '--env', 'CI=1', 'backend', 'bench', '--site', $SiteName,
    'run-tests', '--app', 'rayher_crm', '--junit-xml-output', $remoteReport)
if ($Module) { $benchArgs += @('--module', $Module) }
try {
    # Frappe can return zero outside CI even on failure; validate native XML AND stdout.
    $ErrorActionPreference = 'Continue'
    $output = & docker @benchArgs 2>&1
    $benchExit = $LASTEXITCODE
    $ErrorActionPreference = 'Stop'
    $text = $output -join "`n"
    [IO.File]::WriteAllText($logPath, $text, [Text.UTF8Encoding]::new($false))
    # Native stderr is represented as ErrorRecord; print strings without PS error styling.
    $output | ForEach-Object { Write-Output ([string]$_) }
    # A failed copy must not reuse a previous report.
    if (Test-Path -LiteralPath $junitPath) { Remove-Item -LiteralPath $junitPath }
    & docker @composeArgs cp "backend:$remoteReport" $junitPath
    if ($LASTEXITCODE -ne 0) { throw 'Frappe did not produce a readable native JUnit report. See backend-tests.log.' }
    & (Join-Path $PSScriptRoot 'assert-backend-test-report.ps1') -LogPath $logPath -JUnitPath $junitPath -BenchExit $benchExit
}
finally {
    & docker @composeArgs exec -T backend rm -f $remoteReport | Out-Null
    if (-not $keepReport) {
        foreach ($path in @($logPath, $junitPath)) {
            if (Test-Path -LiteralPath $path) { Remove-Item -LiteralPath $path }
        }
        [IO.Directory]::Delete($ReportDirectory, $false)
    }
}
