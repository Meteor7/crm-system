param(
    [string]$ProjectName = 'rayher-crm-stage1-tests',
    [string]$SiteName = 'rayher-crm.test',
    [string]$EnvFile = 'backend/test.env.example',
    [string]$ComposeFile = 'backend/compose.yaml'
)

# The daily CRM jobs (DDL reminders, quotation expiry) only run when Frappe's scheduler is on.
# A new site starts with it off, and `bench run-tests` cannot observe the real setting because it
# switches the scheduler off for the duration of the run, so this check runs against the live site
# before the tests do. compose.yaml's install-app step is what turns it on.

$ErrorActionPreference = 'Stop'

$composeArgs = @('compose', '--project-name', $ProjectName, '--env-file', $EnvFile, '-f', $ComposeFile, 'exec', '-T', 'backend')

function Invoke-InBackend {
    param([string]$Label, [string[]]$CommandArgs)
    $previous = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    $output = & docker @composeArgs @CommandArgs 2>&1
    $exit = $LASTEXITCODE
    $ErrorActionPreference = $previous
    $text = ($output | ForEach-Object { "$_" }) -join "`n"
    if ($exit -ne 0) {
        throw "Scheduler contract failed: $Label exited $exit`n$text"
    }
    return $text
}

$status = Invoke-InBackend 'bench scheduler status' @('bench', '--site', $SiteName, 'scheduler', 'status')
if ($status -notmatch "(?m)^Scheduler is enabled for site $([regex]::Escape($SiteName))\s*$") {
    throw "Scheduler contract failed: Frappe's scheduler is not enabled on $SiteName, so the daily CRM jobs never run. bench said: $status. Run 'bench --site $SiteName enable-scheduler' (compose.yaml's install-app step does this on every start)."
}

# `bench execute` prints nothing for a False return, so ask Python directly. is_scheduler_inactive
# also covers pause_scheduler and maintenance_mode in site_config.json. Frappe's logger resolves
# ../logs from the working directory, so the probe runs inside sites/ with sites_path='.'.
$probe = @(
    'import frappe',
    'from frappe.utils.scheduler import is_scheduler_inactive',
    "frappe.init(site='$SiteName', sites_path='.')",
    'frappe.connect()',
    "print('scheduler_inactive=' + str(is_scheduler_inactive()))"
) -join "`n"
$composeArgs = $composeArgs[0..($composeArgs.Length - 2)] + @('-w', '/home/frappe/frappe-bench/sites', 'backend')
$inactive = Invoke-InBackend 'scheduler probe' @('../env/bin/python', '-c', $probe)
if ($inactive -notmatch '(?m)^scheduler_inactive=False\s*$') {
    throw "Scheduler contract failed: the scheduler is inactive on $SiteName (pause_scheduler, maintenance_mode or disabled). Probe output: $inactive"
}

Write-Output "Scheduler contract passed: enabled and active on $SiteName."
