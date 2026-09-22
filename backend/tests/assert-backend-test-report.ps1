#Requires -Version 7.0
param(
    [Parameter(Mandatory)][string]$LogPath,
    [Parameter(Mandatory)][string]$JUnitPath,
    [Parameter(Mandatory)][int]$BenchExit
)
$ErrorActionPreference = 'Stop'
$text = [IO.File]::ReadAllText($LogPath)
$text = [regex]::Replace($text, '\x1b\[[0-?]*[ -/]*[@-~]', '')
$ran = [regex]::Matches($text, '(?m)^Ran\s+(\d+)\s+tests?\s+in\s+')
if ($BenchExit -ne 0 -or $ran.Count -ne 1 -or
    -not [regex]::IsMatch($text, '(?m)^OK(?:\s|$)') -or
    [regex]::IsMatch($text, '(?m)^FAILED\b') -or $text.Contains('Traceback (most recent call last):')) {
    throw "Backend execution failed or its result is ambiguous (benchExit=$BenchExit)."
}
$tests = [int]$ran[0].Groups[1].Value
$skipMatch = [regex]::Match($text, '(?m)^OK\s+\([^\r\n]*skipped=(\d+)')
$skipped = if ($skipMatch.Success) { [int]$skipMatch.Groups[1].Value } else { 0 }
$settings = [Xml.XmlReaderSettings]::new()
$settings.DtdProcessing = [Xml.DtdProcessing]::Prohibit
$reader = [Xml.XmlReader]::Create($JUnitPath, $settings)
try {
    $xml = [Xml.XmlDocument]::new()
    $xml.XmlResolver = $null
    $xml.Load($reader)
} finally { $reader.Dispose() }
$cases = @($xml.SelectNodes('//testcase'))
$suites = @($xml.SelectNodes('//testsuite[not(testsuite)]'))
$xmlTests = 0; $xmlSkipped = 0; $xmlFailures = 0; $xmlErrors = 0
foreach ($suite in $suites) {
    $xmlTests += [int]$suite.GetAttribute('tests')
    $xmlSkipped += [int]$suite.GetAttribute('skipped')
    $xmlFailures += [int]$suite.GetAttribute('failures')
    $xmlErrors += [int]$suite.GetAttribute('errors')
}
if ($tests -le 0 -or $tests - $skipped -le 0 -or $xmlTests -ne $tests -or $cases.Count -ne $tests -or
    $xmlSkipped -ne $skipped -or $xmlFailures -ne 0 -or $xmlErrors -ne 0 -or
    $xml.SelectNodes('//testcase/failure | //testcase/error').Count -ne 0 -or
    $xml.SelectNodes('//testcase/skipped').Count -ne $skipped) {
    throw "Backend stdout/JUnit mismatch or failure: stdoutTests=$tests xmlTests=$xmlTests cases=$($cases.Count) skipped=$skipped xmlSkipped=$xmlSkipped failures=$xmlFailures errors=$xmlErrors."
}
Write-Output "Backend test gate: tests=$tests executed=$($tests - $skipped) skipped=$skipped passed=True nativeJUnit=$JUnitPath"
