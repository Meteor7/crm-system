#Requires -Version 7.0
$ErrorActionPreference = 'Stop'
$directory = Join-Path ([IO.Path]::GetTempPath()) ('crm-report-contract-' + [guid]::NewGuid().ToString('N'))
[void][IO.Directory]::CreateDirectory($directory)
$log = Join-Path $directory 'log.txt'; $report = Join-Path $directory 'report.xml'
$valid = '<testsuites><testsuite tests="2" failures="0" errors="0" skipped="0"><testcase name="one"/><testcase name="two"/></testsuite></testsuites>'
$cases = @(
    @{Name='valid'; Log="Ran 2 tests in 1s`nOK"; XML=$valid; Exit=0; Pass=$true},
    @{Name='ANSI styled summary'; Log="`e[31;1mRan 2 tests in 1s`e[0m`n`e[31;1mOK`e[0m"; XML=$valid; Exit=0; Pass=$true},
    @{Name='exit failure'; Log="Ran 2 tests in 1s`nOK"; XML=$valid; Exit=1; Pass=$false},
    @{Name='zero tests'; Log="Ran 0 tests in 1s`nOK"; XML=$valid; Exit=0; Pass=$false},
    @{Name='missing summary'; Log='OK'; XML=$valid; Exit=0; Pass=$false},
    @{Name='traceback'; Log="Ran 2 tests in 1s`nOK`nTraceback (most recent call last):"; XML=$valid; Exit=0; Pass=$false},
    @{Name='duplicate summary'; Log="Ran 2 tests in 1s`nRan 2 tests in 1s`nOK"; XML=$valid; Exit=0; Pass=$false},
    @{Name='all skipped'; Log="Ran 2 tests in 1s`nOK (skipped=2)"; XML='<testsuite tests="2" skipped="2"><testcase><skipped/></testcase><testcase><skipped/></testcase></testsuite>'; Exit=0; Pass=$false},
    @{Name='count mismatch'; Log="Ran 3 tests in 1s`nOK"; XML=$valid; Exit=0; Pass=$false},
    @{Name='case failure'; Log="Ran 2 tests in 1s`nOK"; XML=$valid.Replace('<testcase name="one"/>','<testcase name="one"><failure/></testcase>'); Exit=0; Pass=$false},
    @{Name='malformed XML'; Log="Ran 2 tests in 1s`nOK"; XML='<testsuite'; Exit=0; Pass=$false},
    @{Name='partial skip'; Log="Ran 2 tests in 1s`nOK (skipped=1)"; XML='<testsuite tests="2" skipped="1"><testcase/><testcase><skipped/></testcase></testsuite>'; Exit=0; Pass=$true}
)
try {
    foreach ($case in $cases) {
        [IO.File]::WriteAllText($log, $case.Log)
        [IO.File]::WriteAllText($report, $case.XML)
        $passed = $true
        try { & (Join-Path $PSScriptRoot 'assert-backend-test-report.ps1') -LogPath $log -JUnitPath $report -BenchExit $case.Exit | Out-Null }
        catch { $passed = $false }
        if ($passed -ne $case.Pass) { throw "Report validation contract failed: $($case.Name)" }
    }
    Write-Output "Backend report contract passed: $($cases.Count) execution/report scenarios."
} finally {
    Remove-Item -LiteralPath $log, $report -ErrorAction SilentlyContinue
    [IO.Directory]::Delete($directory, $false)
}
