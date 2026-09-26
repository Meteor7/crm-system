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
    Notifications = @()
    Visit = $null
    Stakeholder = $null
    Opportunity = $null
    Contact = $null
    Site = $null
    Account = $null
    SalesUser = $null
    ActionSalesUser = $null
    ManagerUser = $null
}

function Invoke-CrmPost {
    param($Session, [string]$Method, [hashtable]$Arguments)
    $body = @{}
    foreach ($key in $Arguments.Keys) {
        $value = ConvertTo-CrmHttpFormValue -Value $Arguments[$key]
        $body[$key] = if ($key -in @('input', 'command')) {
            $value | ConvertTo-Json -Compress -Depth 10
        } else { $value }
    }
    $response = Invoke-RestMethod -Uri "$BaseUrl/api/method/$Method" -Method Post -ContentType 'application/x-www-form-urlencoded; charset=utf-8' -Body $body -WebSession $Session
    return $response.message
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

function Remove-TestRow {
    param([string]$DocType, [string]$Name)
    if ([string]::IsNullOrWhiteSpace($Name)) { return }
    $pythonArgs = "[$(ConvertTo-PythonStringLiteral $DocType),{'name':$(ConvertTo-PythonStringLiteral $Name)}]"
    & docker compose @composeArgs exec -T backend bench --site $SiteName execute frappe.db.delete --args $pythonArgs | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "Row cleanup failed for $DocType $Name" }
}

function Remove-TestChildren {
    param([string]$DocType, [string]$Field, [string]$Value)
    if ([string]::IsNullOrWhiteSpace($Value)) { return }
    $pythonArgs = "[$(ConvertTo-PythonStringLiteral $DocType),{$(ConvertTo-PythonStringLiteral $Field):$(ConvertTo-PythonStringLiteral $Value)}]"
    & docker compose @composeArgs exec -T backend bench --site $SiteName execute frappe.db.delete --args $pythonArgs | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "Cleanup failed for $DocType children." }
}

function Remove-OpportunityChildren {
    param([string]$OpportunityId)
    if ([string]::IsNullOrWhiteSpace($OpportunityId)) { return }
    foreach ($docType in @('CRM Opportunity Stakeholder', 'CRM Opportunity Action', 'CRM Opportunity History')) {
        $pythonArgs = "[$(ConvertTo-PythonStringLiteral $docType),{'opportunity':$(ConvertTo-PythonStringLiteral $OpportunityId)}]"
        & docker compose @composeArgs exec -T backend bench --site $SiteName execute frappe.db.delete --args $pythonArgs | Out-Null
        if ($LASTEXITCODE -ne 0) { throw "Cleanup failed for $docType children of $OpportunityId" }
    }
}

function New-CrmUser {
    param($AdminSession, [string]$Email, [string]$Password, [string]$Role, [string]$FirstName)
    $body = @{
        email = $Email; first_name = $FirstName; enabled = 1; send_welcome_email = 0
        new_password = $Password; roles = @(@{ role = $Role })
    } | ConvertTo-Json -Compress -Depth 5
    $response = Invoke-RestMethod -Uri "$BaseUrl/api/resource/User" -Method Post -ContentType 'application/json' -Body $body -WebSession $AdminSession
    return $response.data.name
}

try {
    $adminPassword = (& docker compose @composeArgs run --rm --no-deps --entrypoint cat secrets-init /run/crm-local-secrets/admin_password).Trim()
    if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($adminPassword)) {
        throw 'Could not read the local Administrator password from the isolated secrets volume.'
    }
    $adminSession = New-Object Microsoft.PowerShell.Commands.WebRequestSession
    Invoke-RestMethod -Uri "$BaseUrl/api/method/login" -Method Post -Body @{ usr = 'Administrator'; pwd = $adminPassword } -WebSession $adminSession | Out-Null

    $stamp = [DateTimeOffset]::UtcNow.ToUnixTimeMilliseconds()
    $salesEmail = "crm-stage5g-sales-$stamp@example.invalid"
    $actionSalesEmail = "crm-stage5g-action-sales-$stamp@example.invalid"
    $managerEmail = "crm-stage5g-manager-$stamp@example.invalid"
    $salesPassword = "Aa1!$([guid]::NewGuid().ToString('N'))"
    $actionSalesPassword = "Aa1!$([guid]::NewGuid().ToString('N'))"
    $managerPassword = "Aa1!$([guid]::NewGuid().ToString('N'))"
    $created.SalesUser = New-CrmUser $adminSession $salesEmail $salesPassword 'CRM Sales' 'Stage5G Sales'
    $created.ActionSalesUser = New-CrmUser $adminSession $actionSalesEmail $actionSalesPassword 'CRM Sales' 'Stage5G Action Sales'
    $created.ManagerUser = New-CrmUser $adminSession $managerEmail $managerPassword 'CRM Manager' 'Stage5G Manager'

    $salesSession = New-Object Microsoft.PowerShell.Commands.WebRequestSession
    $actionSalesSession = New-Object Microsoft.PowerShell.Commands.WebRequestSession
    $managerSession = New-Object Microsoft.PowerShell.Commands.WebRequestSession
    Invoke-RestMethod -Uri "$BaseUrl/api/method/login" -Method Post -Body @{ usr = $salesEmail; pwd = $salesPassword } -WebSession $salesSession | Out-Null
    Invoke-RestMethod -Uri "$BaseUrl/api/method/login" -Method Post -Body @{ usr = $actionSalesEmail; pwd = $actionSalesPassword } -WebSession $actionSalesSession | Out-Null
    Invoke-RestMethod -Uri "$BaseUrl/api/method/login" -Method Post -Body @{ usr = $managerEmail; pwd = $managerPassword } -WebSession $managerSession | Out-Null

    $accountInput = @{
        name = "Stage 5G HTTP Account $stamp"; shortName = "S5G $stamp"; segment = 'Frontend'
        tier = 'A'; city = 'Shanghai'; region = 'East China'; owner = $salesEmail; visibility = 'Private'
    }
    $account = Invoke-CrmPost $salesSession 'rayher_crm.api.v1.accounts.create_account' @{ input = $accountInput }
    $created.Account = $account.data.id

    $productionStatus = [string]::Concat([char]0x91CF, [char]0x4EA7)
    $siteJson = @{
        address_title = "Stage 5G Site $stamp"; address_type = 'Other'; address_line1 = "Stage 5G Site $stamp"
        city = 'Shanghai'; country = 'China'; custom_crm_owner = $salesEmail
        custom_crm_site_type = 'Fab'; custom_crm_process = 'Frontend'; custom_crm_status = $productionStatus
        links = @(@{ link_doctype = 'Customer'; link_name = $created.Account })
    } | ConvertTo-Json -Compress -Depth 5
    $siteResponse = Invoke-RestMethod -Uri "$BaseUrl/api/resource/Address" -Method Post -ContentType 'application/json; charset=utf-8' -Body ([Text.Encoding]::UTF8.GetBytes($siteJson)) -WebSession $adminSession
    $created.Site = $siteResponse.data.name

    $contact = Invoke-CrmPost $salesSession 'rayher_crm.api.v1.contacts.create_contact' @{ input = @{
        accountId = $created.Account; siteId = $created.Site; name = "Stage 5G Contact $stamp"
        title = 'Process Director'; department = 'Engineering'; phone = '13800000013'
        email = "stage5g-contact-$stamp@example.invalid"; relationship = 'Developing'
        status = 'Active'; owner = $salesEmail
    } }
    $created.Contact = $contact.data.id

    $stakeholder = Invoke-CrmPost $salesSession 'rayher_crm.api.v1.stakeholders.create_stakeholder' @{ input = @{
        accountId = $created.Account; name = "Stage 5G Stakeholder $stamp"; title = 'VP'
        department = 'Operations'; role = 'Decision Maker'; influence = 'High'
        relationship = 'Strong'; email = "stage5g-stakeholder-$stamp@example.invalid"
    } }
    $created.Stakeholder = $stakeholder.data.id
    $stakeholderUpdate = Invoke-CrmPost $salesSession 'rayher_crm.api.v1.stakeholders.update_stakeholder' @{
        id = $created.Stakeholder; expectedModified = $stakeholder.data.modified; input = @{
            accountId = $created.Account; name = "Stage 5G Stakeholder $stamp"; title = 'VP'
            department = 'Operations'; role = 'Economic Buyer'; influence = 'Medium'
            relationship = 'Strong'; email = "stage5g-stakeholder-$stamp@example.invalid"
        }
    }
    if ($stakeholderUpdate.data.role -ne 'Economic Buyer' -or $stakeholderUpdate.data.influence -ne 'Medium') {
        throw 'Stakeholder compatibility update did not persist Contact fields.'
    }

    $discoveryStage = -join @([char]0x9700, [char]0x6C42, [char]0x53D1, [char]0x73B0)
    $opportunity = Invoke-CrmPost $salesSession 'rayher_crm.api.v1.opportunities.create_strategy_opportunity' @{ input = @{
        accountId = $created.Account; siteId = $created.Site; title = "Stage 5G Opportunity $stamp"
        owner = $salesEmail; stage = $discoveryStage; forecast = 'Pipeline'; amount = '1000'
        probability = 25; intentScore = 70; poDate = '2026-12-31'; toolType = 'Inspection'
        saleType = 'New Equipment'; subRegion = 'East China'; currency = 'CNY'; originalAmount = '1000'
    } }
    $created.Opportunity = $opportunity.data.id
    Invoke-CrmPost $salesSession 'rayher_crm.api.v1.opportunities.create_opportunity_action' @{
        opportunityId = $created.Opportunity; input = @{
            title = 'Prepare HTTP plan'; owner = $salesEmail; due = '2026-08-30'; status = 'Open'
        }
    } | Out-Null

    $visit = Invoke-CrmPost $salesSession 'rayher_crm.api.v1.visits.create_visit' @{ input = @{
        accountId = $created.Account; primaryContactId = $created.Contact; subject = "Stage 5G Visit $stamp"
        opportunityId = $created.Opportunity; date = '2026-08-20'; type = 'On-site'; owner = $salesEmail; objective = 'Confirm criteria'
    } }
    $created.Visit = $visit.data.id
    if ($visit.data.opportunityId -ne $created.Opportunity) { throw 'Visit did not persist its linked Opportunity.' }
    $visited = Invoke-CrmPost $salesSession 'rayher_crm.api.v1.visits.update_visit' @{
        id = $created.Visit; expectedModified = $visit.data.modified
        command = @{ type = 'advance'; status = 'Visited'; outcome = 'Criteria confirmed' }
    }
    Invoke-CrmPost $salesSession 'rayher_crm.api.v1.visits.update_meeting_record' @{
        id = $created.Visit; input = @{
            purpose = 'Confirm acceptance scope'; attendees = 'Customer A; Sales A'; agenda = 'Review samples and acceptance criteria'
            summary = 'Twelve wafers and acceptance criteria confirmed'; conclusion = 'Proceed to Demo plan'; followup = 'Send Demo plan'
        }
    } | Out-Null
    $visited = (Invoke-RestMethod -Uri "$BaseUrl/api/method/rayher_crm.api.v1.visits.get_visit?id=$([Uri]::EscapeDataString($created.Visit))" -WebSession $salesSession).message
    $minutes = Invoke-CrmPost $salesSession 'rayher_crm.api.v1.visits.update_visit' @{
        id = $created.Visit; expectedModified = $visited.data.modified
        command = @{ type = 'edit'; nextAction = 'Prepare plan'; actionOwner = $actionSalesEmail; due = '2026-08-25' }
    }

    $expectedVisitRoute = "/visits?focus=$($created.Visit)"
    $actionSalesNotifications = Invoke-RestMethod -Uri "$BaseUrl/api/method/rayher_crm.api.v1.notifications.list_notifications?page=1&pageSize=20" -WebSession $actionSalesSession
    $assigned = @($actionSalesNotifications.message.data | Where-Object { $_.category -eq 'Visit' -and $_.title -eq 'Visit action assigned' -and $_.route -eq $expectedVisitRoute })
    if ($assigned.Count -ne 1) { throw 'Action Sales did not receive exactly one precisely routed Visit action notification.' }
    if ($assigned[0].recipientId -ne $actionSalesEmail -or $assigned[0].actorId -ne $salesEmail -or $assigned[0].message -notlike '*Prepare plan*') { throw 'Visit action notification identity or business context is incorrect.' }
    $privateVisitStatus = 0
    try {
        Invoke-RestMethod -Uri "$BaseUrl/api/method/rayher_crm.api.v1.visits.get_visit?id=$([Uri]::EscapeDataString($created.Visit))" -WebSession $actionSalesSession | Out-Null
    } catch { $privateVisitStatus = [int]$_.Exception.Response.StatusCode }
    if ($privateVisitStatus -ne 403) { throw "Expected Private Account boundary HTTP 403 for a Visit action owner, got $privateVisitStatus." }
    # Assignment cannot bypass a Private Account; publish this fixture before
    # checking that the assigned Sales user can open the notification's target.
    $accountInput.visibility = 'Public'
    Invoke-CrmPost $salesSession 'rayher_crm.api.v1.accounts.update_account' @{
        id = $created.Account; input = $accountInput; expectedModified = $account.data.modified
    } | Out-Null
    $actionOwnerVisit = (Invoke-RestMethod -Uri "$BaseUrl/api/method/rayher_crm.api.v1.visits.get_visit?id=$([Uri]::EscapeDataString($created.Visit))" -WebSession $actionSalesSession).message.data
    if ($actionOwnerVisit.id -ne $created.Visit -or $actionOwnerVisit.actionOwner -ne $actionSalesEmail) { throw 'Visit action recipient could not open the precisely routed Visit.' }
    $created.Notifications += $assigned[0].id

    $reviewStatus = 0
    try {
        Invoke-CrmPost $salesSession 'rayher_crm.api.v1.visits.update_visit' @{
            id = $created.Visit; expectedModified = $minutes.data.modified
            command = @{ type = 'advance'; status = 'Manager Reviewed' }
        } | Out-Null
    } catch { $reviewStatus = [int]$_.Exception.Response.StatusCode }
    if ($reviewStatus -ne 403) { throw "Expected Sales Manager Review HTTP 403, got $reviewStatus." }

    $reviewed = Invoke-CrmPost $managerSession 'rayher_crm.api.v1.visits.update_visit' @{
        id = $created.Visit; expectedModified = $minutes.data.modified
        command = @{ type = 'advance'; status = 'Manager Reviewed' }
    }
    if ($reviewed.data.status -ne 'Manager Reviewed') { throw 'Manager Review did not persist.' }
    $salesNotifications = Invoke-RestMethod -Uri "$BaseUrl/api/method/rayher_crm.api.v1.notifications.list_notifications?page=1&pageSize=20" -WebSession $salesSession
    $reviewNotices = @($salesNotifications.message.data | Where-Object { $_.category -eq 'Visit' -and $_.title -eq 'Visit minutes reviewed' -and $_.route -eq $expectedVisitRoute })
    if ($reviewNotices.Count -ne 1) { throw 'Sales did not receive exactly one precisely routed Visit review notification.' }
    if ($reviewNotices[0].recipientId -ne $salesEmail -or $reviewNotices[0].actorId -ne $managerEmail -or $reviewNotices[0].message -notlike '*reviewed*') { throw 'Visit review notification identity or business context is incorrect.' }
    $ownerVisit = (Invoke-RestMethod -Uri "$BaseUrl/api/method/rayher_crm.api.v1.visits.get_visit?id=$([Uri]::EscapeDataString($created.Visit))" -WebSession $salesSession).message.data
    if ($ownerVisit.id -ne $created.Visit -or $ownerVisit.status -ne 'Manager Reviewed') { throw 'Visit owner could not open the reviewed Visit from the notification route.' }
    $created.Notifications += $reviewNotices[0].id

    $visitList = Invoke-RestMethod -Uri "$BaseUrl/api/method/rayher_crm.api.v1.visits.list_visits?accountId=$($created.Account)&status=Manager%20Reviewed&page=1&pageSize=20" -WebSession $salesSession
    if ($created.Visit -notin @($visitList.message.data.items | ForEach-Object { $_.id })) { throw 'Scoped Visit list omitted the reviewed Visit.' }
    $pipeline = Invoke-RestMethod -Uri "$BaseUrl/api/method/rayher_crm.api.v1.pipeline.list_pipeline?accountId=$($created.Account)" -WebSession $salesSession
    if ($created.Opportunity -notin @($pipeline.message.data.opportunities | ForEach-Object { $_.id })) { throw 'Pipeline omitted canonical Opportunity.' }
    $expectedWeightedPipeline = [decimal]$opportunity.data.amount * [decimal]$opportunity.data.probability / 100
    $actualOpenPipeline = [decimal]$pipeline.message.data.totals.openPipeline
    $actualWeightedPipeline = [decimal]$pipeline.message.data.totals.weightedPipeline
    if ($actualOpenPipeline -ne [decimal]1000 -or $actualWeightedPipeline -ne $expectedWeightedPipeline) {
        throw "Pipeline totals were not canonical: open=$actualOpenPipeline weighted=$actualWeightedPipeline expectedWeighted=$expectedWeightedPipeline."
    }
    $detail = Invoke-RestMethod -Uri "$BaseUrl/api/method/rayher_crm.api.v1.accounts.get_account_360?id=$($created.Account)" -WebSession $salesSession
    if ($created.Visit -notin @($detail.message.data.visits | ForEach-Object { $_.id })) { throw 'Account360 omitted canonical Visit.' }
    $dashboard = Invoke-RestMethod -Uri "$BaseUrl/api/method/rayher_crm.api.v1.dashboard.get_dashboard?range=month&segment=Frontend" -WebSession $salesSession
    $cnyKpi = @($dashboard.message.data.kpis.moneyByCurrency | Where-Object { $_.currency -eq 'CNY' })[0]
    if (-not $cnyKpi -or [decimal]$cnyKpi.openPipeline -ne [decimal]1000 -or [decimal]$cnyKpi.weightedPipeline -ne $expectedWeightedPipeline -or @($dashboard.message.data.process.requirementsByStatus).Count -ne 0) {
        throw 'Dashboard currency aggregation or empty Requirement boundary failed.'
    }

    $requirements = Invoke-RestMethod -Uri "$BaseUrl/api/method/rayher_crm.api.v1.read_only_views.list_requirements?page=2&pageSize=5" -WebSession $salesSession
    $contracts = Invoke-RestMethod -Uri "$BaseUrl/api/method/rayher_crm.api.v1.read_only_views.list_contracts?page=1&pageSize=5" -WebSession $salesSession
    $documents = Invoke-RestMethod -Uri "$BaseUrl/api/method/rayher_crm.api.v1.read_only_views.list_controlled_documents?page=1&pageSize=5" -WebSession $salesSession
    if ($requirements.message.meta.total -ne 0 -or $requirements.message.meta.page -ne 2) { throw 'Requirement empty-source pagination failed.' }
    $documentCount = @($documents.message.data.items).Count
    if ($contracts.message.meta.total -ne 0 -or $documents.message.meta.page -ne 1 -or $documentCount -gt 5 -or $documents.message.meta.total -lt $documentCount) { throw 'Contract empty-source or controlled-document pagination boundary failed.' }
    $accessStatus = 0
    try {
        Invoke-CrmPost $salesSession 'rayher_crm.api.v1.read_only_views.request_controlled_document_access' @{
            versionId = 'DOC-NOT-INGESTED'; reason = 'HTTP acceptance'
        } | Out-Null
    } catch { $accessStatus = [int]$_.Exception.Response.StatusCode }
    if ($accessStatus -ne 404) { throw "Expected controlled-document access HTTP 404, got $accessStatus." }

    Write-Output 'Stage 5G authenticated HTTP acceptance passed: Visit workflow/notifications/Pipeline/Account360/Dashboard/Stakeholder/empty-source views.'
} finally {
    $adminPassword = $null
    $salesPassword = $null
    $actionSalesPassword = $null
    $managerPassword = $null
    foreach ($notificationId in @($created.Notifications)) { Remove-TestRow 'CRM Notification Event' $notificationId }
    foreach ($userId in @($created.ManagerUser, $created.ActionSalesUser, $created.SalesUser)) {
        Remove-TestChildren 'CRM Notification Event' 'recipient_user' $userId
    }
    Remove-TestChildren 'CRM Visit Meeting Record' 'visit' $created.Visit
    Remove-TestChildren 'CRM Notification Event' 'source_name' $created.Visit
    Remove-TestDoc 'CRM Visit' $created.Visit
    Remove-TestDoc 'Contact' $created.Stakeholder
    Remove-OpportunityChildren $created.Opportunity
    Remove-TestDoc 'CRM Opportunity' $created.Opportunity
    Remove-TestDoc 'Contact' $created.Contact
    Remove-TestDoc 'Address' $created.Site
    Remove-TestDoc 'Customer' $created.Account
    Remove-TestDoc 'User' $created.ManagerUser
    Remove-TestDoc 'User' $created.ActionSalesUser
    Remove-TestDoc 'User' $created.SalesUser
}
