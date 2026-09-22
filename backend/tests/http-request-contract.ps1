#Requires -Version 7.0
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'http-acceptance-values.ps1')
$temporaryFile = [IO.Path]::GetTempFileName()
[IO.File]::WriteAllText($temporaryFile, 'HTTP encoding fixture')
function Assert-IsoTimestamp([string]$EncodedValue) {
    $Value = [Text.Encoding]::UTF8.GetString([Convert]::FromBase64String($EncodedValue))
    if ($Value -notmatch '^\d{4}-\d{2}-\d{2}T' -or $Value -notmatch '(Z|[+-]\d{2}:\d{2})$' -or
        [DateTimeOffset]::Parse($Value).UtcTicks -ne [DateTimeOffset]::Parse('2026-09-09T09:47:12.123456Z').UtcTicks) {
        throw "HTTP encoder lost timestamp format, timezone or precision: $Value"
    }
}
$start = [Diagnostics.ProcessStartInfo]::new()
$start.FileName = if ($IsWindows) { 'python' } else { 'python3' }
$start.UseShellExecute = $false
$start.RedirectStandardOutput = $true
$start.RedirectStandardError = $true
[void]$start.ArgumentList.Add('-u')
[void]$start.ArgumentList.Add((Join-Path $PSScriptRoot 'http-echo-fixture.py'))
$server = [Diagnostics.Process]::Start($start)
try {
    $portTask = $server.StandardOutput.ReadLineAsync()
    if (-not $portTask.Wait(10000)) { throw 'HTTP fixture did not start.' }
    $port = [int]$portTask.Result
    if ($port -le 0) { throw 'HTTP fixture returned no port.' }
    $BaseUrl = "http://127.0.0.1:$port"
    $files = @(Get-ChildItem -LiteralPath $PSScriptRoot -Filter 'http-stage*-acceptance.ps1')
    if ($files.Count -ne 6) { throw 'Expected all six HTTP acceptance suites.' }
    foreach ($file in $files) {
        $tokens = $null; $errors = $null
        $ast = [Management.Automation.Language.Parser]::ParseFile($file.FullName, [ref]$tokens, [ref]$errors)
        if ($errors) { throw "Could not parse $($file.Name)." }
        $helper = $ast.Find({param($node) $node -is [Management.Automation.Language.FunctionDefinitionAst] -and $node.Name -eq 'Invoke-CrmPost'}, $true)
        if (-not $helper) { throw "Missing RPC helper in $($file.Name)." }
        # Load only the actual RPC function; never execute test setup or cleanup.
        . ([scriptblock]::Create($helper.Extent.Text))
        $session = [Microsoft.PowerShell.Commands.WebRequestSession]::new()
        $initial = Invoke-RestMethod "$BaseUrl/initial-json" -Method Post -ContentType 'application/json' -Body '{"initial":true}' -WebSession $session
        $response = Invoke-CrmPost $session 'echo' @{input=@{text='客户 A & B + 1'}; expectedModified='a+b&c'; empty=''}
        if ($response.content_type -notlike 'application/x-www-form-urlencoded*') {
            throw "$($file.Name) inherited a stale content type: $($response.content_type)"
        }
        $inputBody = $response.form.input[0] | ConvertFrom-Json
        if ($inputBody.text -ne '客户 A & B + 1' -or $response.form.expectedModified[0] -ne 'a+b&c' -or $response.form.empty[0] -ne '') {
            throw "$($file.Name) corrupted RPC form data."
        }
        $dated = Invoke-CrmPost $session 'echo' @{expectedModified=$initial.message.modified}
        Assert-IsoTimestamp $dated.encoded_form.expectedModified[0]
        $nested = Invoke-CrmPost $session 'echo' @{input=@{expectedModified=$initial.message.modified}}
        $nestedInput = [System.Text.Json.JsonDocument]::Parse([string]$nested.form.input[0])
        try {
            $nestedTimestamp = $nestedInput.RootElement.GetProperty('expectedModified').GetString()
            Assert-IsoTimestamp ([Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($nestedTimestamp)))
        } finally { $nestedInput.Dispose() }
        if (-not (ConvertTo-CrmHttpFormValue -Value $initial.message.modified).EndsWith('Z')) {
            throw 'UTC response timestamp lost its timezone during assertion formatting.'
        }
        $multipartHelpers = $ast.FindAll({param($node) $node -is [Management.Automation.Language.FunctionDefinitionAst] -and $node.Name -in @('Invoke-MultipartFile', 'Invoke-MultipartFiles')}, $true)
        foreach ($multipart in $multipartHelpers) {
            . ([scriptblock]::Create($multipart.Extent.Text))
            $arguments = @{Session=$session; Method='echo'; Fields=@{expectedModified=$initial.message.modified}}
            if ($multipart.Name -eq 'Invoke-MultipartFile') {
                $arguments.FieldName='file'; $arguments.FilePath=$temporaryFile; $arguments.MimeType='text/plain'
            } else {
                $arguments.Files=@(@{Name='file';Path=$temporaryFile;MimeType='text/plain'})
            }
            $uploaded = & $multipart.Name @arguments
            Assert-IsoTimestamp $uploaded.encoded_form.expectedModified[0]
        }
    }
    Write-Output 'HTTP request contract passed: six RPC and three multipart helpers; sessions, Unicode, escaping and ISO timestamp precision.'
} finally {
    if (-not $server.HasExited) { $server.Kill($true) }
    $server.WaitForExit()
    $server.Dispose()
    Remove-Item -LiteralPath $temporaryFile
}
