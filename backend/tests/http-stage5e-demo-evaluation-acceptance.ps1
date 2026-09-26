param(
    [string]$ProjectName = 'rayher-crm-stage1-tests',
    [string]$SiteName = 'rayher-crm.test',
    [string]$BaseUrl = 'http://127.0.0.1:2225'
)

$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'http-acceptance-values.ps1')
$backendRoot = Split-Path -Parent $PSScriptRoot
$composeFile = Join-Path $backendRoot 'compose.yaml'
$envFile = Join-Path $backendRoot 'test.env.example'
$envFileName = [IO.Path]::GetFileName($envFile)
if (-not $SiteName.EndsWith('.test') -or $envFileName -ne 'test.env.example') {
    throw "Acceptance requires a dedicated .test site and backend/test.env.example; refused '$SiteName' / '$envFileName'."
}
$composeArgs = @('--project-name', $ProjectName, '--env-file', $envFile, '-f', $composeFile)
$created = [ordered]@{
    Account=$null; Site=$null; Contact=$null; Opportunity=$null; Request=$null; Evaluation=$null
    InternalReportArtifact=$null; ExternalReportArtifact=$null
    Sales=$null; Engineer=$null; OtherEngineer=$null; Manager=$null
}

function Invoke-MultipartFiles {
    param($Session, [string]$Method, [hashtable]$Fields, [array]$Files)
    $boundary = '----------------crmstage5e' + [guid]::NewGuid().ToString('N')
    $stream = New-Object IO.MemoryStream
    try {
        foreach ($key in $Fields.Keys) {
            $bytes = [Text.Encoding]::UTF8.GetBytes("--$boundary`r`nContent-Disposition: form-data; name=`"$key`"`r`n`r`n$(ConvertTo-CrmHttpFormValue -Value $Fields[$key])`r`n")
            $stream.Write($bytes, 0, $bytes.Length)
        }
        foreach ($file in $Files) {
            $header = [Text.Encoding]::UTF8.GetBytes("--$boundary`r`nContent-Disposition: form-data; name=`"$($file.Name)`"; filename=`"$([IO.Path]::GetFileName($file.Path))`"`r`nContent-Type: $($file.MimeType)`r`n`r`n")
            $stream.Write($header, 0, $header.Length)
            $fileBytes = [IO.File]::ReadAllBytes($file.Path); $stream.Write($fileBytes, 0, $fileBytes.Length)
            $separator = [Text.Encoding]::UTF8.GetBytes("`r`n"); $stream.Write($separator, 0, $separator.Length)
        }
        $tail = [Text.Encoding]::UTF8.GetBytes("--$boundary--`r`n"); $stream.Write($tail, 0, $tail.Length)
        return (Invoke-RestMethod -Uri "$BaseUrl/api/method/$Method" -Method Post -Body $stream.ToArray() -ContentType "multipart/form-data; boundary=$boundary" -WebSession $Session).message
    } finally { $stream.Dispose() }
}

function Invoke-CrmPost {
    param($Session, [string]$Method, [hashtable]$Arguments)
    $body = @{}
    foreach ($key in $Arguments.Keys) {
        $value = ConvertTo-CrmHttpFormValue -Value $Arguments[$key]
        $body[$key] = if ($key -in @('input', 'command')) { $value | ConvertTo-Json -Compress -Depth 15 } else { $value }
    }
    return (Invoke-RestMethod -Uri "$BaseUrl/api/method/$Method" -Method Post -ContentType 'application/x-www-form-urlencoded; charset=utf-8' -Body $body -WebSession $Session).message
}

function ConvertTo-PythonStringLiteral {
    param([string]$Value)
    return "'" + $Value.Replace('\', '\\').Replace("'", "\'") + "'"
}

function Remove-TestDoc {
    param([string]$DocType, [string]$Name)
    if ([string]::IsNullOrWhiteSpace($Name)) { return }
    $pythonArgs = "[$(ConvertTo-PythonStringLiteral $DocType),$(ConvertTo-PythonStringLiteral $Name)]"
    & docker compose @composeArgs exec -T backend bench --site $SiteName execute frappe.delete_doc --args $pythonArgs | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "Cleanup failed for $DocType $Name" }
}

function Remove-TestChildren {
    param([string]$DocType, [string]$Field, [string]$Value)
    if ([string]::IsNullOrWhiteSpace($Value)) { return }
    $pythonArgs = "[$(ConvertTo-PythonStringLiteral $DocType),{$(ConvertTo-PythonStringLiteral $Field):$(ConvertTo-PythonStringLiteral $Value)}]"
    & docker compose @composeArgs exec -T backend bench --site $SiteName execute frappe.db.delete --args $pythonArgs | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "Cleanup failed for $DocType children." }
}

try {
    $adminPassword = (& docker compose @composeArgs run --rm --no-deps --entrypoint cat secrets-init /run/crm-local-secrets/admin_password).Trim()
    if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($adminPassword)) { throw 'Could not read isolated Administrator password.' }
    $adminSession = New-Object Microsoft.PowerShell.Commands.WebRequestSession
    Invoke-RestMethod -Uri "$BaseUrl/api/method/login" -Method Post -Body @{usr='Administrator';pwd=$adminPassword} -WebSession $adminSession | Out-Null

    $stamp = [DateTimeOffset]::UtcNow.ToUnixTimeMilliseconds()
    $passwords = @{
        Sales="Aa1!$([guid]::NewGuid().ToString('N'))"
        Engineer="Aa1!$([guid]::NewGuid().ToString('N'))"
        OtherEngineer="Aa1!$([guid]::NewGuid().ToString('N'))"
        Manager="Aa1!$([guid]::NewGuid().ToString('N'))"
    }
    foreach ($spec in @(
        @{Key='Sales'; Email="crm-stage5e-sales-$stamp@example.invalid"; Role='CRM Sales'},
        @{Key='Engineer'; Email="crm-stage5e-engineer-$stamp@example.invalid"; Role='CRM Engineer'},
        @{Key='OtherEngineer'; Email="crm-stage5e-other-engineer-$stamp@example.invalid"; Role='CRM Engineer'},
        @{Key='Manager'; Email="crm-stage5e-manager-$stamp@example.invalid"; Role='CRM Manager'}
    )) {
        $json = @{
            email=$spec.Email; first_name="Stage 5E $($spec.Key)"; enabled=1; send_welcome_email=0
            new_password=$passwords[$spec.Key]; roles=@(@{role=$spec.Role})
        } | ConvertTo-Json -Compress -Depth 5
        $response = Invoke-RestMethod -Uri "$BaseUrl/api/resource/User" -Method Post -ContentType 'application/json' -Body $json -WebSession $adminSession
        $created[$spec.Key] = $response.data.name
    }

    $sessions = @{}
    foreach ($key in @('Sales', 'Engineer', 'OtherEngineer', 'Manager')) {
        $sessions[$key] = New-Object Microsoft.PowerShell.Commands.WebRequestSession
        Invoke-RestMethod -Uri "$BaseUrl/api/method/login" -Method Post -Body @{usr=$created[$key];pwd=$passwords[$key]} -WebSession $sessions[$key] | Out-Null
    }

    $account = Invoke-CrmPost $sessions.Sales 'rayher_crm.api.v1.accounts.create_account' @{input=@{
        name="Stage 5E Account $stamp";shortName="S5E $stamp";segment='Frontend';tier='A';city='Shanghai';region='East China';owner=$created.Sales
    }}
    $created.Account = $account.data.id
    $productionStatus = -join ([char[]]@(0x91CF, 0x4EA7))
    $siteTitle = "Stage 5E Site $stamp"
    $siteJson = @{
        address_title=$siteTitle;address_type='Other';address_line1=$siteTitle;city='Shanghai';country='China'
        custom_crm_owner=$created.Sales;custom_crm_site_type='Fab';custom_crm_process='Frontend';custom_crm_status=$productionStatus
        links=@(@{link_doctype='Customer';link_name=$created.Account})
    } | ConvertTo-Json -Compress -Depth 5
    $siteBytes = [Text.Encoding]::UTF8.GetBytes($siteJson)
    $site = Invoke-RestMethod -Uri "$BaseUrl/api/resource/Address" -Method Post -ContentType 'application/json; charset=utf-8' -Body $siteBytes -WebSession $adminSession
    $created.Site = $site.data.name

    $contact = Invoke-CrmPost $sessions.Sales 'rayher_crm.api.v1.contacts.create_contact' @{input=@{
        accountId=$created.Account;siteId=$created.Site;name="Stage 5E Contact $stamp";title='Director';department='Engineering'
        phone='13800000011';email="stage5e-contact-$stamp@example.invalid";relationship='Developing';status='Active';owner=$created.Sales
    }}
    $created.Contact = $contact.data.id
    $discoveryStage = -join ([char[]]@(0x9700, 0x6C42, 0x53D1, 0x73B0))
    $waferDemoStage = 'Wafer Demo' + (-join ([char[]]@(0x786E, 0x8BA4)))
    $budgetApprovalStage = -join ([char[]]@(0x9884, 0x7B97, 0x5BA1, 0x6279))
    $opportunity = Invoke-CrmPost $sessions.Sales 'rayher_crm.api.v1.opportunities.create_strategy_opportunity' @{input=@{
        accountId=$created.Account;siteId=$created.Site;title="Stage 5E Opportunity $stamp";owner=$created.Sales
        stage=$discoveryStage;forecast='Pipeline';amount='300000.00';probability=50;intentScore=85;poDate='2026-12-31'
        toolType='Inspection';saleType='New Equipment';subRegion='East China';currency='CNY';originalAmount='300000.00'
    }}
    $created.Opportunity = $opportunity.data.id

    $formData = @{
        contactPerson='forged';industry='Frontend Fab';salesContact=$created.Sales;demoOwner=$created.Engineer
        sizeShape='300 mm';material='Si(100)';specificRequest='Edge exclusion';detectMeasure='Detect particles'
        expectedResults='Wafer map';otherTools='Tool of record';primaryTool='Inspection 3000';complementaryTool=''
        timing='2026-12-20';keySuccessFactors='Capture above 95%';internalQuestions='Confirm recipe'
        customerQuestions='Confirm sample readiness';wafers=@(@{
            slotId='1';wid="HTTP-$stamp-W01";waferSpecificity='Si wafer';notchFlat='Notch up'
            doiMetrologyItems='Particles';resultFileProvided='Wafer map'
        })
    }
    $requestInput = @{
        accountId=$created.Account;primaryContactId=$created.Contact;requirementId="REQ-HTTP-$stamp"
        opportunityId=$created.Opportunity;formData=$formData;customerExpectedDate='2026-12-31';submit=$false
    }
    $request = Invoke-CrmPost $sessions.Sales 'rayher_crm.api.v1.demo_requests.create_demo_request' @{input=$requestInput}
    $created.Request = $request.data.id
    if ($request.data.status -ne 'Draft' -or $request.data.createdBy -ne $created.Sales) { throw 'HTTP Draft create did not preserve server identity/state.' }
    if ($request.data.formData.contactPerson -eq 'forged') { throw 'HTTP Demo contact display trusted client text.' }
    $opportunityAfterRequest = (Invoke-RestMethod -Uri "$BaseUrl/api/method/rayher_crm.api.v1.opportunities.get_strategy_opportunity?id=$([Uri]::EscapeDataString($created.Opportunity))" -WebSession $sessions.Sales).message.data
    if ($opportunityAfterRequest.stage -ne $waferDemoStage) { throw "Demo Request creation did not advance Opportunity to $waferDemoStage." }

    $conflictStatus = 0
    $updatedInput = $requestInput.Clone(); $updatedInput.submit = $false
    $updated = Invoke-CrmPost $sessions.Sales 'rayher_crm.api.v1.demo_requests.update_demo_request' @{id=$created.Request;input=$updatedInput;expectedModified=$request.data.modified}
    try {
        Invoke-CrmPost $sessions.Sales 'rayher_crm.api.v1.demo_requests.update_demo_request' @{id=$created.Request;input=$updatedInput;expectedModified=$request.data.modified} | Out-Null
    } catch { $conflictStatus = [int]$_.Exception.Response.StatusCode }
    if ($conflictStatus -ne 409) { throw "Expected Demo Request stale HTTP 409, got $conflictStatus." }
    $submitted = Invoke-CrmPost $sessions.Sales 'rayher_crm.api.v1.demo_requests.transition_demo_request' @{id=$created.Request;command=@{type='submit'};expectedModified=$updated.data.modified}
    if ($submitted.data.request.status -ne 'Engineer Review') { throw 'HTTP submit did not reach Engineer Review.' }

    $comment = Invoke-CrmPost $sessions.Sales 'rayher_crm.api.v1.demo_requests.add_demo_comment' @{demoRequestId=$created.Request;input=@{body='Please review';mentionedPersonId=$created.Engineer;mentionedPerson='forged'}}
    if ($comment.data.author -ne $created.Sales -or $comment.data.mentionedPerson -eq 'forged') { throw 'HTTP Comment trusted client identity/label.' }

    $engineering = Invoke-CrmPost $sessions.Engineer 'rayher_crm.api.v1.demo_requests.transition_demo_request' @{id=$created.Request;expectedModified=$submitted.data.request.modified;command=@{
        type='engineer_approve';engineerOwner=$created.Engineer;testPlan='Particle recipe';assignedEquipment='Inspection 3000'
        resourceWindow='Week 48';estimatedCompletionDate='2026-12-20';technicalRisk='Contamination';comment='Feasible'
    }}
    if ($engineering.data.request.status -ne 'Manager Approval') { throw 'Engineer HTTP approval did not reach Manager Approval.' }
    $approved = Invoke-CrmPost $sessions.Manager 'rayher_crm.api.v1.demo_requests.transition_demo_request' @{id=$created.Request;command=@{type='manager_approve';comment='Approved'};expectedModified=$engineering.data.request.modified}
    $created.Evaluation = $approved.data.evaluation.id
    if ($approved.data.request.status -ne 'Converted') { throw 'Manager HTTP approval did not convert Request.' }

    $duplicateStatus = 0
    try { Invoke-CrmPost $sessions.Manager 'rayher_crm.api.v1.demo_requests.transition_demo_request' @{id=$created.Request;command=@{type='manager_approve';comment='Again'};expectedModified=$approved.data.request.modified} | Out-Null } catch { $duplicateStatus = [int]$_.Exception.Response.StatusCode }
    if ($duplicateStatus -ne 409) { throw "Expected duplicate approve HTTP 409, got $duplicateStatus." }

    $otherList = Invoke-RestMethod -Uri "$BaseUrl/api/method/rayher_crm.api.v1.evaluations.list_evaluations" -WebSession $sessions.OtherEngineer
    if (@($otherList.message.data.items | Where-Object {$_.id -eq $created.Evaluation}).Count -ne 0) { throw 'Unassigned Engineer could list Evaluation.' }

    $evaluation = $approved.data.evaluation
    $scopeConfirmed = Invoke-CrmPost $sessions.Engineer 'rayher_crm.api.v1.evaluations.update_evaluation_status' @{id=$created.Evaluation;command=@{status='Scope Confirmed'};expectedModified=$evaluation.modified}
    $evalConflict = 0
    try { Invoke-CrmPost $sessions.Engineer 'rayher_crm.api.v1.evaluations.update_evaluation_status' @{id=$created.Evaluation;command=@{status='Sample Received'};expectedModified=$evaluation.modified} | Out-Null } catch { $evalConflict = [int]$_.Exception.Response.StatusCode }
    if ($evalConflict -ne 409) { throw "Expected Evaluation stale HTTP 409, got $evalConflict." }
    $sampled = Invoke-CrmPost $sessions.Engineer 'rayher_crm.api.v1.evaluations.update_evaluation_status' @{id=$created.Evaluation;command=@{status='Sample Received'};expectedModified=$scopeConfirmed.data.modified}
    $scheduled = Invoke-CrmPost $sessions.Engineer 'rayher_crm.api.v1.evaluations.update_evaluation_status' @{id=$created.Evaluation;command=@{status='Scheduled'};expectedModified=$sampled.data.modified}
    $current = $scheduled.data
    $step = Invoke-CrmPost $sessions.Engineer 'rayher_crm.api.v1.evaluations.update_evaluation_status' @{id=$created.Evaluation;command=@{status='Testing'};expectedModified=$current.modified}
    $current = $step.data
    if (@($current.runs).Count -ne 0 -or $current.reportStatus -ne 'Not Ready') { throw 'Testing must begin with zero Test Runs and no report.' }
    $blockedStatus = 0
    try { Invoke-CrmPost $sessions.Engineer 'rayher_crm.api.v1.evaluations.update_evaluation_status' @{id=$created.Evaluation;command=@{status='Internal Review'};expectedModified=$current.modified} | Out-Null } catch { $blockedStatus = [int]$_.Exception.Response.StatusCode }
    if ($blockedStatus -ne 409) { throw "Expected Internal Review gate HTTP 409 before Test Report upload, got $blockedStatus." }
    $internalReportPath = Join-Path ([IO.Path]::GetTempPath()) "crm-stage5e-internal-report-$stamp.txt"
    $externalReportPath = Join-Path ([IO.Path]::GetTempPath()) "crm-stage5e-external-report-$stamp.txt"
    [IO.File]::WriteAllText($internalReportPath, 'internal capture=96.5', [Text.UTF8Encoding]::new($false))
    [IO.File]::WriteAllText($externalReportPath, 'customer capture=96.5', [Text.UTF8Encoding]::new($false))
    try {
        $uploaded = Invoke-MultipartFiles $sessions.Engineer 'rayher_crm.api.v1.evaluations.release_demo_test_report' @{id=$created.Evaluation; expectedRound=1} @(
            @{Name='internalFile';Path=$internalReportPath;MimeType='text/plain'},
            @{Name='externalFile';Path=$externalReportPath;MimeType='text/plain'}
        )
    } finally {
        if (Test-Path -LiteralPath $internalReportPath) { Remove-Item -LiteralPath $internalReportPath -Force }
        if (Test-Path -LiteralPath $externalReportPath) { Remove-Item -LiteralPath $externalReportPath -Force }
    }
    $created.InternalReportArtifact = $uploaded.data.internalReportArtifact.id
    $created.ExternalReportArtifact = $uploaded.data.externalReportArtifact.id
    if ($uploaded.data.internalReportArtifact.fileName -notlike '*internal-report*' -or $uploaded.data.externalReportArtifact.fileName -notlike '*external-report*' -or $uploaded.data.version -ne 1) { throw 'Uploaded Test Report metadata is incorrect.' }
    $current = (Invoke-RestMethod -Uri "$BaseUrl/api/method/rayher_crm.api.v1.evaluations.get_evaluation?id=$([Uri]::EscapeDataString($created.Evaluation))" -WebSession $sessions.Engineer).message.data
    if ($current.internalReportArtifactId -ne $created.InternalReportArtifact -or $current.externalReportArtifactId -ne $created.ExternalReportArtifact -or @($current.runs).Count -ne 0 -or $current.reportStatus -ne 'Ready') { throw 'Zero-Run report upload did not persist both report artifacts.' }
    $planned = Invoke-CrmPost $sessions.Engineer 'rayher_crm.api.v1.evaluations.add_evaluation_run' @{id=$created.Evaluation;input=@{expectedModified=$current.modified;date='2026-12-10';lot='LOT-PLAN';wafers=2;capture=$null;falsePositive=$null;wph=$null;summary=''}}
    $completed = Invoke-CrmPost $sessions.Engineer 'rayher_crm.api.v1.evaluations.add_evaluation_run' @{id=$created.Evaluation;input=@{expectedModified=$planned.data.modified;date='2026-12-11';lot='LOT-DONE';wafers=3;capture=96.5;falsePositive=1.2;wph=12;summary='Passed'}}
    if ($completed.data.wafers -ne 5 -or $completed.data.reportStatus -ne 'Ready' -or $completed.data.internalReportArtifactId -ne $created.InternalReportArtifact -or $completed.data.externalReportArtifactId -ne $created.ExternalReportArtifact) { throw 'Optional Test Run writes changed report readiness.' }
    $current = $completed.data
    foreach ($status in @('Internal Review', 'Customer Review', 'Accepted')) {
        $command = @{status=$status}
        if ($status -eq 'Accepted') { $command.customerComment = 'Customer accepted the demo results' }
        $step = Invoke-CrmPost $sessions.Engineer 'rayher_crm.api.v1.evaluations.update_evaluation_status' @{id=$created.Evaluation;command=$command;expectedModified=$current.modified}
        $current = $step.data
    }
    if ($current.testRound -ne 1) { throw 'HTTP Evaluation did not report its test round.' }
    if ($current.acceptance -ne 'Accepted') { throw 'HTTP Evaluation acceptance was not derived.' }
    $opportunityAfterAcceptance = (Invoke-RestMethod -Uri "$BaseUrl/api/method/rayher_crm.api.v1.opportunities.get_strategy_opportunity?id=$([Uri]::EscapeDataString($created.Opportunity))" -WebSession $sessions.Sales).message.data
    if ($opportunityAfterAcceptance.stage -ne $budgetApprovalStage) { throw "Accepted Evaluation did not advance Opportunity to $budgetApprovalStage." }

    $workflow = Invoke-RestMethod -Uri "$BaseUrl/api/method/rayher_crm.api.v1.evaluations.list_demo_workflows" -WebSession $sessions.Sales
    $workflowRow = @($workflow.message.data.items | Where-Object {$_.id -eq $created.Request})[0]
    if (-not $workflowRow -or $workflowRow.evaluation.id -ne $created.Evaluation) { throw 'HTTP workflow projection is missing Evaluation.' }
    if (@($workflowRow.artifacts | Where-Object {$_.id -in @($created.InternalReportArtifact,$created.ExternalReportArtifact) -and $_.type -eq 'Test Report'}).Count -ne 2) { throw 'HTTP workflow Article projection is missing one or both uploaded Test Reports.' }

    & docker compose @composeArgs restart backend frontend queue-short queue-long scheduler websocket | Out-Null
    if ($LASTEXITCODE -ne 0) { throw 'Runtime service restart failed.' }
    $persisted = $null; $deadline = [DateTime]::UtcNow.AddSeconds(90)
    while ([DateTime]::UtcNow -lt $deadline -and -not $persisted) {
        try {
            $afterRestart = Invoke-RestMethod -Uri "$BaseUrl/api/method/rayher_crm.api.v1.evaluations.list_evaluations?accountId=$($created.Account)" -WebSession $sessions.Engineer
            $persisted = @($afterRestart.message.data.items | Where-Object {$_.id -eq $created.Evaluation})[0]
        } catch { Start-Sleep -Seconds 2 }
    }
    if (-not $persisted -or $persisted.acceptance -ne 'Accepted' -or $persisted.wafers -ne 5) { throw 'Stage 5E data did not persist through runtime restart.' }
    Write-Output 'Stage 5E authenticated HTTP acceptance passed: create/update/409/comment/roles/atomic-convert/scope/zero-run-report-upload/optional-test-runs/article-workflow/restart-persistence.'
} finally {
    $adminPassword=$null; $passwords=$null
    if ($created.Request) {
        $args = "['CRM Demo Request',$(ConvertTo-PythonStringLiteral $created.Request),'evaluation',None]"
        & docker compose @composeArgs exec -T backend bench --site $SiteName execute frappe.db.set_value --args $args | Out-Null
    }
    foreach ($artifactId in @($created.InternalReportArtifact, $created.ExternalReportArtifact)) {
        Remove-TestChildren 'File' 'attached_to_name' $artifactId
        Remove-TestChildren 'CRM Demo Artifact' 'name' $artifactId
    }
    Remove-TestChildren 'CRM Notification Event' 'source_name' $created.Evaluation
    Remove-TestChildren 'CRM Notification Event' 'source_name' $created.Request
    foreach ($userId in @($created.Manager, $created.OtherEngineer, $created.Engineer, $created.Sales)) {
        Remove-TestChildren 'CRM Notification Event' 'recipient_user' $userId
    }
    Remove-TestChildren 'CRM Test Run' 'evaluation' $created.Evaluation
    Remove-TestChildren 'CRM Evaluation History' 'evaluation' $created.Evaluation
    Remove-TestChildren 'CRM Evaluation Customer Review' 'evaluation' $created.Evaluation
    Remove-TestDoc 'CRM Evaluation' $created.Evaluation
    Remove-TestChildren 'CRM Demo Comment' 'demo_request' $created.Request
    Remove-TestChildren 'CRM Demo Request History' 'demo_request' $created.Request
    Remove-TestDoc 'CRM Demo Request' $created.Request
    Remove-TestChildren 'CRM Opportunity History' 'opportunity' $created.Opportunity
    Remove-TestDoc 'CRM Opportunity' $created.Opportunity
    Remove-TestDoc 'Contact' $created.Contact
    Remove-TestDoc 'Address' $created.Site
    Remove-TestDoc 'Customer' $created.Account
    Remove-TestDoc 'User' $created.Manager
    Remove-TestDoc 'User' $created.OtherEngineer
    Remove-TestDoc 'User' $created.Engineer
    Remove-TestDoc 'User' $created.Sales
}
