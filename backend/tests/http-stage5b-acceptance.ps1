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
    Opportunity = $null
    Lead = $null
    ConversionContact = $null
    ConversionSite = $null
    ConversionAccount = $null
    Contact = $null
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

function Remove-TestChildren {
    param([string]$DocType, [string]$Field, [string]$Value)
    if ([string]::IsNullOrWhiteSpace($Value)) { return }
    $pythonArgs = "[$(ConvertTo-PythonStringLiteral $DocType),{$(ConvertTo-PythonStringLiteral $Field):$(ConvertTo-PythonStringLiteral $Value)}]"
    & docker compose @composeArgs exec -T backend bench --site $SiteName execute frappe.db.delete --args $pythonArgs | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "Cleanup failed for $DocType children of $Value" }
}

try {
    $adminPassword = (& docker compose @composeArgs run --rm --no-deps --entrypoint cat secrets-init /run/crm-local-secrets/admin_password).Trim()
    if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($adminPassword)) {
        throw 'Could not read the local Administrator password from the isolated secrets volume.'
    }

    $adminSession = New-Object Microsoft.PowerShell.Commands.WebRequestSession
    Invoke-RestMethod -Uri "$BaseUrl/api/method/login" -Method Post -Body @{ usr = 'Administrator'; pwd = $adminPassword } -WebSession $adminSession | Out-Null

    $stamp = [DateTimeOffset]::UtcNow.ToUnixTimeMilliseconds()
    $salesEmail = "crm-http-$stamp@example.invalid"
    $salesPassword = "Aa1!$([guid]::NewGuid().ToString('N'))"
    $userBody = @{
        email = $salesEmail
        first_name = 'CRM HTTP Acceptance'
        enabled = 1
        send_welcome_email = 0
        new_password = $salesPassword
        roles = @(@{ role = 'CRM Sales' })
    } | ConvertTo-Json -Compress -Depth 5
    $userResponse = Invoke-RestMethod -Uri "$BaseUrl/api/resource/User" -Method Post -ContentType 'application/json' -Body $userBody -WebSession $adminSession
    $created.User = $userResponse.data.name

    $foreignInput = @{
        name = "HTTP Foreign Account $stamp"
        shortName = "HTTP Foreign $stamp"
        segment = 'Frontend'
        tier = 'B'
        city = 'Beijing'
        region = 'North China'
        owner = 'Administrator'
    }
    $foreign = Invoke-CrmPost $adminSession 'rayher_crm.api.v1.accounts.create_account' @{ input = $foreignInput }
    $created.ForeignAccount = $foreign.data.id

    $salesSession = New-Object Microsoft.PowerShell.Commands.WebRequestSession
    Invoke-RestMethod -Uri "$BaseUrl/api/method/login" -Method Post -Body @{ usr = $salesEmail; pwd = $salesPassword } -WebSession $salesSession | Out-Null

    $accountInput = @{
        name = "HTTP Account $stamp"
        shortName = "HTTP $stamp"
        segment = 'Advanced Packaging'
        tier = 'A'
        city = 'Shanghai'
        region = 'East China'
        owner = $salesEmail
    }
    $account = Invoke-CrmPost $salesSession 'rayher_crm.api.v1.accounts.create_account' @{ input = $accountInput }
    $created.Account = $account.data.id
    $staleModified = $account.data.modified

    $accountInput.city = 'Suzhou'
    $updated = Invoke-CrmPost $salesSession 'rayher_crm.api.v1.accounts.update_account' @{
        id = $created.Account
        input = $accountInput
        expectedModified = $staleModified
    }
    if ($updated.data.city -ne 'Suzhou') { throw 'HTTP Account update did not persist the expected city.' }

    $conflictStatus = 0
    try {
        Invoke-CrmPost $salesSession 'rayher_crm.api.v1.accounts.update_account' @{
            id = $created.Account
            input = $accountInput
            expectedModified = $staleModified
        } | Out-Null
    } catch {
        $conflictStatus = [int]$_.Exception.Response.StatusCode
    }
    if ($conflictStatus -ne 409) { throw "Expected HTTP 409 for stale update, got $conflictStatus." }

    $contactInput = @{
        accountId = $created.Account
        name = "HTTP Contact $stamp"
        title = 'Process Manager'
        department = 'Process Engineering'
        phone = '13800000006'
        email = "crm-http-contact-$stamp@example.invalid"
        relationship = 'Developing'
        status = 'Active'
        owner = $salesEmail
    }
    $contact = Invoke-CrmPost $salesSession 'rayher_crm.api.v1.contacts.create_contact' @{ input = $contactInput }
    $created.Contact = $contact.data.id

    $leadInput = @{
        name = "HTTP Lead $stamp"
        company = "HTTP Lead Company $stamp"
        title = 'Process Manager'
        phone = '13800000007'
        email = "crm-http-lead-$stamp@example.invalid"
        source = 'Trade Show'
        status = 'New'
        owner = $salesEmail
        interest = 'Advanced packaging inspection'
        firstContactNote = 'HTTP acceptance'
        nextAction = 'Convert lead'
        nextActionDue = '2026-08-20'
        activities = @()
    }
    $lead = Invoke-CrmPost $salesSession 'rayher_crm.api.v1.leads.create_lead' @{ input = $leadInput }
    $created.Lead = $lead.data.id

    $conversionInput = @{
        newAccount = @{
            name = "HTTP Converted Account $stamp"
            shortName = "HTTP Converted $stamp"
            segment = 'Advanced Packaging'
            tier = 'A'
            city = 'Shanghai'
            region = 'East China'
            owner = 'Administrator'
        }
        newSite = @{
            name = "HTTP Converted Site $stamp"
            city = 'Shanghai'
            type = 'Fab'
            process = 'Advanced Packaging'
            status = [string]::Concat([char]0x91CF, [char]0x4EA7)
        }
        newContact = @{
            name = "HTTP Converted Contact $stamp"
            title = 'Process Manager'
            department = 'Process Engineering'
            phone = '13800000008'
            email = "crm-http-converted-$stamp@example.invalid"
            relationship = 'Developing'
            status = 'Active'
            owner = 'Administrator'
        }
        opportunityTitle = "HTTP Opportunity $stamp"
        opportunityAmount = '100000.50'
        opportunityCloseDate = '2026-12-31'
        opportunityOwner = 'Administrator'
        toolType = 'Inspection'
        qualificationConfirmed = $true
    }
    $assignmentStatus = 0
    try {
        Invoke-CrmPost $salesSession 'rayher_crm.api.v1.leads.convert_lead' @{
            id = $created.Lead; input = $conversionInput
        } | Out-Null
    } catch { $assignmentStatus = [int]$_.Exception.Response.StatusCode }
    if ($assignmentStatus -ne 403) { throw "Expected HTTP 403 when Sales assigns an Opportunity to Administrator, got $assignmentStatus." }
    $conversionInput.opportunityOwner = $salesEmail
    $conversion = Invoke-CrmPost $salesSession 'rayher_crm.api.v1.leads.convert_lead' @{
        id = $created.Lead
        input = $conversionInput
    }
    $created.Opportunity = $conversion.data.opportunityId
    $created.ConversionAccount = $conversion.data.accountId
    $created.ConversionContact = $conversion.data.contactId
    if ($conversion.data.lead.id -ne $created.Lead) { throw 'Lead conversion response omitted or changed the canonical Lead.' }
    $converted360 = Invoke-RestMethod -Uri "$BaseUrl/api/method/rayher_crm.api.v1.accounts.get_account_360?id=$($created.ConversionAccount)" -WebSession $salesSession
    $created.ConversionSite = $converted360.message.data.sites[0].id

    $list = Invoke-RestMethod -Uri "$BaseUrl/api/method/rayher_crm.api.v1.accounts.list_accounts?search=HTTP%20Account%20$stamp&page=1&pageSize=20" -WebSession $salesSession
    if ($list.message.meta.total -lt 1) { throw 'HTTP scoped Account list did not return the created record.' }

    $scopeStatus = 0
    try {
        Invoke-RestMethod -Uri "$BaseUrl/api/method/rayher_crm.api.v1.accounts.get_account_360?id=$($created.ForeignAccount)" -WebSession $salesSession | Out-Null
    } catch {
        $scopeStatus = [int]$_.Exception.Response.StatusCode
    }
    if ($scopeStatus -ne 403) { throw "Expected HTTP 403 for foreign Account detail, got $scopeStatus." }

    Write-Output 'Stage 5B authenticated HTTP acceptance passed: create/list/update/409/scope-403/assignment-403/convert.'
} finally {
    $adminPassword = $null
    $salesPassword = $null
    if ($created.Lead -and $created.Opportunity) {
        $setValueArgs = "['Lead',$(ConvertTo-PythonStringLiteral $created.Lead),'custom_crm_converted_opportunity',None]"
        & docker compose @composeArgs exec -T backend bench --site $SiteName execute frappe.db.set_value --args $setValueArgs | Out-Null
        if ($LASTEXITCODE -ne 0) { throw 'Cleanup failed while unlinking the converted Opportunity.' }
    }
    foreach ($docType in @('CRM Opportunity History', 'CRM Opportunity Stage History', 'CRM Opportunity Probability History', 'CRM Opportunity Internal Validation')) {
        Remove-TestChildren $docType 'opportunity' $created.Opportunity
    }
    Remove-TestDoc 'CRM Opportunity' $created.Opportunity
    Remove-TestDoc 'Lead' $created.Lead
    Remove-TestDoc 'Contact' $created.ConversionContact
    Remove-TestDoc 'Address' $created.ConversionSite
    Remove-TestDoc 'Customer' $created.ConversionAccount
    Remove-TestDoc 'Contact' $created.Contact
    Remove-TestDoc 'Customer' $created.Account
    Remove-TestDoc 'Customer' $created.ForeignAccount
    Remove-TestDoc 'User' $created.User
}
