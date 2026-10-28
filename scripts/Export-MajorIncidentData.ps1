<#
.SYNOPSIS
    Read-only export of incidents, changes, problems and post-incident actions from ServiceNow (Table API) or Jira Service Management
    (REST search), written as the CSV files that mickit reads.

.DESCRIPTION
    Only GET requests. Nothing is created, updated or deleted in the ITSM tool. Use an account with read access to the tables or projects.

    ServiceNow (-Platform ServiceNow), Table API GET /api/now/table/<table> with sysparm_query, sysparm_fields, sysparm_limit and
    sysparm_offset paging, and sysparm_display_value=true so priority, CI, service and group come out as names:
      - incident:        number, priority, opened_at, resolved_at, business_service, cmdb_ci, assignment_group, major_incident_state,
                         problem_id, caused_by, contact_type, short_description, plus the fields you name for impact start, detected,
                         acknowledged, mitigated, customer impact, the three roles and the review date (these are usually custom u_ fields);
      - change_request:  number, business_service, cmdb_ci, start_date, end_date, type, state, short_description;
      - problem:         number, first_reported_by_task, cause_notes, state;
      - problem_task:    number, problem, short_description, assigned_to, due_date, state, closed_at;
      - sys_journal_field (with -IncludeWorkNotes): the work notes and comments of the major incidents, written as timeline.csv.
    Set the integration user's date format to yyyy-MM-dd and its time zone to the one you report in: display values follow them.

    Jira Service Management (-Platform Jira), GET /rest/api/3/search/jql with jql, fields, maxResults and nextPageToken paging
    (the enhanced search that replaces /rest/api/3/search on Jira Cloud). Incidents, changes and problems are read from the service project
    by issue type; the times, roles, affected service and change window live in custom fields, so pass their ids (customfield_NNNNN).

    Not exported here: monitoring alerts (export first-fired times per service or host from SolarWinds, Grafana, Dynatrace, Datadog or
    Azure Monitor into alerts.csv) and the stakeholder updates (from the communication plan, the status page or the mailbox, into comms.csv).
    See docs/data-format.md.

.EXAMPLE
    $cred = Get-Credential
    .\scripts\Export-MajorIncidentData.ps1 -Platform ServiceNow -InstanceUrl https://contoso.service-now.com -Credential $cred `
        -From 2026-07-01 -To 2026-09-30 -DetectedField u_detected -MitigatedField u_service_restored -IncludeWorkNotes -OutputFolder .\data

.EXAMPLE
    $cred = Get-Credential   # user: your Atlassian e-mail, password: an API token
    .\scripts\Export-MajorIncidentData.ps1 -Platform Jira -InstanceUrl https://contoso.atlassian.net -Credential $cred -JiraProject ITOPS `
        -From 2026-07-01 -To 2026-09-30 -MajorField customfield_10120 -ServiceField customfield_10110 -OutputFolder .\data
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory)] [ValidateSet('ServiceNow', 'Jira')] [string] $Platform,
    [Parameter(Mandatory)] [string] $InstanceUrl,
    [Parameter(Mandatory)] [pscredential] $Credential,
    [Parameter(Mandatory)] [datetime] $From,
    [Parameter(Mandatory)] [datetime] $To,
    [string] $OutputFolder = '.\data',
    [ValidateRange(1, 4)] [int] $MaxPriority = 3,
    [int] $ChangeLookbackDays = 3,
    # fields that are not standard in either tool: name your own
    [string] $ImpactStartField = '',
    [string] $DetectedField = '',
    [string] $AcknowledgedField = '',
    [string] $MitigatedField = '',
    [string] $CustomerImpactField = '',
    [string] $CommanderField = '',
    [string] $CommsLeadField = '',
    [string] $TechLeadField = '',
    [string] $ReviewDateField = '',
    [switch] $IncludeWorkNotes,
    # Jira only
    [string] $JiraProject = '',
    [string] $MajorField = '',
    [string] $ServiceField = '',
    [string] $ChangeStartField = '',
    [string] $ChangeEndField = '',
    [int] $PageSize = 100
)

$ErrorActionPreference = 'Stop'
$base = $InstanceUrl.TrimEnd('/')
$pair = '{0}:{1}' -f $Credential.UserName, $Credential.GetNetworkCredential().Password
$headers = @{ Authorization = 'Basic ' + [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($pair)); Accept = 'application/json' }
New-Item -ItemType Directory -Force -Path $OutputFolder | Out-Null
$f = $From.ToString('yyyy-MM-dd'); $t = $To.ToString('yyyy-MM-dd')

function Get-Json([string] $uri) { Invoke-RestMethod -Method Get -Uri $uri -Headers $headers }
function Write-Out([object[]] $rows, [string] $name) {
    $path = Join-Path $OutputFolder $name
    $rows | Export-Csv -Path $path -NoTypeInformation -Encoding utf8
    Write-Host ("{0,5} rows -> {1}" -f @($rows).Count, $path)
}
function Val($obj, [string] $field) {
    if (-not $field) { return '' }
    $v = $obj.$field
    if ($null -eq $v) { return '' }
    if ($v -is [array]) { return (($v | ForEach-Object { if ($_.value) { $_.value } elseif ($_.name) { $_.name } elseif ($_.displayName) { $_.displayName } else { "$_" } }) -join '; ') }
    if ($v.PSObject.Properties['displayName']) { return $v.displayName }
    if ($v.PSObject.Properties['value']) { return $v.value }
    if ($v.PSObject.Properties['name']) { return $v.name }
    return "$v"
}

# ------------------------------------------------------------------ ServiceNow
function Get-SnTable([string] $table, [string] $query, [string[]] $fields) {
    $out = @(); $offset = 0
    $q = [uri]::EscapeDataString($query)
    $fl = ($fields | Where-Object { $_ } | Select-Object -Unique) -join ','
    do {
        $uri = "$base/api/now/table/${table}?sysparm_query=$q&sysparm_fields=$fl&sysparm_display_value=true&sysparm_exclude_reference_link=true" +
               "&sysparm_limit=$PageSize&sysparm_offset=$offset"
        $page = @((Get-Json $uri).result)
        $out += $page; $offset += $PageSize
    } while ($page.Count -eq $PageSize)
    return $out
}

if ($Platform -eq 'ServiceNow') {
    $range = "javascript:gs.dateGenerate('$f','00:00:00')@javascript:gs.dateGenerate('$t','23:59:59')"
    $custom = @($ImpactStartField, $DetectedField, $AcknowledgedField, $MitigatedField, $CustomerImpactField, $CommanderField, $CommsLeadField,
                $TechLeadField, $ReviewDateField)
    $inc = Get-SnTable 'incident' "opened_atBETWEEN$range^priority<=$MaxPriority^ORDERBYopened_at" (@('sys_id', 'number', 'priority', 'opened_at',
        'resolved_at', 'business_service', 'cmdb_ci', 'assignment_group', 'major_incident_state', 'problem_id', 'caused_by', 'contact_type',
        'short_description') + $custom)
    Write-Out ($inc | ForEach-Object { [pscustomobject] @{
        'Number' = $_.number; 'Priority' = $_.priority; 'Opened' = $_.opened_at; 'Impact start' = (Val $_ $ImpactStartField)
        'Detected' = (Val $_ $DetectedField); 'Acknowledged' = (Val $_ $AcknowledgedField); 'Mitigated' = (Val $_ $MitigatedField)
        'Resolved' = $_.resolved_at; 'Business service' = $_.business_service; 'Configuration item' = $_.cmdb_ci
        'Assignment group' = $_.assignment_group; 'Major incident state' = $_.major_incident_state; 'Customer impact' = (Val $_ $CustomerImpactField)
        'Problem' = $_.problem_id; 'Caused by change' = $_.caused_by; 'Incident commander' = (Val $_ $CommanderField)
        'Comms lead' = (Val $_ $CommsLeadField); 'Tech lead' = (Val $_ $TechLeadField); 'Review date' = (Val $_ $ReviewDateField)
        'Detection source' = $_.contact_type; 'Short description' = $_.short_description } }) 'incidents.csv'

    $cf = $From.AddDays(-$ChangeLookbackDays).ToString('yyyy-MM-dd')
    $chg = Get-SnTable 'change_request' "start_dateBETWEENjavascript:gs.dateGenerate('$cf','00:00:00')@javascript:gs.dateGenerate('$t','23:59:59')^ORDERBYstart_date" @(
        'number', 'business_service', 'cmdb_ci', 'start_date', 'end_date', 'type', 'state', 'short_description')
    Write-Out ($chg | ForEach-Object { [pscustomobject] @{ 'Number' = $_.number; 'Business service' = $_.business_service; 'Configuration item' = $_.cmdb_ci
        'Planned start' = $_.start_date; 'Planned end' = $_.end_date; 'Type' = $_.type; 'State' = $_.state; 'Short description' = $_.short_description } }) 'changes.csv'

    $probNums = @($inc | Where-Object { $_.problem_id } | ForEach-Object { $_.problem_id } | Select-Object -Unique)
    $prob = @(); $tasks = @()
    if ($probNums.Count) {
        $prob = Get-SnTable 'problem' ("numberIN" + ($probNums -join ',')) @('number', 'first_reported_by_task', 'cause_notes', 'state')
        $tasks = Get-SnTable 'problem_task' ("problem.numberIN" + ($probNums -join ',')) @('number', 'problem', 'short_description', 'assigned_to',
            'due_date', 'state', 'closed_at')
    }
    Write-Out ($prob | ForEach-Object { [pscustomobject] @{ 'Number' = $_.number; 'Incidents' = $_.first_reported_by_task; 'Root cause' = $_.cause_notes
        'RCA date' = ''; 'State' = $_.state } }) 'problems.csv'
    Write-Out ($tasks | ForEach-Object { [pscustomobject] @{ 'Action ID' = $_.number; 'Problem' = $_.problem; 'Incident' = ''; 'Action' = $_.short_description
        'Owner' = $_.assigned_to; 'Due date' = $_.due_date; 'Status' = $_.state; 'Closed' = $_.closed_at } }) 'problem-actions.csv'

    if ($IncludeWorkNotes) {
        $major = @($inc | Where-Object { $_.priority -match '^1' -or ($_.major_incident_state -and $_.major_incident_state -match 'accepted') })
        $notes = foreach ($m in $major) {
            Get-SnTable 'sys_journal_field' "element_id=$($m.sys_id)^elementINwork_notes,comments^ORDERBYsys_created_on" @('sys_created_on',
                'sys_created_by', 'element', 'value') | ForEach-Object { [pscustomobject] @{ 'Incident' = $m.number; 'Time' = $_.sys_created_on
                'Source' = "ITSM $($_.element)"; 'Actor' = $_.sys_created_by; 'Text' = ($_.value -replace '\s+', ' ') } }
        }
        Write-Out @($notes) 'timeline.csv'
    }
}

# ------------------------------------------------------------------ Jira Service Management
function Get-JiraIssues([string] $jql, [string[]] $fields) {
    $out = @(); $token = $null
    $fl = ($fields | Where-Object { $_ } | Select-Object -Unique) -join ','
    do {
        $uri = "$base/rest/api/3/search/jql?jql=$([uri]::EscapeDataString($jql))&fields=$fl&maxResults=$PageSize"
        if ($token) { $uri += "&nextPageToken=$([uri]::EscapeDataString($token))" }
        $page = Get-Json $uri
        $out += @($page.issues)
        $token = $page.nextPageToken
    } while ($token -and -not $page.isLast)
    return $out
}

if ($Platform -eq 'Jira') {
    if (-not $JiraProject) { throw '-JiraProject is required for Jira' }
    $custom = @($ImpactStartField, $DetectedField, $AcknowledgedField, $MitigatedField, $CustomerImpactField, $CommanderField, $CommsLeadField,
                $TechLeadField, $ReviewDateField, $MajorField, $ServiceField)
    $inc = Get-JiraIssues "project = $JiraProject AND issuetype = Incident AND created >= '$f' AND created <= '$t 23:59' ORDER BY created ASC" (
        @('summary', 'priority', 'created', 'resolutiondate', 'components', 'issuelinks') + $custom)
    Write-Out ($inc | ForEach-Object {
        $x = $_.fields
        $links = @($x.issuelinks | ForEach-Object { if ($_.outwardIssue) { $_.outwardIssue } elseif ($_.inwardIssue) { $_.inwardIssue } })
        $prob = ($links | Where-Object { $_.fields.issuetype.name -eq 'Problem' } | Select-Object -First 1).key
        $chg = ($links | Where-Object { $_.fields.issuetype.name -eq 'Change' } | Select-Object -First 1).key
        [pscustomobject] @{
            'Number' = $_.key; 'Priority' = $x.priority.name; 'Opened' = $x.created; 'Impact start' = (Val $x $ImpactStartField)
            'Detected' = (Val $x $DetectedField); 'Acknowledged' = (Val $x $AcknowledgedField); 'Mitigated' = (Val $x $MitigatedField)
            'Resolved' = $x.resolutiondate; 'Business service' = (Val $x $ServiceField); 'Configuration item' = (($x.components | ForEach-Object { $_.name }) -join '; ')
            'Assignment group' = ''; 'Major incident state' = (Val $x $MajorField); 'Customer impact' = (Val $x $CustomerImpactField)
            'Problem' = $prob; 'Caused by change' = $chg; 'Incident commander' = (Val $x $CommanderField); 'Comms lead' = (Val $x $CommsLeadField)
            'Tech lead' = (Val $x $TechLeadField); 'Review date' = (Val $x $ReviewDateField); 'Detection source' = ''; 'Short description' = $x.summary } }) 'incidents.csv'

    $cf = $From.AddDays(-$ChangeLookbackDays).ToString('yyyy-MM-dd')
    $chg = Get-JiraIssues "project = $JiraProject AND issuetype = Change AND created >= '$cf' AND created <= '$t 23:59'" @('summary', 'components',
        'status', $ChangeStartField, $ChangeEndField, $ServiceField)
    Write-Out ($chg | ForEach-Object { $x = $_.fields; [pscustomobject] @{ 'Number' = $_.key; 'Business service' = (Val $x $ServiceField)
        'Configuration item' = (($x.components | ForEach-Object { $_.name }) -join '; '); 'Planned start' = (Val $x $ChangeStartField)
        'Planned end' = (Val $x $ChangeEndField); 'Type' = ''; 'State' = $x.status.name; 'Short description' = $x.summary } }) 'changes.csv'

    $prob = Get-JiraIssues "project = $JiraProject AND issuetype = Problem AND updated >= '$f'" @('summary', 'status', 'issuelinks', 'subtasks')
    Write-Out ($prob | ForEach-Object { $x = $_.fields; [pscustomobject] @{ 'Number' = $_.key
        'Incidents' = (($x.issuelinks | ForEach-Object { if ($_.outwardIssue) { $_.outwardIssue.key } elseif ($_.inwardIssue) { $_.inwardIssue.key } }) -join '; ')
        'Root cause' = ''; 'RCA date' = ''; 'State' = $x.status.name } }) 'problems.csv'
    $keys = @($prob | ForEach-Object { $_.key })
    $tasks = @()
    if ($keys.Count) {
        $tasks = Get-JiraIssues ("parent in (" + ($keys -join ',') + ")") @('summary', 'assignee', 'duedate', 'status', 'resolutiondate', 'parent')
    }
    Write-Out ($tasks | ForEach-Object { $x = $_.fields; [pscustomobject] @{ 'Action ID' = $_.key; 'Problem' = $x.parent.key; 'Incident' = ''
        'Action' = $x.summary; 'Owner' = $x.assignee.displayName; 'Due date' = $x.duedate; 'Status' = $x.status.name; 'Closed' = $x.resolutiondate } }) 'problem-actions.csv'
}

Write-Host "Add alerts.csv and comms.csv from the monitoring and communication tools, and settings.json with your targets; then run:"
Write-Host "  python -m mickit review $OutputFolder"
