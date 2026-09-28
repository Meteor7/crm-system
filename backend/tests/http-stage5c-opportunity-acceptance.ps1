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
    Stakeholder = $null
    Action = $null
    Opportunity = $null
    ForeignOpportunity = $null
    Contact = $null
    Site = $null
    ForeignSite = $null
    Account = $null
    ForeignAccount = $null
    User = $null
}

function Invoke-CrmPost {
    param($Session, [string]$Method, [hashtable]$Arguments)
    $body = @{}
    foreach ($key in $Arguments.Keys) {
        $value = ConvertTo-CrmHttpFormValue -Value $Arguments[$key]
        $body[$key] = if ($key -eq 'input') { $value | ConvertTo-Json -Compress -Depth 10 } else { $value }
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

function Remove-OpportunityChildren {
    param([string]$OpportunityId)
    if ([string]::IsNullOrWhiteSpace($OpportunityId)) { return }
    foreach ($docType in @('CRM Opportunity Stakeholder', 'CRM Opportunity Action', 'CRM Opportunity History', 'CRM Opportunity Stage History', 'CRM Opportunity Probability History', 'CRM Opportunity Internal Validation')) {
        $pythonArgs = "[$(ConvertTo-PythonStringLiteral $docType),{'opportunity':$(ConvertTo-PythonStringLiteral $OpportunityId)}]"
        & docker compose @composeArgs exec -T backend bench --site $SiteName execute frappe.db.delete --args $pythonArgs | Out-Null
        if ($LASTEXITCODE -ne 0) { throw "Cleanup failed for $docType children of $OpportunityId" }
    }
}

function Get-ArchivedValue {
    param([string]$DocType, [string]$Name)
    $pythonArgs = "[$(ConvertTo-PythonStringLiteral $DocType),$(ConvertTo-PythonStringLiteral $Name),'archived']"
    $output = (& docker compose @composeArgs exec -T backend bench --site $SiteName execute frappe.db.get_value --args $pythonArgs) -join ''
    if ($LASTEXITCODE -ne 0) { throw "Could not inspect archived value for $DocType $Name" }
    return $output.Trim()
}

try {
    $adminPassword = (& docker compose @composeArgs run --rm --no-deps --entrypoint cat secrets-init /run/crm-local-secrets/admin_password).Trim()
    if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($adminPassword)) {
        throw 'Could not read the local Administrator password from the isolated secrets volume.'
    }

    $adminSession = New-Object Microsoft.PowerShell.Commands.WebRequestSession
    Invoke-RestMethod -Uri "$BaseUrl/api/method/login" -Method Post -Body @{ usr = 'Administrator'; pwd = $adminPassword } -WebSession $adminSession | Out-Null

    $stamp = [DateTimeOffset]::UtcNow.ToUnixTimeMilliseconds()
    $salesEmail = "crm-stage5c-http-$stamp@example.invalid"
    $salesPassword = "Aa1!$([guid]::NewGuid().ToString('N'))"
    $userBody = @{
        email = $salesEmail
        first_name = 'CRM Stage 5C HTTP'
        enabled = 1
        send_welcome_email = 0
        new_password = $salesPassword
        roles = @(@{ role = 'CRM Sales' })
    } | ConvertTo-Json -Compress -Depth 5
    $userResponse = Invoke-RestMethod -Uri "$BaseUrl/api/resource/User" -Method Post -ContentType 'application/json' -Body $userBody -WebSession $adminSession
    $created.User = $userResponse.data.name

    $salesSession = New-Object Microsoft.PowerShell.Commands.WebRequestSession
    Invoke-RestMethod -Uri "$BaseUrl/api/method/login" -Method Post -Body @{ usr = $salesEmail; pwd = $salesPassword } -WebSession $salesSession | Out-Null

    $account = Invoke-CrmPost $salesSession 'rayher_crm.api.v1.accounts.create_account' @{ input = @{
        name = "Stage 5C HTTP Account $stamp"; shortName = "S5C $stamp"; segment = 'Frontend'
        tier = 'A'; city = 'Shanghai'; region = 'East China'; owner = $salesEmail
    } }
    $created.Account = $account.data.id
    $foreign = Invoke-CrmPost $adminSession 'rayher_crm.api.v1.accounts.create_account' @{ input = @{
        name = "Stage 5C Foreign Account $stamp"; shortName = "Foreign $stamp"; segment = 'Frontend'
        tier = 'B'; city = 'Beijing'; region = 'North China'; owner = 'Administrator'
    } }
    $created.ForeignAccount = $foreign.data.id

    $productionStatus = [string]::Concat([char]0x91CF, [char]0x4EA7)
    foreach ($siteSpec in @(
        @{ Account = $created.Account; Owner = $salesEmail; Title = "Stage 5C Site $stamp"; Target = 'Site' },
        @{ Account = $created.ForeignAccount; Owner = 'Administrator'; Title = "Stage 5C Foreign Site $stamp"; Target = 'ForeignSite' }
    )) {
        $siteJson = @{
            address_title = $siteSpec.Title; address_type = 'Other'; address_line1 = $siteSpec.Title
            city = 'Shanghai'; country = 'China'; custom_crm_owner = $siteSpec.Owner
            custom_crm_site_type = 'Fab'; custom_crm_process = 'Frontend'; custom_crm_status = $productionStatus
            links = @(@{ link_doctype = 'Customer'; link_name = $siteSpec.Account })
        } | ConvertTo-Json -Compress -Depth 5
        $siteBody = [Text.Encoding]::UTF8.GetBytes($siteJson)
        $siteResponse = Invoke-RestMethod -Uri "$BaseUrl/api/resource/Address" -Method Post -ContentType 'application/json; charset=utf-8' -Body $siteBody -WebSession $adminSession
        $created[$siteSpec.Target] = $siteResponse.data.name
    }

    $contact = Invoke-CrmPost $salesSession 'rayher_crm.api.v1.contacts.create_contact' @{ input = @{
        accountId = $created.Account; name = "Stage 5C Contact $stamp"; title = 'Process Director'
        department = 'Engineering'; phone = '13800000009'; email = "stage5c-contact-$stamp@example.invalid"
        relationship = 'Developing'; status = 'Active'; owner = $salesEmail
    } }
    $created.Contact = $contact.data.id

    $qualifiedStage = 'qualified_opportunity'
    $opportunityInput = @{
        probabilityLevel = 'pipeline'
        accountId = $created.Account; siteId = $created.Site; title = "Stage 5C Opportunity $stamp"
        owner = $salesEmail; stage = $qualifiedStage; qualificationConfirmed = $true; forecast = 'Pipeline'; amount = '123456.78'
        probability = 20; intentScore = 30; poDate = '2026-12-31'; toolType = 'Inspection'
        saleType = 'New Equipment'; subRegion = 'East China'; currency = 'CNY'; originalAmount = '123456.78'
        paymentMilestones = @('30% PO', '70% FAT'); strengths = @('Local support'); redFlags = @(); informationNeeded = @('Budget')
    }
    $opportunity = Invoke-CrmPost $salesSession 'rayher_crm.api.v1.opportunities.create_strategy_opportunity' @{ input = $opportunityInput }
    $created.Opportunity = $opportunity.data.id
    if ($opportunity.data.owner -ne $salesEmail -or $opportunity.data.stage -ne $qualifiedStage) {
        throw 'HTTP Opportunity create returned an unexpected owner or stage.'
    }

    $foreignInput = $opportunityInput.Clone()
    $foreignInput.accountId = $created.ForeignAccount
    $foreignInput.siteId = $created.ForeignSite
    $foreignInput.title = "Stage 5C Foreign Opportunity $stamp"
    $foreignInput.owner = 'Administrator'
    $foreignOpportunity = Invoke-CrmPost $adminSession 'rayher_crm.api.v1.opportunities.create_strategy_opportunity' @{ input = $foreignInput }
    $created.ForeignOpportunity = $foreignOpportunity.data.id

    $search = [Uri]::EscapeDataString([string]$stamp)
    $list = Invoke-RestMethod -Uri "$BaseUrl/api/method/rayher_crm.api.v1.opportunities.list_strategy_opportunities?search=$search&page=1&pageSize=200" -WebSession $salesSession
    $visibleIds = @($list.message.data.items | ForEach-Object { $_.id })
    if ($created.Opportunity -notin $visibleIds -or $created.ForeignOpportunity -in $visibleIds) {
        throw "HTTP Opportunity list scope mismatch: expected=$($created.Opportunity), foreign=$($created.ForeignOpportunity), visible=$($visibleIds -join ',')."
    }

    $staleModified = $opportunity.data.modified
    $updated = Invoke-CrmPost $salesSession 'rayher_crm.api.v1.opportunities.update_strategy_opportunity' @{
        id = $created.Opportunity; input = @{ probabilityLevel = 'upside'; intentScore = 40 }; expectedModified = $staleModified
    }
    if ($updated.data.stage -ne $qualifiedStage -or $updated.data.probabilityLevel -ne 'upside' -or $updated.data.score -ne 40) {
        throw "HTTP Opportunity update mismatch: stage=$($updated.data.stage), probabilityLevel=$($updated.data.probabilityLevel), score=$($updated.data.score)."
    }

    $conflictStatus = 0
    try {
        Invoke-CrmPost $salesSession 'rayher_crm.api.v1.opportunities.update_strategy_opportunity' @{
            id = $created.Opportunity; input = @{ probabilityLevel = 'committed' }; expectedModified = $staleModified
        } | Out-Null
    } catch {
        $conflictStatus = [int]$_.Exception.Response.StatusCode
    }
    if ($conflictStatus -ne 409) { throw "Expected HTTP 409 for stale Opportunity update, got $conflictStatus." }

    $scopeStatus = 0
    try {
        Invoke-CrmPost $salesSession 'rayher_crm.api.v1.opportunities.update_strategy_opportunity' @{
            id = $created.ForeignOpportunity; input = @{ probabilityLevel = 'upside' }; expectedModified = $foreignOpportunity.data.modified
        } | Out-Null
    } catch {
        $scopeStatus = [int]$_.Exception.Response.StatusCode
    }
    if ($scopeStatus -ne 403) { throw "Expected HTTP 403 for foreign Opportunity update, got $scopeStatus." }

    $stageStatus = 0
    try {
        Invoke-CrmPost $salesSession 'rayher_crm.api.v1.opportunities.update_strategy_opportunity' @{
            id = $created.Opportunity; input = @{ stage = 'demo_done' }; expectedModified = $updated.data.modified
        } | Out-Null
    } catch {
        $stageStatus = [int]$_.Exception.Response.StatusCode
    }
    if ($stageStatus -ne 409) { throw "Expected HTTP 409 for a direct Opportunity stage change, got $stageStatus." }

    $stakeholder = Invoke-CrmPost $salesSession 'rayher_crm.api.v1.opportunities.create_opportunity_stakeholder' @{
        opportunityId = $created.Opportunity; input = @{
            contactId = $created.Contact; role = 'Decision Maker'; influence = 'High'; stance = 'Support'
            coverage = 'Monthly'; isCoach = $true; winResult = 'Budget'; opportunityNotes = 'HTTP acceptance'
        }
    }
    $created.Stakeholder = $stakeholder.data.id
    $action = Invoke-CrmPost $salesSession 'rayher_crm.api.v1.opportunities.create_opportunity_action' @{
        opportunityId = $created.Opportunity; input = @{
            title = 'Confirm scope'; owner = $salesEmail; due = '2026-09-01'; status = 'Open'
        }
    }
    $created.Action = $action.data.id

    Invoke-CrmPost $salesSession 'rayher_crm.api.v1.opportunities.delete_opportunity_stakeholder' @{
        opportunityId = $created.Opportunity; stakeholderId = $created.Stakeholder
    } | Out-Null
    Invoke-CrmPost $salesSession 'rayher_crm.api.v1.opportunities.delete_opportunity_action' @{
        opportunityId = $created.Opportunity; actionId = $created.Action
    } | Out-Null
    if ((Get-ArchivedValue 'CRM Opportunity Stakeholder' $created.Stakeholder) -notmatch '1') {
        throw 'HTTP Stakeholder delete did not preserve an archived database row.'
    }
    if ((Get-ArchivedValue 'CRM Opportunity Action' $created.Action) -notmatch '1') {
        throw 'HTTP Action delete did not preserve an archived database row.'
    }
    $afterDelete = Invoke-RestMethod -Uri "$BaseUrl/api/method/rayher_crm.api.v1.opportunities.list_strategy_opportunities" -WebSession $salesSession
    $current = @($afterDelete.message.data.items | Where-Object { $_.id -eq $created.Opportunity })[0]
    if (@($current.stakeholders).Count -ne 0 -or @($current.actions).Count -ne 0) {
        throw 'Archived relations remained visible in the HTTP Opportunity DTO.'
    }

    $lostStaleStatus = 0
    try {
        Invoke-CrmPost $salesSession 'rayher_crm.api.v1.opportunities.mark_opportunity_lost' @{
            id = $created.Opportunity; input = @{ lostReason = 'Customer postponed the project' }; expectedModified = $staleModified
        } | Out-Null
    } catch {
        $lostStaleStatus = [int]$_.Exception.Response.StatusCode
    }
    if ($lostStaleStatus -ne 409) { throw "Expected HTTP 409 for a stale mark-lost, got $lostStaleStatus." }
    $lost = Invoke-CrmPost $salesSession 'rayher_crm.api.v1.opportunities.mark_opportunity_lost' @{
        id = $created.Opportunity; input = @{ lostReason = 'Customer postponed the project' }; expectedModified = $current.modified
    }
    if ($lost.data.stage -ne 'lost' -or $lost.data.lostAtStage -ne $qualifiedStage -or $lost.data.lostReason -ne 'Customer postponed the project') {
        throw "HTTP mark-lost mismatch: stage=$($lost.data.stage), lostAtStage=$($lost.data.lostAtStage), lostReason=$($lost.data.lostReason)."
    }

    & docker compose @composeArgs restart backend frontend queue-short queue-long scheduler websocket | Out-Null
    if ($LASTEXITCODE -ne 0) { throw 'Runtime service restart failed.' }
    $persisted = $null
    $deadline = [DateTime]::UtcNow.AddSeconds(90)
    while ([DateTime]::UtcNow -lt $deadline -and -not $persisted) {
        try {
            $afterRestart = Invoke-RestMethod -Uri "$BaseUrl/api/method/rayher_crm.api.v1.opportunities.list_strategy_opportunities" -WebSession $salesSession
            $persisted = @($afterRestart.message.data.items | Where-Object { $_.id -eq $created.Opportunity })[0]
        } catch {
            Start-Sleep -Seconds 2
        }
    }
    if (-not $persisted) { throw 'Opportunity did not remain readable after runtime service restart.' }

    Write-Output 'Stage 5C authenticated HTTP acceptance passed: create/list/update/409/scope-403/stage-change-409/relations/soft-delete/mark-lost/restart-persistence.'
} finally {
    $adminPassword = $null
    $salesPassword = $null
    Remove-OpportunityChildren $created.Opportunity
    Remove-TestDoc 'CRM Opportunity' $created.Opportunity
    Remove-OpportunityChildren $created.ForeignOpportunity
    Remove-TestDoc 'CRM Opportunity' $created.ForeignOpportunity
    Remove-TestDoc 'Contact' $created.Contact
    Remove-TestDoc 'Address' $created.Site
    Remove-TestDoc 'Address' $created.ForeignSite
    Remove-TestDoc 'Customer' $created.Account
    Remove-TestDoc 'Customer' $created.ForeignAccount
    Remove-TestDoc 'User' $created.User
}
