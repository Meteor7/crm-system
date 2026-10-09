param(
    [string]$ProjectName = 'rayher-crm-stage1-tests',
    [string]$SiteName = 'rayher-crm.test',
    [string]$BaseUrl = 'http://127.0.0.1:2225'
)

$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'http-acceptance-values.ps1')
$backendRoot = Split-Path -Parent $PSScriptRoot
$workspaceRoot = Split-Path -Parent $backendRoot
$composeFile = Join-Path $backendRoot 'compose.yaml'
$envFile = Join-Path $backendRoot 'test.env.example'
$envFileName = [IO.Path]::GetFileName($envFile)
if (-not $SiteName.EndsWith('.test') -or $envFileName -ne 'test.env.example') {
    throw "Acceptance requires a dedicated .test site and backend/test.env.example; refused '$SiteName' / '$envFileName'."
}
$sourceDocx = Join-Path $workspaceRoot 'public\templates\demo-request-form-v2.docx'
$composeArgs = @('--project-name', $ProjectName, '--env-file', $envFile, '-f', $composeFile)
$created = [ordered]@{
    Account=$null; Site=$null; Contact=$null; Opportunity=$null; Request=$null; Evaluation=$null; ContactFile=$null; RequestArtifact=$null
    InternalReportArtifact=$null; ExternalReportArtifact=$null; StatusRecord=$null; StatusFile=$null
    Sales=$null; Engineer=$null; OtherSales=$null; Manager=$null; Files=@()
}
$temporaryFiles = @()

function Invoke-CrmPost {
    param($Session, [string]$Method, [hashtable]$Arguments)
    $body = @{}
    foreach ($key in $Arguments.Keys) {
        $value = ConvertTo-CrmHttpFormValue -Value $Arguments[$key]
        $body[$key] = if ($key -in @('input', 'command', 'selection')) { $value | ConvertTo-Json -Compress -Depth 15 } else { $value }
    }
    return (Invoke-RestMethod -Uri "$BaseUrl/api/method/$Method" -Method Post -ContentType 'application/x-www-form-urlencoded; charset=utf-8' -Body $body -WebSession $Session).message
}

function Invoke-MultipartFile {
    param(
        $Session, [string]$Method, [hashtable]$Fields, [string]$FieldName,
        [string]$FilePath, [string]$MimeType
    )
    $boundary = '----------------crmstage5f' + [guid]::NewGuid().ToString('N')
    $stream = New-Object IO.MemoryStream
    try {
        foreach ($key in $Fields.Keys) {
            $part = "--$boundary`r`nContent-Disposition: form-data; name=`"$key`"`r`n`r`n$(ConvertTo-CrmHttpFormValue -Value $Fields[$key])`r`n"
            $bytes = [Text.Encoding]::UTF8.GetBytes($part)
            $stream.Write($bytes, 0, $bytes.Length)
        }
        $fileHeader = "--$boundary`r`nContent-Disposition: form-data; name=`"$FieldName`"; filename=`"$([IO.Path]::GetFileName($FilePath))`"`r`nContent-Type: $MimeType`r`n`r`n"
        $headerBytes = [Text.Encoding]::UTF8.GetBytes($fileHeader)
        $stream.Write($headerBytes, 0, $headerBytes.Length)
        $fileBytes = [IO.File]::ReadAllBytes($FilePath)
        $stream.Write($fileBytes, 0, $fileBytes.Length)
        $tailBytes = [Text.Encoding]::UTF8.GetBytes("`r`n--$boundary--`r`n")
        $stream.Write($tailBytes, 0, $tailBytes.Length)
        return (Invoke-RestMethod -Uri "$BaseUrl/api/method/$Method" -Method Post -Body $stream.ToArray() -ContentType "multipart/form-data; boundary=$boundary" -WebSession $Session).message
    } finally {
        $stream.Dispose()
    }
}

function Invoke-MultipartFiles {
    param($Session, [string]$Method, [hashtable]$Fields, [array]$Files)
    $boundary = '----------------crmstage5f' + [guid]::NewGuid().ToString('N')
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

function Save-Download {
    param($Session, [string]$Method, [string]$IdParameter, [string]$Id)
    $path = [IO.Path]::GetTempFileName()
    $script:temporaryFiles += $path
    Invoke-WebRequest -UseBasicParsing -Uri "$BaseUrl/api/method/$Method`?$IdParameter=$([Uri]::EscapeDataString($Id))" -WebSession $Session -OutFile $path | Out-Null
    return $path
}

function Remember-AttachedFiles {
    param($AdminSession, [string]$AttachedName)
    $filters = ConvertTo-Json -Compress -Depth 4 -InputObject (,@('File','attached_to_name','=',$AttachedName))
    $fields = ConvertTo-Json -Compress -InputObject @('name')
    $uri = "$BaseUrl/api/resource/File?fields=$([Uri]::EscapeDataString($fields))&filters=$([Uri]::EscapeDataString($filters))&limit_page_length=100"
    $rows = (Invoke-RestMethod -Uri $uri -WebSession $AdminSession).data
    foreach ($row in @($rows)) {
        if ($row.name -and $script:created.Files -notcontains $row.name) { $script:created.Files += $row.name }
    }
}

try {
    if (-not (Test-Path -LiteralPath $sourceDocx -PathType Leaf)) { throw 'Verified DOCX fixture is missing.' }
    $adminPassword = (& docker compose @composeArgs run --rm --no-deps --entrypoint cat secrets-init /run/crm-local-secrets/admin_password).Trim()
    if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($adminPassword)) { throw 'Could not read isolated Administrator password.' }
    $adminSession = New-Object Microsoft.PowerShell.Commands.WebRequestSession
    Invoke-RestMethod -Uri "$BaseUrl/api/method/login" -Method Post -Body @{usr='Administrator';pwd=$adminPassword} -WebSession $adminSession | Out-Null

    $stamp = [DateTimeOffset]::UtcNow.ToUnixTimeMilliseconds()
    $passwords = @{
        Sales="Aa1!$([guid]::NewGuid().ToString('N'))"; Engineer="Aa1!$([guid]::NewGuid().ToString('N'))"
        OtherSales="Aa1!$([guid]::NewGuid().ToString('N'))"; Manager="Aa1!$([guid]::NewGuid().ToString('N'))"
    }
    foreach ($spec in @(
        @{Key='Sales'; Email="crm-stage5f-sales-$stamp@example.invalid"; Role='CRM Sales'},
        @{Key='Engineer'; Email="crm-stage5f-engineer-$stamp@example.invalid"; Role='CRM Engineer'},
        @{Key='OtherSales'; Email="crm-stage5f-other-sales-$stamp@example.invalid"; Role='CRM Sales'},
        @{Key='Manager'; Email="crm-stage5f-manager-$stamp@example.invalid"; Role='CRM Manager'}
    )) {
        $json = @{
            email=$spec.Email; first_name="Stage 5F $($spec.Key)"; enabled=1; send_welcome_email=0
            new_password=$passwords[$spec.Key]; roles=@(@{role=$spec.Role})
        } | ConvertTo-Json -Compress -Depth 5
        $response = Invoke-RestMethod -Uri "$BaseUrl/api/resource/User" -Method Post -ContentType 'application/json' -Body $json -WebSession $adminSession
        $created[$spec.Key] = $response.data.name
    }
    $sessions = @{}
    foreach ($key in @('Sales','Engineer','OtherSales','Manager')) {
        $sessions[$key] = New-Object Microsoft.PowerShell.Commands.WebRequestSession
        Invoke-RestMethod -Uri "$BaseUrl/api/method/login" -Method Post -Body @{usr=$created[$key];pwd=$passwords[$key]} -WebSession $sessions[$key] | Out-Null
    }

    $account = Invoke-CrmPost $sessions.Sales 'rayher_crm.api.v1.accounts.create_account' @{input=@{
        name="Stage 5F Account $stamp";shortName="S5F $stamp";segment='Frontend';tier='A';city='Shanghai';region='East China';owner=$created.Sales
    }}
    $created.Account = $account.data.id
    $siteTitle = "Stage 5F Site $stamp"
    $siteJson = @{
        address_title=$siteTitle;address_type='Other';address_line1=$siteTitle;city='Shanghai';country='China'
        custom_crm_owner=$created.Sales;custom_crm_site_type='Fab';custom_crm_process='Frontend';custom_crm_status=(-join ([char[]]@(0x91CF, 0x4EA7)))
        links=@(@{link_doctype='Customer';link_name=$created.Account})
    } | ConvertTo-Json -Compress -Depth 5
    $siteResponse = Invoke-RestMethod -Uri "$BaseUrl/api/resource/Address" -Method Post -ContentType 'application/json; charset=utf-8' -Body ([Text.Encoding]::UTF8.GetBytes($siteJson)) -WebSession $adminSession
    $created.Site = $siteResponse.data.name
    $contact = Invoke-CrmPost $sessions.Sales 'rayher_crm.api.v1.contacts.create_contact' @{input=@{
        accountId=$created.Account;name="Stage 5F Contact $stamp";title='Director';department='Engineering';phone='13800000012'
        email="stage5f-contact-$stamp@example.invalid";relationship='Developing';status='Active';owner=$created.Sales
    }}
    $created.Contact = $contact.data.id

    $qualifiedStage = 'qualified_opportunity'
    $opportunity = Invoke-CrmPost $sessions.Sales 'rayher_crm.api.v1.opportunities.create_strategy_opportunity' @{input=@{probabilityLevel='pipeline';
        accountId=$created.Account;siteId=$created.Site;title="Stage 5F Opportunity $stamp";owner=$created.Sales
        stage=$qualifiedStage;qualificationConfirmed=$true;forecast='Pipeline';amount='300000.00';probability=20;intentScore=85;poDate='2026-12-31'
        toolType='Inspection';saleType='New Equipment';subRegion='East China';currency='CNY';originalAmount='300000.00';amountCny='300000.00'
    }}
    $created.Opportunity = $opportunity.data.id

    $contactUpload = Invoke-MultipartFile $sessions.Sales 'rayher_crm.api.v1.contact_files.upload_files' @{contactId=$created.Contact} 'files' $sourceDocx 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
    $created.ContactFile = $contactUpload.data[0].id
    if ($contactUpload.data[0].uploadedBy -ne $created.Sales) { throw 'Contact File trusted a non-server uploader.' }
    Remember-AttachedFiles $adminSession $created.ContactFile
    $contactDownload = Save-Download $sessions.Sales 'rayher_crm.api.v1.contact_files.download_file' 'fileId' $created.ContactFile
    if ((Get-FileHash -Algorithm SHA256 -LiteralPath $contactDownload).Hash -ne (Get-FileHash -Algorithm SHA256 -LiteralPath $sourceDocx).Hash) { throw 'Contact File raw download bytes changed.' }
    $contactDenied = 0
    try { Save-Download $sessions.OtherSales 'rayher_crm.api.v1.contact_files.download_file' 'fileId' $created.ContactFile | Out-Null } catch { $contactDenied = [int]$_.Exception.Response.StatusCode }
    if ($contactDenied -ne 403) { throw "Expected foreign Contact File HTTP 403, got $contactDenied." }

    # A Status attachment named outside ASCII (#92) keeps its name through a real
    # download: an ASCII fallback plus the UTF-8 filename* form, read back by the
    # RFC 6266 parser in .NET.
    $statusName = (-join [char[]](0x62A5, 0x4EF7, 0x5355)) + ' 2026.docx'
    $statusDirectory = Join-Path ([IO.Path]::GetTempPath()) ('crm-stage5f-' + [guid]::NewGuid().ToString('N'))
    New-Item -ItemType Directory -Path $statusDirectory | Out-Null
    $statusSource = Join-Path $statusDirectory $statusName
    $temporaryFiles += $statusSource
    $temporaryFiles += $statusDirectory
    Copy-Item -LiteralPath $sourceDocx -Destination $statusSource
    $statusInput = ConvertTo-Json -Compress -InputObject @{text='Stage 5F status with a non-ASCII attachment name'}
    $statusRecord = Invoke-MultipartFile $sessions.Sales 'rayher_crm.api.v1.opportunity_status.save_record' @{opportunityId=$created.Opportunity;input=$statusInput} 'files' $statusSource 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
    $created.StatusRecord = $statusRecord.data.id
    $created.StatusFile = $statusRecord.data.files[0].id
    Remember-AttachedFiles $adminSession $created.StatusFile
    if ($statusRecord.data.files[0].fileName -cne $statusName) { throw "Status attachment name changed on upload: $($statusRecord.data.files[0].fileName)" }
    $statusDownload = [IO.Path]::GetTempFileName()
    $temporaryFiles += $statusDownload
    $statusQuery = "opportunityId=$([Uri]::EscapeDataString($created.Opportunity))&recordId=$([Uri]::EscapeDataString($created.StatusRecord))&fileId=$([Uri]::EscapeDataString($created.StatusFile))"
    $statusResponse = Invoke-WebRequest -UseBasicParsing -Uri "$BaseUrl/api/method/rayher_crm.api.v1.opportunity_status.download_file?$statusQuery" -WebSession $sessions.Sales -OutFile $statusDownload -PassThru
    $dispositions = @($statusResponse.Headers['Content-Disposition'])
    $expectedDisposition = "attachment; filename=`"___ 2026.docx`"; filename*=UTF-8''%E6%8A%A5%E4%BB%B7%E5%8D%95%202026.docx"
    if ($dispositions.Count -ne 1 -or $dispositions[0] -cne $expectedDisposition) { throw "Unexpected Status Content-Disposition: $($dispositions -join ' | ')" }
    Add-Type -AssemblyName System.Net.Http
    $savedName = [Net.Http.Headers.ContentDispositionHeaderValue]::Parse($dispositions[0]).FileNameStar
    if ($savedName -cne $statusName) { throw "Status download would be saved as '$savedName'." }
    if ((Get-FileHash -Algorithm SHA256 -LiteralPath $statusDownload).Hash -ne (Get-FileHash -Algorithm SHA256 -LiteralPath $sourceDocx).Hash) { throw 'Status attachment raw download bytes changed.' }

    $formData = @{
        contactPerson='forged';industry='Frontend Fab';salesContact=$created.Sales;demoOwner=$created.Engineer
        sizeShape='300 mm';material='Si(100)';specificRequest='Edge exclusion';detectMeasure='Detect particles';expectedResults='Wafer map'
        otherTools='Tool of record';primaryTool='Inspection 3000';complementaryTool='';timing='2026-12-20'
        keySuccessFactors='Capture above 95%';internalQuestions='Confirm recipe';customerQuestions='Confirm sample readiness'
        wafers=@(@{slotId='1';wid="HTTP-$stamp-W01";waferSpecificity='Si wafer';notchFlat='Notch up';doiMetrologyItems='Particles';resultFileProvided='Wafer map'})
    }
    $request = Invoke-CrmPost $sessions.Sales 'rayher_crm.api.v1.demo_requests.create_demo_request' @{input=@{
        accountId=$created.Account;primaryContactId=$created.Contact;requirementId="REQ-S5F-$stamp";opportunityId=$created.Opportunity;formData=$formData
        customerExpectedDate='2026-12-31';submit=$true
    }}
    $created.Request = $request.data.id
    $opportunityAfterRequest = (Invoke-RestMethod -Uri "$BaseUrl/api/method/rayher_crm.api.v1.opportunities.get_strategy_opportunity?id=$([Uri]::EscapeDataString($created.Opportunity))" -WebSession $sessions.Sales).message.data
    if ($opportunityAfterRequest.stage -ne $qualifiedStage) { throw "Demo Request creation moved the Opportunity to $($opportunityAfterRequest.stage)." }
    $artifactUpload = Invoke-MultipartFile $sessions.Sales 'rayher_crm.api.v1.demo_artifacts.save_artifact' @{
        demoRequestId=$created.Request;type='Demo Request DOCX';visibility='Internal'
    } 'file' $sourceDocx 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
    $created.RequestArtifact = $artifactUpload.data.id
    Remember-AttachedFiles $adminSession $created.RequestArtifact
    $artifactDownload = Save-Download $sessions.Engineer 'rayher_crm.api.v1.demo_artifacts.download_artifact' 'artifactId' $created.RequestArtifact
    if ((Get-FileHash -Algorithm SHA256 -LiteralPath $artifactDownload).Hash -ne (Get-FileHash -Algorithm SHA256 -LiteralPath $sourceDocx).Hash) { throw 'Demo Artifact raw download bytes changed.' }
    $artifactDenied = 0
    try { Save-Download $sessions.OtherSales 'rayher_crm.api.v1.demo_artifacts.download_artifact' 'artifactId' $created.RequestArtifact | Out-Null } catch { $artifactDenied = [int]$_.Exception.Response.StatusCode }
    if ($artifactDenied -ne 403) { throw "Expected foreign Artifact HTTP 403, got $artifactDenied." }

    $engineering = Invoke-CrmPost $sessions.Engineer 'rayher_crm.api.v1.demo_requests.transition_demo_request' @{id=$created.Request;expectedModified=$request.data.modified;command=@{
        type='engineer_approve';engineerOwner=$created.Engineer;testPlan='Particle recipe';assignedEquipment='Inspection 3000'
        resourceWindow='Week 48';estimatedCompletionDate='2026-12-20';technicalRisk='Contamination';comment='Feasible'
    }}
    $approved = Invoke-CrmPost $sessions.Manager 'rayher_crm.api.v1.demo_requests.transition_demo_request' @{id=$created.Request;command=@{type='manager_approve';comment='Approved'};expectedModified=$engineering.data.request.modified}
    $created.Evaluation = $approved.data.evaluation.id
    $current = $approved.data.evaluation
    foreach ($status in @('Scope Confirmed','Sample Received','Scheduled')) {
        $current = (Invoke-CrmPost $sessions.Engineer 'rayher_crm.api.v1.evaluations.update_evaluation_status' @{id=$created.Evaluation;command=@{status=$status};expectedModified=$current.modified}).data
    }
    $current = (Invoke-CrmPost $sessions.Engineer 'rayher_crm.api.v1.evaluations.update_evaluation_status' @{id=$created.Evaluation;command=@{status='Testing'};expectedModified=$current.modified}).data
    if (@($current.runs).Count -ne 0) { throw 'Stage 5F expected zero Test Runs before report upload.' }
    $blockedStatus = 0
    try { Invoke-CrmPost $sessions.Engineer 'rayher_crm.api.v1.evaluations.update_evaluation_status' @{id=$created.Evaluation;command=@{status='Internal Review'};expectedModified=$current.modified} | Out-Null } catch { $blockedStatus = [int]$_.Exception.Response.StatusCode }
    if ($blockedStatus -ne 409) { throw "Expected report upload gate HTTP 409, got $blockedStatus." }
    $internalReportSource = Join-Path ([IO.Path]::GetTempPath()) "crm-stage5f-internal-report-$stamp.csv"
    $externalReportSource = Join-Path ([IO.Path]::GetTempPath()) "crm-stage5f-external-report-$stamp.csv"
    $temporaryFiles += @($internalReportSource, $externalReportSource)
    [IO.File]::WriteAllText($internalReportSource, "metric,value`ncapture,96.5`n", [Text.UTF8Encoding]::new($false))
    [IO.File]::WriteAllText($externalReportSource, "metric,value`ncustomer_capture,96.5`n", [Text.UTF8Encoding]::new($false))
    $released = Invoke-MultipartFiles $sessions.Manager 'rayher_crm.api.v1.evaluations.release_demo_test_report' @{id=$created.Evaluation; expectedRound=1} @(
        @{Name='internalFile';Path=$internalReportSource;MimeType='text/csv'},
        @{Name='externalFile';Path=$externalReportSource;MimeType='text/csv'}
    )
    $created.InternalReportArtifact = $released.data.internalReportArtifact.id
    $created.ExternalReportArtifact = $released.data.externalReportArtifact.id
    if ($released.data.version -ne 1 -or $released.data.internalReportArtifact.fileName -notlike '*internal-report*' -or $released.data.externalReportArtifact.fileName -notlike '*external-report*') { throw 'Uploaded Test Report metadata is incorrect.' }
    Remember-AttachedFiles $adminSession $created.InternalReportArtifact
    Remember-AttachedFiles $adminSession $created.ExternalReportArtifact
    $internalReportDownload = Save-Download $sessions.Sales 'rayher_crm.api.v1.demo_artifacts.download_artifact' 'artifactId' $created.InternalReportArtifact
    $externalReportDownload = Save-Download $sessions.Engineer 'rayher_crm.api.v1.demo_artifacts.download_artifact' 'artifactId' $created.ExternalReportArtifact
    $reportBytes = [IO.File]::ReadAllBytes($internalReportDownload)
    if ((Get-FileHash -Algorithm SHA256 -LiteralPath $internalReportDownload).Hash -ne (Get-FileHash -Algorithm SHA256 -LiteralPath $internalReportSource).Hash) { throw 'Internal Test Report bytes changed.' }
    if ((Get-FileHash -Algorithm SHA256 -LiteralPath $externalReportDownload).Hash -ne (Get-FileHash -Algorithm SHA256 -LiteralPath $externalReportSource).Hash) { throw 'External Test Report bytes changed.' }
    $current = (Invoke-RestMethod -Uri "$BaseUrl/api/method/rayher_crm.api.v1.evaluations.get_evaluation?id=$([Uri]::EscapeDataString($created.Evaluation))" -WebSession $sessions.Engineer).message.data
    if ($current.internalReportArtifactId -ne $created.InternalReportArtifact -or $current.externalReportArtifactId -ne $created.ExternalReportArtifact -or @($current.runs).Count -ne 0) { throw 'Zero-Run Test Report metadata did not persist.' }
    $current = (Invoke-CrmPost $sessions.Engineer 'rayher_crm.api.v1.evaluations.add_evaluation_run' @{id=$created.Evaluation;input=@{
        expectedModified=$current.modified
        date='2026-12-11';lot="LOT-S5F-$stamp";wafers=3;capture=96.5;falsePositive=1.2;wph=12;summary='Optional structured record'
    }}).data
    if ($current.reportStatus -ne 'Ready' -or $current.internalReportArtifactId -ne $created.InternalReportArtifact -or $current.externalReportArtifactId -ne $created.ExternalReportArtifact) { throw 'Optional Test Run changed current report readiness.' }
    foreach ($status in @('Internal Review','Customer Review')) {
        $current = (Invoke-CrmPost $sessions.Engineer 'rayher_crm.api.v1.evaluations.update_evaluation_status' @{id=$created.Evaluation;command=@{status=$status};expectedModified=$current.modified}).data
    }
    $workflow = Invoke-RestMethod -Uri "$BaseUrl/api/method/rayher_crm.api.v1.evaluations.list_demo_workflows" -WebSession $sessions.Sales
    $workflowRow = @($workflow.message.data.items | Where-Object {$_.id -eq $created.Request})[0]
    if (@($workflowRow.artifacts | Where-Object {$_.id -in @($created.RequestArtifact,$created.InternalReportArtifact,$created.ExternalReportArtifact)}).Count -ne 3) { throw 'Article projection is missing Demo Request Form or one of the Test Reports.' }

    $salesNotifications = (Invoke-RestMethod -Uri "$BaseUrl/api/method/rayher_crm.api.v1.notifications.list_notifications?page=1&pageSize=200" -WebSession $sessions.Sales).message
    $expectedReportRoute = "/demo-workflow/$($created.Request)?tab=information"
    $salesRelease = @($salesNotifications.data | Where-Object {$_.category -eq 'Evaluation' -and $_.route -eq $expectedReportRoute -and $_.title -eq 'Test Report uploaded'})[0]
    if (-not $salesRelease -or $salesRelease.recipientId -ne $created.Sales -or $salesRelease.actorId -ne $created.Manager) { throw 'Sales release notification identity is incorrect.' }
    $engineerNotifications = (Invoke-RestMethod -Uri "$BaseUrl/api/method/rayher_crm.api.v1.notifications.list_notifications?page=1&pageSize=200" -WebSession $sessions.Engineer).message
    $engineerRelease = @($engineerNotifications.data | Where-Object {$_.category -eq 'Evaluation' -and $_.route -eq $expectedReportRoute -and $_.title -eq 'Test Report uploaded'})[0]
    if (-not $engineerRelease -or $engineerRelease.recipientId -ne $created.Engineer -or $engineerRelease.actorId -ne $created.Manager) { throw 'Engineer release notification identity is incorrect.' }
    if (@($engineerNotifications.data | Where-Object {$_.id -eq $salesRelease.id}).Count -ne 0) { throw 'Engineer could read Sales notification ID.' }
    $salesWorkflow = (Invoke-RestMethod -Uri "$BaseUrl/api/method/rayher_crm.api.v1.evaluations.get_demo_workflow?id=$([Uri]::EscapeDataString($created.Request))" -WebSession $sessions.Sales).message.data
    $engineerWorkflow = (Invoke-RestMethod -Uri "$BaseUrl/api/method/rayher_crm.api.v1.evaluations.get_demo_workflow?id=$([Uri]::EscapeDataString($created.Request))" -WebSession $sessions.Engineer).message.data
    if ($salesWorkflow.evaluation.id -ne $created.Evaluation -or $engineerWorkflow.evaluation.id -ne $created.Evaluation) { throw 'A report notification recipient could not open the routed workflow.' }
    $markDenied = 0
    try { Invoke-CrmPost $sessions.OtherSales 'rayher_crm.api.v1.notifications.mark_notification_read' @{id=$salesRelease.id} | Out-Null } catch { $markDenied = [int]$_.Exception.Response.StatusCode }
    if ($markDenied -ne 404) { throw "Expected foreign notification HTTP 404, got $markDenied." }
    $marked = Invoke-CrmPost $sessions.Sales 'rayher_crm.api.v1.notifications.mark_notification_read' @{id=$salesRelease.id}
    if (-not $marked.data.read -or -not (ConvertTo-CrmHttpFormValue -Value $marked.data.readAt).EndsWith('Z')) { throw 'Notification mark-read did not return ISO server state.' }
    $markAll = Invoke-CrmPost $sessions.Engineer 'rayher_crm.api.v1.notifications.mark_all_notifications_read' @{}
    if (-not (ConvertTo-CrmHttpFormValue -Value $markAll.data.readAt).EndsWith('Z')) { throw 'Notification mark-all did not return ISO server time.' }
    $managerNotifications = (Invoke-RestMethod -Uri "$BaseUrl/api/method/rayher_crm.api.v1.notifications.list_notifications?page=1&pageSize=200" -WebSession $sessions.Manager).message
    if (@($managerNotifications.data | Where-Object {$_.id -eq $salesRelease.id}).Count -ne 0) { throw 'Manager wildcarded into a recipient notification.' }

    # List only this run's fixtures. Service-backed Contact files keep scope-based
    # access; ordinary private CRM parent attachments and Demo artifacts stay hidden.
    foreach ($parent in @(@{Type='Customer';Name=$created.Account}, @{Type='Contact';Name=$created.Contact}, @{Type='Address';Name=$created.Site})) {
        $body = @{file_name="native-$($parent.Type)-$stamp.txt";content="private $($parent.Type) $stamp";is_private=1;attached_to_doctype=$parent.Type;attached_to_name=$parent.Name} | ConvertTo-Json -Compress
        $file = (Invoke-RestMethod -Uri "$BaseUrl/api/resource/File" -Method Post -ContentType 'application/json' -Body $body -WebSession $adminSession).data
        $created.Files += $file.name
    }
    $nativeFileFields = [Uri]::EscapeDataString((ConvertTo-Json -Compress -InputObject @('name','file_name','file_url','attached_to_doctype','attached_to_name')))
    $nativeFileFilters = [Uri]::EscapeDataString((ConvertTo-Json -Compress -Depth 5 -InputObject @{name=@('in',@($created.Files))}))
    $nativeFileUri = "$BaseUrl/api/resource/File?fields=$nativeFileFields&filters=$nativeFileFilters&limit_page_length=1000"
    $nativeUserFields = [Uri]::EscapeDataString((ConvertTo-Json -Compress -InputObject @('name','last_ip','last_login')))
    $adminFiles = @((Invoke-RestMethod -Uri $nativeFileUri -WebSession $adminSession).data)
    if ($adminFiles.Count -ne $created.Files.Count) { throw 'Administrator no longer lists all fixture files.' }
    $contactNative = @($adminFiles | Where-Object { $_.attached_to_doctype -eq 'CRM Contact File' -and $_.attached_to_name -eq $created.ContactFile })
    if ($contactNative.Count -ne 1) { throw 'Expected one service-backed Contact file.' }
    $nativeDownloadPath = [IO.Path]::GetTempFileName(); $temporaryFiles += $nativeDownloadPath
    Invoke-WebRequest -Uri ($BaseUrl + $contactNative[0].file_url) -WebSession $sessions.Sales -OutFile $nativeDownloadPath | Out-Null
    if ((Get-FileHash $nativeDownloadPath).Hash -ne (Get-FileHash $contactDownload).Hash) { throw 'Authorized native Contact download differs from CRM delivery.' }
    foreach ($key in @('OtherSales','Engineer','Sales','Manager')) {
        $nativeFiles = @((Invoke-RestMethod -Uri $nativeFileUri -WebSession $sessions[$key]).data)
        $expectedNames = if ($key -in @('Sales','Manager')) { @($contactNative[0].name) } else { @() }
        if (@(Compare-Object (@('sentinel') + @($nativeFiles | ForEach-Object { $_.name })) (@('sentinel') + $expectedNames)).Count -ne 0) { throw "Unexpected native File visibility for $key." }
        $nativeUsers = @((Invoke-RestMethod -Uri "$BaseUrl/api/resource/User?fields=$nativeUserFields&limit_page_length=1000" -WebSession $sessions[$key]).data)
        if ($key -eq 'Manager') {
            if (@($nativeUsers | Where-Object { $_.name -eq $created.Engineer }).Count -ne 1) { throw 'The native User list no longer shows a Manager the Engineer to assign.' }
        } else {
            if ($nativeUsers.Count -ne 1 -or $nativeUsers[0].name -ne $created[$key]) { throw "The native User list showed $key more than their own row." }
            $nativeCount = (Invoke-RestMethod -Uri "$BaseUrl/api/method/frappe.client.get_count?doctype=User" -WebSession $sessions[$key]).message
            if ($nativeCount -ne 1) { throw "Native User count leaks other rows to $key." }
            $otherUserFilter = [Uri]::EscapeDataString((ConvertTo-Json -Compress -InputObject @{name=$created.Manager}))
            $otherUserValue = (Invoke-RestMethod -Uri "$BaseUrl/api/method/frappe.client.get_value?doctype=User&fieldname=last_ip&filters=$otherUserFilter" -WebSession $sessions[$key]).message
            if ($otherUserValue -and $otherUserValue.PSObject.Properties.Count -gt 0) { throw "Native User get_value leaks the Manager row to $key." }
        }
    }

    # Transfer through the actual business API: the former uploader must lose
    # both the native metadata row and native bytes, then recover after transfer back.
    $accountInput = @{name=$account.data.name;shortName=$account.data.shortName;segment=$account.data.segment;tier=$account.data.tier;city=$account.data.city;region=$account.data.region;owner=$created.OtherSales;visibility='Private'}
    $transferred = Invoke-CrmPost $sessions.Manager 'rayher_crm.api.v1.accounts.update_account' @{id=$created.Account;input=$accountInput;expectedModified=$account.data.modified}
    $revokedFiles = @((Invoke-RestMethod -Uri $nativeFileUri -WebSession $sessions.Sales).data)
    if ($revokedFiles.Count -ne 0) { throw 'The former uploader still lists Contact metadata after transfer.' }
    $revokedPath = [IO.Path]::GetTempFileName(); $temporaryFiles += $revokedPath
    $revokedStatus = 0
    try { Invoke-WebRequest -Uri ($BaseUrl + $contactNative[0].file_url) -WebSession $sessions.Sales -OutFile $revokedPath | Out-Null } catch { $revokedStatus = [int]$_.Exception.Response.StatusCode }
    if ($revokedStatus -ne 403) { throw "Expected revoked native Contact download HTTP 403, got $revokedStatus." }
    $accountInput.owner = $created.Sales
    Invoke-CrmPost $sessions.Manager 'rayher_crm.api.v1.accounts.update_account' @{id=$created.Account;input=$accountInput;expectedModified=$transferred.data.modified} | Out-Null
    $restoredFiles = @((Invoke-RestMethod -Uri $nativeFileUri -WebSession $sessions.Sales).data)
    if ($restoredFiles.Count -ne 1 -or $restoredFiles[0].name -ne $contactNative[0].name) { throw 'Authorized Contact visibility did not recover after transfer back.' }

    & docker compose @composeArgs restart backend | Out-Null
    if ($LASTEXITCODE -ne 0) { throw 'Backend restart failed.' }
    $persisted = $null; $deadline = [DateTime]::UtcNow.AddSeconds(90)
    while ([DateTime]::UtcNow -lt $deadline -and -not $persisted) {
        try {
            $page = (Invoke-RestMethod -Uri "$BaseUrl/api/method/rayher_crm.api.v1.notifications.list_notifications?page=1&pageSize=200" -WebSession $sessions.Sales).message
            $persisted = @($page.data | Where-Object {$_.id -eq $salesRelease.id})[0]
        } catch { Start-Sleep -Seconds 2 }
    }
    if (-not $persisted -or -not $persisted.read) { throw 'Notification did not persist through backend restart.' }
    $reportAfterRestart = Save-Download $sessions.Sales 'rayher_crm.api.v1.demo_artifacts.download_artifact' 'artifactId' $created.InternalReportArtifact
    if ((Get-Item -LiteralPath $reportAfterRestart).Length -ne $reportBytes.Length) { throw 'Report Artifact did not persist through backend restart.' }

    Invoke-CrmPost $sessions.Sales 'rayher_crm.api.v1.contact_files.delete_file' @{fileId=$created.ContactFile} | Out-Null
    $deletedStatus = 0
    try { Save-Download $sessions.Sales 'rayher_crm.api.v1.contact_files.download_file' 'fileId' $created.ContactFile | Out-Null } catch { $deletedStatus = [int]$_.Exception.Response.StatusCode }
    if ($deletedStatus -ne 404) { throw "Expected deleted Contact File HTTP 404, got $deletedStatus." }
    Write-Output 'Stage 5F authenticated HTTP acceptance passed: multipart/private raw download/non-ASCII download name/IDOR/arbitrary Test Report/Article projection/recipient notifications/read state/native File and User lists/restart persistence.'
} finally {
    $adminPassword=$null; $passwords=$null
    foreach ($path in @($temporaryFiles)) {
        if ($path -and (Test-Path -LiteralPath $path)) {
            $resolved = [IO.Path]::GetFullPath($path)
            $tempRoot = [IO.Path]::GetFullPath([IO.Path]::GetTempPath())
            if (-not $resolved.StartsWith($tempRoot, [StringComparison]::OrdinalIgnoreCase)) { throw "Refusing to remove non-temp path: $resolved" }
            Remove-Item -LiteralPath $resolved -Force
        }
    }
    Remove-TestChildren 'CRM File Access Audit' 'entity_id' $created.ContactFile
    Remove-TestChildren 'CRM File Access Audit' 'entity_id' $created.RequestArtifact
    Remove-TestChildren 'CRM File Access Audit' 'entity_id' $created.InternalReportArtifact
    Remove-TestChildren 'CRM File Access Audit' 'entity_id' $created.ExternalReportArtifact
    Remove-TestChildren 'CRM Contact File' 'name' $created.ContactFile
    Remove-TestChildren 'CRM File Access Audit' 'entity_id' $created.StatusFile
    Remove-TestChildren 'CRM Status Attachment' 'status' $created.StatusRecord
    Remove-TestChildren 'CRM Opportunity Status' 'name' $created.StatusRecord
    Remove-TestChildren 'CRM Demo Artifact' 'demo_request' $created.Request
    foreach ($fileName in @($created.Files)) { Remove-TestDoc 'File' $fileName }
    Remove-TestChildren 'CRM Notification Event' 'source_name' $created.Evaluation
    Remove-TestChildren 'CRM Notification Event' 'source_name' $created.Request
    foreach ($userId in @($created.Manager, $created.OtherSales, $created.Engineer, $created.Sales)) {
        Remove-TestChildren 'CRM Notification Event' 'recipient_user' $userId
    }
    if ($created.Request) {
        $args = "['CRM Demo Request',$(ConvertTo-PythonStringLiteral $created.Request),'evaluation',None]"
        & docker compose @composeArgs exec -T backend bench --site $SiteName execute frappe.db.set_value --args $args | Out-Null
    }
    Remove-TestChildren 'CRM Test Run' 'evaluation' $created.Evaluation
    Remove-TestChildren 'CRM Evaluation History' 'evaluation' $created.Evaluation
    Remove-TestDoc 'CRM Evaluation' $created.Evaluation
    Remove-TestChildren 'CRM Demo Comment' 'demo_request' $created.Request
    Remove-TestChildren 'CRM Demo Request History' 'demo_request' $created.Request
    Remove-TestDoc 'CRM Demo Request' $created.Request
    foreach ($docType in @('CRM Opportunity History', 'CRM Opportunity Stage History', 'CRM Opportunity Probability History', 'CRM Opportunity Internal Validation')) {
        Remove-TestChildren $docType 'opportunity' $created.Opportunity
    }
    Remove-TestDoc 'CRM Opportunity' $created.Opportunity
    Remove-TestDoc 'Contact' $created.Contact
    Remove-TestDoc 'Address' $created.Site
    Remove-TestDoc 'Customer' $created.Account
    Remove-TestDoc 'User' $created.Manager
    Remove-TestDoc 'User' $created.OtherSales
    Remove-TestDoc 'User' $created.Engineer
    Remove-TestDoc 'User' $created.Sales
}
