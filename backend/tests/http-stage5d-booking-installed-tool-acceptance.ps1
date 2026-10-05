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
$created = [ordered]@{ Tool=$null; Booking=$null; Opportunity=$null; Contact=$null; Site=$null; Account=$null; Sales=$null; Engineer=$null; OtherEngineer=$null }

function Invoke-CrmPost {
    param($Session, [string]$Method, [hashtable]$Arguments)
    $body = @{}
    foreach ($key in $Arguments.Keys) {
        $value = ConvertTo-CrmHttpFormValue -Value $Arguments[$key]
        $body[$key] = if ($key -eq 'input') { $value | ConvertTo-Json -Compress -Depth 10 } else { $value }
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

function Remove-OpportunityHistory {
    param([string]$OpportunityId)
    if ([string]::IsNullOrWhiteSpace($OpportunityId)) { return }
    foreach ($docType in @('CRM Opportunity History', 'CRM Opportunity Stage History', 'CRM Opportunity Probability History', 'CRM Opportunity Internal Validation')) {
        $pythonArgs = "[$(ConvertTo-PythonStringLiteral $docType),{'opportunity':$(ConvertTo-PythonStringLiteral $OpportunityId)}]"
        & docker compose @composeArgs exec -T backend bench --site $SiteName execute frappe.db.delete --args $pythonArgs | Out-Null
        if ($LASTEXITCODE -ne 0) { throw "Cleanup failed for $docType." }
    }
}

function Remove-InstalledToolHistory {
    param([string]$InstalledToolId)
    if ([string]::IsNullOrWhiteSpace($InstalledToolId)) { return }
    $pythonArgs = "[$(ConvertTo-PythonStringLiteral $InstalledToolId)]"
    & docker compose @composeArgs exec -T backend bench --site $SiteName execute rayher_crm.tests._opportunity_fixtures.cleanup_installed_tool_trace_fixture --args $pythonArgs | Out-Null
    if ($LASTEXITCODE -ne 0) { throw 'Cleanup failed for Installed Tool trace records.' }
}

try {
    $adminPassword = (& docker compose @composeArgs run --rm --no-deps --entrypoint cat secrets-init /run/crm-local-secrets/admin_password).Trim()
    if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($adminPassword)) { throw 'Could not read isolated Administrator password.' }
    $adminSession = New-Object Microsoft.PowerShell.Commands.WebRequestSession
    Invoke-RestMethod -Uri "$BaseUrl/api/method/login" -Method Post -Body @{usr='Administrator';pwd=$adminPassword} -WebSession $adminSession | Out-Null

    $stamp = [DateTimeOffset]::UtcNow.ToUnixTimeMilliseconds()
    $salesPassword = "Aa1!$([guid]::NewGuid().ToString('N'))"
    $engineerPassword = "Aa1!$([guid]::NewGuid().ToString('N'))"
    $otherEngineerPassword = "Aa1!$([guid]::NewGuid().ToString('N'))"
    foreach ($spec in @(
        @{Key='Sales'; Email="crm-stage5d-sales-$stamp@example.invalid"; Role='CRM Sales'; Password=$salesPassword},
        @{Key='Engineer'; Email="crm-stage5d-engineer-$stamp@example.invalid"; Role='CRM Engineer'; Password=$engineerPassword},
        @{Key='OtherEngineer'; Email="crm-stage5d-other-engineer-$stamp@example.invalid"; Role='CRM Engineer'; Password=$otherEngineerPassword}
    )) {
        $json = @{email=$spec.Email;first_name="Stage 5D $($spec.Key)";enabled=1;send_welcome_email=0;new_password=$spec.Password;roles=@(@{role=$spec.Role})} | ConvertTo-Json -Compress -Depth 5
        $response = Invoke-RestMethod -Uri "$BaseUrl/api/resource/User" -Method Post -ContentType 'application/json' -Body $json -WebSession $adminSession
        $created[$spec.Key] = $response.data.name
    }

    $salesSession = New-Object Microsoft.PowerShell.Commands.WebRequestSession
    Invoke-RestMethod -Uri "$BaseUrl/api/method/login" -Method Post -Body @{usr=$created.Sales;pwd=$salesPassword} -WebSession $salesSession | Out-Null
    $engineerSession = New-Object Microsoft.PowerShell.Commands.WebRequestSession
    Invoke-RestMethod -Uri "$BaseUrl/api/method/login" -Method Post -Body @{usr=$created.Engineer;pwd=$engineerPassword} -WebSession $engineerSession | Out-Null
    $otherEngineerSession = New-Object Microsoft.PowerShell.Commands.WebRequestSession
    Invoke-RestMethod -Uri "$BaseUrl/api/method/login" -Method Post -Body @{usr=$created.OtherEngineer;pwd=$otherEngineerPassword} -WebSession $otherEngineerSession | Out-Null

    $account = Invoke-CrmPost $salesSession 'rayher_crm.api.v1.accounts.create_account' @{input=@{name="Stage 5D Account $stamp";shortName="S5D $stamp";segment='Frontend';tier='A';city='Shanghai';region='East China';owner=$created.Sales}}
    $created.Account = $account.data.id
    $productionStatus = [string]::Concat([char]0x91CF, [char]0x4EA7)
    $siteTitle = "Stage 5D Site $stamp"
    $siteJson = @{address_title=$siteTitle;address_type='Other';address_line1=$siteTitle;city='Shanghai';country='China';custom_crm_owner=$created.Sales;custom_crm_site_type='Fab';custom_crm_process='Frontend';custom_crm_status=$productionStatus;links=@(@{link_doctype='Customer';link_name=$created.Account})} | ConvertTo-Json -Compress -Depth 5
    $siteBytes = [Text.Encoding]::UTF8.GetBytes($siteJson)
    $site = Invoke-RestMethod -Uri "$BaseUrl/api/resource/Address" -Method Post -ContentType 'application/json; charset=utf-8' -Body $siteBytes -WebSession $adminSession
    $created.Site = $site.data.name

    $contact = Invoke-CrmPost $salesSession 'rayher_crm.api.v1.contacts.create_contact' @{input=@{accountId=$created.Account;siteId=$created.Site;name="Stage 5D Contact $stamp";title='Director';department='Engineering';phone='13800000010';email="stage5d-contact-$stamp@example.invalid";relationship='Developing';status='Active';owner=$created.Sales}}
    $created.Contact = $contact.data.id
    $opportunity = Invoke-CrmPost $salesSession 'rayher_crm.api.v1.opportunities.create_strategy_opportunity' @{input=@{probabilityLevel='pipeline';accountId=$created.Account;siteId=$created.Site;title="Stage 5D Opportunity $stamp";owner=$created.Sales;stage='qualified_opportunity';qualificationConfirmed=$true;forecast='Pipeline';amount='300000.00';probability=20;intentScore=90;poDate='2026-12-31';toolType='Inspection';saleType='New Equipment';subRegion='East China';currency='CNY';originalAmount='300000.00';amountCny='300000.00'}}
    $created.Opportunity = $opportunity.data.id
    $fixtureArgs = "[$(ConvertTo-PythonStringLiteral $created.Opportunity),'quotation_sent']"
    & docker compose @composeArgs exec -T backend bench --site $SiteName execute rayher_crm.tests._opportunity_fixtures.advance_opportunity_fixture_by_id --args $fixtureArgs | Out-Null
    if ($LASTEXITCODE -ne 0) { throw 'Dedicated test fixture could not prepare the quotation_sent Opportunity.' }

    $bookingDraft = @{primaryContactId=$created.Contact;equipment='Inspection 5000';quantity=1;ddl='2027-01-31';amount='300000.00';currency='CNY';owner=$created.Sales;note='HTTP acceptance'}
    $manualInput = $bookingDraft.Clone(); $manualInput.accountId = $created.Account; $manualInput.status = 'Confirmed'; $manualInput.source = 'Opportunity'; $manualInput.sourceOpportunityId = $created.Opportunity
    $sourceStatus = 0
    try { Invoke-CrmPost $salesSession 'rayher_crm.api.v1.bookings.create_booking' @{input=$manualInput} | Out-Null } catch { $sourceStatus = [int]$_.Exception.Response.StatusCode }
    if ($sourceStatus -ne 409) { throw "Expected manual Opportunity Booking HTTP 409, got $sourceStatus." }

    $quoted = (Invoke-RestMethod -Uri "$BaseUrl/api/method/rayher_crm.api.v1.opportunities.get_strategy_opportunity?id=$([Uri]::EscapeDataString($created.Opportunity))" -WebSession $salesSession).message.data
    if ($quoted.stage -ne 'quotation_sent') { throw "Fixture left the Opportunity at $($quoted.stage) instead of quotation_sent." }
    $confirmed = Invoke-CrmPost $salesSession 'rayher_crm.api.v1.opportunities.confirm_po' @{id=$created.Opportunity;input=@{booking=$bookingDraft;actualPoDate=(Get-Date).AddDays(-1).ToString('yyyy-MM-dd')};expectedModified=$quoted.modified}
    $created.Booking = $confirmed.data.liveBooking.id
    if ($confirmed.data.stage -ne 'po_received' -or -not $created.Booking -or $confirmed.data.liveBooking.status -ne 'Confirmed') { throw 'HTTP PO confirmation did not create a Confirmed Opportunity Booking.' }
    $booking = (Invoke-RestMethod -Uri "$BaseUrl/api/method/rayher_crm.api.v1.bookings.get_booking?id=$([Uri]::EscapeDataString($created.Booking))" -WebSession $salesSession).message
    if ($booking.data.source -ne 'Opportunity' -or $booking.data.sourceOpportunityId -ne $created.Opportunity) { throw 'PO Booking did not keep its Opportunity source.' }
    $staleModified = $booking.data.modified
    $updated = Invoke-CrmPost $salesSession 'rayher_crm.api.v1.bookings.update_booking' @{id=$created.Booking;input=@{note='Updated over HTTP'};expectedModified=$staleModified}
    $conflictStatus = 0
    try { Invoke-CrmPost $salesSession 'rayher_crm.api.v1.bookings.update_booking' @{id=$created.Booking;input=@{note='stale'};expectedModified=$staleModified} | Out-Null } catch { $conflictStatus = [int]$_.Exception.Response.StatusCode }
    if ($conflictStatus -ne 409) { throw "Expected Booking stale HTTP 409, got $conflictStatus." }
    $statusChangeStatus = 0
    try { Invoke-CrmPost $salesSession 'rayher_crm.api.v1.bookings.update_booking' @{id=$created.Booking;input=@{status='Pending'};expectedModified=$updated.data.modified} | Out-Null } catch { $statusChangeStatus = [int]$_.Exception.Response.StatusCode }
    if ($statusChangeStatus -ne 409) { throw "Expected Opportunity Booking status change HTTP 409, got $statusChangeStatus." }

    $serial = "HTTP-SERIAL-$stamp"
    $converted = Invoke-CrmPost $salesSession 'rayher_crm.api.v1.installed_tools.convert_booking_to_installed_tool' @{id=$created.Booking;input=@{siteId=$created.Site;engineerOwner=$created.Engineer;serial=$serial;model='Model X';location='Fab 1';salesOrder='SO-REF';contract='CT-REF';software='1.0';firmware='2.0';configuration='Standard'};expectedModified=$updated.data.modified}
    $created.Tool = $converted.data.installedTool.id
    if ($converted.data.booking.status -ne 'Completed') { throw 'Booking was not Completed by HTTP conversion.' }
    $repeatStatus = 0
    try { Invoke-CrmPost $salesSession 'rayher_crm.api.v1.installed_tools.convert_booking_to_installed_tool' @{id=$created.Booking;input=@{siteId=$created.Site;engineerOwner=$created.Engineer;serial="OTHER-$stamp";model='Model X'};expectedModified=$converted.data.booking.modified} | Out-Null } catch { $repeatStatus = [int]$_.Exception.Response.StatusCode }
    if ($repeatStatus -ne 409) { throw "Expected repeated conversion HTTP 409, got $repeatStatus." }

    $engineerList = Invoke-RestMethod -Uri "$BaseUrl/api/method/rayher_crm.api.v1.installed_tools.list_installed_tools" -WebSession $engineerSession
    $tool = @($engineerList.message.data.items | Where-Object {$_.id -eq $created.Tool})[0]
    if (-not $tool) { throw 'Assigned Engineer could not list Installed Tool.' }
    $milestones = @($tool.milestones)
    if (($milestones.label -join ',') -ne 'FAT,Shipment,Installation,SAT,Warranty') { throw 'Installed Tool milestones are not in board order.' }
    $boardStage = @($milestones | Where-Object {$_.state -eq 'Current'})[0]
    if (-not $boardStage) { $boardStage = @($milestones | Where-Object {$_.state -eq 'Waiting'})[0] }
    if (-not $boardStage) { $boardStage = $milestones[-1] }
    $completedMilestones = @($milestones | Where-Object {$_.state -eq 'Done'}).Count
    if ($boardStage.label -ne 'FAT' -or $completedMilestones -ne 0) { throw 'Installed Tool board stage/progress projection is incorrect.' }
    $toolInput = @{siteId=$tool.siteId;serial=$tool.serial;model=$tool.model;location=$tool.location;engineerOwner=$tool.engineerOwner;operatingSystem=$tool.operatingSystem;warrantyStart=$tool.warrantyStart;warrantyEnd=$tool.warrantyEnd;serviceContract=$tool.serviceContract;pmCycle=$tool.pmCycle;ownershipType=$tool.ownershipType;salesOrder=$tool.salesOrder;contract=$tool.contract}
    $engineerUpdated = Invoke-CrmPost $engineerSession 'rayher_crm.api.v1.installed_tools.update_installed_tool' @{id=$created.Tool;input=$toolInput;expectedModified=$tool.modified}
    # F1-02: the Engineer, not assigned to the Account, reads the Account's Sites with the Tool, and the Account 360 not at all.
    $engineerTool = (Invoke-RestMethod -Uri "$BaseUrl/api/method/rayher_crm.api.v1.installed_tools.get_installed_tool?id=$([Uri]::EscapeDataString($created.Tool))" -WebSession $engineerSession).message.data
    if ($created.Site -notin @($engineerTool.sites | ForEach-Object { $_.id })) { throw 'Engineer did not receive the Account Sites with the Installed Tool.' }
    $account360Status = 0
    try { Invoke-RestMethod -Uri "$BaseUrl/api/method/rayher_crm.api.v1.accounts.get_account_360?id=$([Uri]::EscapeDataString($created.Account))" -WebSession $engineerSession | Out-Null } catch { $account360Status = [int]$_.Exception.Response.StatusCode }
    if ($account360Status -ne 404) { throw "Expected the Engineer's hidden Account 360 to answer HTTP 404, got $account360Status." }
    $reassignInput = $toolInput.Clone(); $reassignInput.engineerOwner = $created.OtherEngineer
    $reassignStatus = 0
    try { Invoke-CrmPost $engineerSession 'rayher_crm.api.v1.installed_tools.update_installed_tool' @{id=$created.Tool;input=$reassignInput;expectedModified=$engineerUpdated.data.modified} | Out-Null } catch { $reassignStatus = [int]$_.Exception.Response.StatusCode }
    if ($reassignStatus -ne 403) { throw "Expected Engineer reassign HTTP 403, got $reassignStatus." }
    $managerReassigned = Invoke-CrmPost $adminSession 'rayher_crm.api.v1.installed_tools.update_installed_tool' @{id=$created.Tool;input=$reassignInput;expectedModified=$engineerUpdated.data.modified}
    if ($managerReassigned.data.engineerOwner -ne $created.OtherEngineer) { throw 'Manager reassignment did not persist.' }

    $salesLifecycleStatus = 0
    try {
        Invoke-CrmPost $salesSession 'rayher_crm.api.v1.installed_tools.transition_installed_tool' @{id=$created.Tool;input=@{completedAt='2026-08-12';result='Passed';openIssues='None';customerSignoff='Signed';comment='Sales must not operate';evidence=@()};expectedModified=$managerReassigned.data.modified} | Out-Null
    } catch { $salesLifecycleStatus = [int]$_.Exception.Response.StatusCode }
    if ($salesLifecycleStatus -ne 403) { throw "Expected Sales lifecycle operation HTTP 403, got $salesLifecycleStatus." }

    $transitioned = Invoke-CrmPost $otherEngineerSession 'rayher_crm.api.v1.installed_tools.transition_installed_tool' @{id=$created.Tool;input=@{completedAt='2026-08-12';result='Passed';openIssues='None';customerSignoff='Signed';comment='FAT completed over HTTP';evidence=@('fat-http.pdf')};expectedModified=$managerReassigned.data.modified}
    if ($transitioned.data.lifecycleStage -ne 'Shipment' -or $transitioned.data.lifecycleHistory[0].fromStage -ne 'FAT') { throw 'Lifecycle transition or history was not persisted.' }

    $versioned = Invoke-CrmPost $otherEngineerSession 'rayher_crm.api.v1.installed_tools.add_installed_tool_version_record' @{id=$created.Tool;input=@{changeDate='2026-08-13';changeType='Software';toValue='1.1';reason='HTTP acceptance';comment='Approved'};expectedModified=$transitioned.data.modified}
    if ($versioned.data.software -ne '1.1' -or $versioned.data.versionHistory[0].fromValue -ne '1.0') { throw 'Version snapshot or history was not persisted.' }

    $serviced = Invoke-CrmPost $otherEngineerSession 'rayher_crm.api.v1.installed_tools.add_installed_tool_service_record' @{id=$created.Tool;input=@{serviceDate='2026-08-14';serviceType='Warranty Activation';result='Activated';openIssues='None';nextAction='Review after one month';actionOwner=$created.OtherEngineer;due='2026-09-14';warrantyStart='2026-08-14';warrantyEnd='2027-08-13';serviceContract='SC-HTTP';pmCycle='6 months';comment='HTTP acceptance'};expectedModified=$versioned.data.modified}
    if ($serviced.data.lastService -ne '2026-08-14' -or $serviced.data.serviceHistory[0].actionOwner -ne $created.OtherEngineer) { throw 'Service snapshot or history was not persisted.' }

    & docker compose @composeArgs restart backend frontend queue-short queue-long scheduler websocket | Out-Null
    if ($LASTEXITCODE -ne 0) { throw 'Runtime service restart failed.' }
    $persisted = $null; $deadline = [DateTime]::UtcNow.AddSeconds(90)
    while ([DateTime]::UtcNow -lt $deadline -and -not $persisted) {
        try {
            $afterRestart = Invoke-RestMethod -Uri "$BaseUrl/api/method/rayher_crm.api.v1.installed_tools.list_installed_tools" -WebSession $otherEngineerSession
            $persisted = @($afterRestart.message.data.items | Where-Object {$_.id -eq $created.Tool})[0]
        } catch { Start-Sleep -Seconds 2 }
    }
    if (-not $persisted -or $persisted.engineerOwner -ne $created.OtherEngineer) { throw 'Reassigned Tool did not persist through runtime restart.' }
    Write-Output 'Stage 5D authenticated HTTP acceptance passed: po-confirmation-booking/manual-source-409/stale-409/status-409/convert/repeat/scope/reassign/lifecycle/version/service/audit/restart-persistence.'
} finally {
    $adminPassword=$null; $salesPassword=$null; $engineerPassword=$null; $otherEngineerPassword=$null
    if ($created.Booking) {
        $args = "['CRM Booking',$(ConvertTo-PythonStringLiteral $created.Booking),'installed_tool',None]"
        & docker compose @composeArgs exec -T backend bench --site $SiteName execute frappe.db.set_value --args $args | Out-Null
    }
    Remove-InstalledToolHistory $created.Tool
    Remove-TestDoc 'CRM Installed Tool' $created.Tool
    Remove-TestDoc 'CRM Booking' $created.Booking
    Remove-OpportunityHistory $created.Opportunity
    Remove-TestDoc 'CRM Opportunity' $created.Opportunity
    Remove-TestDoc 'Contact' $created.Contact
    Remove-TestDoc 'Address' $created.Site
    Remove-TestDoc 'Customer' $created.Account
    Remove-TestDoc 'User' $created.OtherEngineer
    Remove-TestDoc 'User' $created.Engineer
    Remove-TestDoc 'User' $created.Sales
}
