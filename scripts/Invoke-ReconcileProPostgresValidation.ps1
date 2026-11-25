[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$dockerExe = (Get-Command docker -ErrorAction SilentlyContinue).Source
if (-not $dockerExe) {
    $knownDocker = Join-Path $env:LOCALAPPDATA 'Programs\DockerDesktop\resources\bin\docker.exe'
    if (Test-Path -LiteralPath $knownDocker) { $dockerExe = $knownDocker }
}
if (-not $dockerExe -or -not (Test-Path -LiteralPath $dockerExe)) {
    throw 'Docker CLI is unavailable to this PowerShell user. Start Docker Desktop and retry.'
}
$script:validatedDockerContext = $null
$script:dockerExecutable = $dockerExe

function ConvertTo-WindowsArgument([string]$Value) {
    if ($Value.Length -eq 0) { return '""' }
    if ($Value -notmatch '[\s"]') { return $Value }
    $escaped = $Value -replace '(\\*)"', '$1$1\"'
    $escaped = $escaped -replace '(\\+)$', '$1$1'
    return '"' + $escaped + '"'
}

function Invoke-LocalProcess {
    param(
        [Parameter(Mandatory)][string]$FilePath,
        [Parameter(Mandatory)][string[]]$Arguments,
        [hashtable]$Environment = @{},
        [string]$WorkingDirectory = (Get-Location).ProviderPath
    )
    $start = [System.Diagnostics.ProcessStartInfo]::new()
    $start.FileName = $FilePath
    $start.WorkingDirectory = $WorkingDirectory
    $effectiveArguments = $Arguments
    if ($script:validatedDockerContext -and $FilePath -eq $script:dockerExecutable) {
        $effectiveArguments = @('--context', $script:validatedDockerContext) + $Arguments
    }
    $start.Arguments = (($effectiveArguments | ForEach-Object { ConvertTo-WindowsArgument $_ }) -join ' ')
    $start.UseShellExecute = $false
    $start.CreateNoWindow = $true
    $start.RedirectStandardOutput = $true
    $start.RedirectStandardError = $true
    foreach ($key in $Environment.Keys) { $start.EnvironmentVariables[$key] = [string]$Environment[$key] }
    # The subprocess gets an explicit safe environment without mutating the
    # interactive PowerShell process that launched this script.
    foreach ($key in @(
        'RENDER', 'DATABASE_URL', 'JWT_SECRET', 'ENVIRONMENT', 'PYTHON_DOTENV_DISABLED',
        'RECONCILEPRO_TEST_DATABASE_URL', 'RECONCILEPRO_ALLOW_PRODUCTION_MIGRATION',
        'SUPABASE_URL', 'SUPABASE_KEY', 'SUPABASE_SERVICE_ROLE_KEY',
        'PGHOST', 'PGPORT', 'PGDATABASE', 'PGUSER', 'PGPASSWORD', 'PGSERVICE', 'PGSERVICEFILE',
        'SQLALCHEMY_DATABASE_URI', 'PYTHONPATH', 'PYTEST_ADDOPTS', 'PYTEST_PLUGINS'
    )) {
        if (-not $Environment.ContainsKey($key)) { $start.EnvironmentVariables.Remove($key) }
    }

    $process = [System.Diagnostics.Process]::new()
    $process.StartInfo = $start
    if (-not $process.Start()) { throw "Could not start $FilePath." }
    $stdoutTask = $process.StandardOutput.ReadToEndAsync()
    $stderrTask = $process.StandardError.ReadToEndAsync()
    $process.WaitForExit()
    return [pscustomobject]@{
        ExitCode = $process.ExitCode
        Stdout = $stdoutTask.Result
        Stderr = $stderrTask.Result
    }
}

function Test-MissingDockerContainerResponse([string]$Output, [string]$ExpectedNameOrId) {
    # Accept only Docker's known missing-container/object diagnostics naming
    # the exact generated name or previously verified container ID.
    $prefix = '(?:Error:\s+|Error response from daemon:\s+)'
    $pattern = '(?im)^' + $prefix + 'No such (?:object|container):\s*' +
        [regex]::Escape($ExpectedNameOrId) + '\s*$'
    return $Output.Trim() -match $pattern
}

function Test-MissingDockerVolumeResponse([string]$Output, [string]$ExpectedVolumeName) {
    # Accept only Docker's known missing-volume diagnostics naming
    # the exact expected volume identifier.
    $escaped = [regex]::Escape($ExpectedVolumeName)
    $prefix = '(?:Error:\s+|Error response from daemon:\s+)'
    $pattern = '(?im)^' + $prefix + '(?:No such volume:\s*' + $escaped + '|get\s+' + $escaped + ':\s*no such volume)\s*$'
    return $Output.Trim() -match $pattern
}

function Write-ProcessOutput($Result, [string[]]$Redact = @()) {
    foreach ($source in @($Result.Stdout, $Result.Stderr)) {
        if (-not $source) { continue }
        $safe = $source
        foreach ($secret in $Redact) {
            if ($secret) { $safe = $safe.Replace($secret, '[redacted]') }
        }
        $safe = [regex]::Replace($safe, '(?i)postgres(?:ql)?(?:\+[a-z0-9_]+)?://[^\s''"]+', '[database URL redacted]')
        Write-Host $safe.TrimEnd()
    }
}

function New-TemporaryHexSecret {
    $bytes = New-Object byte[] 32
    $generator = [System.Security.Cryptography.RandomNumberGenerator]::Create()
    try { $generator.GetBytes($bytes) }
    finally { $generator.Dispose() }
    return ([BitConverter]::ToString($bytes).Replace('-', '').ToLowerInvariant())
}

function ConvertFrom-JsonArraySafe([string]$JsonText) {
    $trimmed = $JsonText.Trim()
    if (-not $trimmed.StartsWith('[') -or -not $trimmed.EndsWith(']')) {
        throw 'JSON value is not an array.'
    }
    if ($trimmed -ceq '[]') {
        return ,([object[]]@())
    }
    $parsed = ConvertFrom-Json -InputObject $trimmed -ErrorAction Stop
    if ($null -eq $parsed) {
        return ,([object[]]@())
    }
    # Enumerate through the pipeline so Windows PowerShell 5.1 does not
    # wrap an array result in an extra outer array element.
    $items = @($parsed | ForEach-Object { $_ })
    return ,([object[]]$items)
}

function Format-SanitizedJsonDiagnostic([string]$Label, [string]$JsonText) {
    $trimmed = if ($null -eq $JsonText) { '' } else { $JsonText.Trim() }
    if (-not $trimmed) {
        return "${Label}: type=empty"
    }
    if ($trimmed -ceq 'null') {
        return "${Label}: type=null"
    }
    try {
        if ($trimmed.StartsWith('{') -and $trimmed.EndsWith('}')) {
            $obj = ConvertFrom-Json -InputObject $trimmed -ErrorAction Stop
            if ($null -eq $obj -or $obj -isnot [System.Management.Automation.PSCustomObject]) {
                return "${Label}: type=non-object"
            }
            $propNames = @($obj.PSObject.Properties | ForEach-Object { $_.Name })
            $keyList = if ($propNames.Count -gt 0) { $propNames -join ',' } else { 'none' }
            return "${Label}: type=object, keys=[$keyList]"
        }
        if ($trimmed.StartsWith('[') -and $trimmed.EndsWith(']')) {
            $items = ConvertFrom-JsonArraySafe -JsonText $trimmed
            $itemSummaries = @()
            foreach ($item in $items) {
                if ($null -eq $item) {
                    $itemSummaries += 'null'
                }
                elseif ($item -is [System.Management.Automation.PSCustomObject]) {
                    $itemProps = @($item.PSObject.Properties | ForEach-Object { $_.Name })
                    $parts = @("keys=[$($itemProps -join ',')]")
                    if ($item.PSObject.Properties['Type']) {
                        $parts += "Type=$([string]$item.Type)"
                    }
                    if ($item.PSObject.Properties['Destination']) {
                        $parts += "Destination=$([string]$item.Destination)"
                    }
                    $itemSummaries += '{' + ($parts -join ', ') + '}'
                }
                else {
                    # Do not print scalar values (e.g. HostConfig.Binds) to avoid leaking host paths.
                    $itemSummaries += "scalar($($item.GetType().Name))"
                }
            }
            $itemsText = if ($itemSummaries.Count -gt 0) { $itemSummaries -join '; ' } else { 'none' }
            return "${Label}: type=array, count=$($items.Count), items=[$itemsText]"
        }
        return "${Label}: type=scalar-or-unexpected"
    }
    catch {
        return "${Label}: type=invalid-json"
    }
}

$runId = [guid]::NewGuid().ToString('N')
$containerName = "reconcilepro-pg16-it-$runId"
$databaseName = "reconcilepro_it_$runId"
$databaseUser = 'reconcilepro_test'
$dataDirectory = '/var/lib/postgresql/data'
$labelKey = 'com.reconcilepro.pg-validation-run'
$containerId = $null
$containerCreationAttempted = $false
$createdContainer = $false
$password = New-TemporaryHexSecret
$jwtSecret = New-TemporaryHexSecret
$preexistingVolumeNames = [System.Collections.Generic.HashSet[string]]::new([StringComparer]::OrdinalIgnoreCase)
$overallExit = 1
$cleanupOk = $true
$backendDir = Join-Path (Split-Path -Parent $PSScriptRoot) 'backend'
$pythonExe = Join-Path $backendDir 'venv\Scripts\python.exe'

try {
    if (-not (Test-Path -LiteralPath $pythonExe)) {
        throw 'Backend virtual-environment Python was not found. Create backend\venv before running validation.'
    }

    $alembicIniPath = Join-Path $backendDir 'alembic.ini'
    $migrationsDir = Join-Path $backendDir 'migrations'
    if (-not (Test-Path -LiteralPath $alembicIniPath)) {
        throw "Alembic configuration file was not found at $alembicIniPath."
    }
    if (-not (Test-Path -LiteralPath $migrationsDir)) {
        throw "Alembic migrations directory was not found at $migrationsDir."
    }
    Write-Host 'Validating Alembic configuration and revision head (offline preflight)...'
    $alembicPreflight = Invoke-LocalProcess -FilePath $pythonExe -Arguments @(
        '-m', 'alembic', '-c', 'alembic.ini', 'heads'
    ) -Environment @{ PYTHON_DOTENV_DISABLED = '1' } -WorkingDirectory $backendDir
    Write-ProcessOutput $alembicPreflight
    if ($alembicPreflight.ExitCode -ne 0 -or
        $alembicPreflight.Stdout.Trim() -notmatch '(?m)^0004_import_batch_rev_counts\s+\(head\)\s*$') {
        throw 'Alembic preflight validation failed; expected head 0004_import_batch_rev_counts was not discovered.'
    }
    Write-Host 'Alembic preflight passed (head: 0004_import_batch_rev_counts).'

    # Resolve and reject remote contexts before any command that contacts an engine.
    $context = Invoke-LocalProcess -FilePath $dockerExe -Arguments @('context', 'show')
    if ($context.ExitCode -ne 0 -or $context.Stdout.Trim() -notin @('desktop-linux', 'default')) {
        throw 'The active Docker context is not a supported local Docker Desktop context.'
    }
    $endpoint = Invoke-LocalProcess -FilePath $dockerExe -Arguments @(
        'context', 'inspect', '--format', '{{(index .Endpoints "docker").Host}}', $context.Stdout.Trim()
    )
    if ($endpoint.ExitCode -ne 0 -or $endpoint.Stdout.Trim() -notmatch '^npipe:////\./pipe/docker(?:DesktopLinuxEngine|_engine)$') {
        throw 'The active Docker endpoint is not a local Windows Docker Desktop named pipe.'
    }
    $script:validatedDockerContext = $context.Stdout.Trim()
    Write-Host 'Local Docker Desktop context verified; remote Docker contexts are refused.'

    $daemon = Invoke-LocalProcess -FilePath $dockerExe -Arguments @('info', '--format', '{{.ServerVersion}}|{{.OSType}}')
    if ($daemon.ExitCode -ne 0) {
        Write-ProcessOutput $daemon
        throw 'Docker Desktop is not reachable from this PowerShell session.'
    }
    $daemonValues = $daemon.Stdout.Trim().Split('|')
    if ($daemonValues.Count -lt 2 -or $daemonValues[1] -ne 'linux') {
        throw 'Docker must be running Linux containers for the PostgreSQL 16 image.'
    }
    Write-Host "Docker Engine $($daemonValues[0]) is available (Linux containers)."

    $existing = Invoke-LocalProcess -FilePath $dockerExe -Arguments @('container', 'inspect', $containerName)
    if ($existing.ExitCode -eq 0) {
        throw 'The unique container name unexpectedly already exists; refusing to reuse it.'
    }
    $existingInspectOutput = $existing.Stdout.Trim()
    if (
        ($existingInspectOutput -cne '' -and $existingInspectOutput -cne '[]') -or
        -not (Test-MissingDockerContainerResponse $existing.Stderr $containerName)
    ) {
        throw 'Could not positively verify that the unique container name is unused; refusing to start a container.'
    }
    $volumeSnapshot = Invoke-LocalProcess -FilePath $dockerExe -Arguments @('volume', 'ls', '--quiet')
    if ($volumeSnapshot.ExitCode -ne 0) { throw 'Could not verify existing Docker volumes; refusing to start a container.' }
    foreach ($volumeName in ($volumeSnapshot.Stdout -split '\r?\n' | Where-Object { $_ })) {
        [void]$preexistingVolumeNames.Add($volumeName.Trim())
    }

    $containerCreationAttempted = $true
    $run = Invoke-LocalProcess -FilePath $dockerExe -Arguments @(
        'run', '--detach', '--name', $containerName,
        '--label', "$labelKey=$runId",
        '--publish', '127.0.0.1::5432',
        '--tmpfs', '/var/lib/postgresql/data:rw,noexec,nosuid,size=512m',
        '--env', "POSTGRES_USER=$databaseUser",
        '--env', 'POSTGRES_PASSWORD',
        '--env', "POSTGRES_DB=$databaseName",
        'postgres:16-alpine'
    ) -Environment @{ POSTGRES_PASSWORD = $password }
    if ($run.ExitCode -ne 0) {
        Write-ProcessOutput $run -Redact @($password)
        throw 'Docker could not start the disposable PostgreSQL container.'
    }
    $containerId = $run.Stdout.Trim()
    if ($containerId -notmatch '^[0-9a-f]{64}$') { throw 'Docker returned an unexpected container identifier.' }
    $createdContainer = $true

    $ready = $false
    for ($attempt = 0; $attempt -lt 60; $attempt++) {
        $probe = Invoke-LocalProcess -FilePath $dockerExe -Arguments @(
            'exec', $containerId, 'pg_isready', '-U', $databaseUser, '-d', $databaseName
        )
        if ($probe.ExitCode -eq 0) { $ready = $true; break }
        Start-Sleep -Seconds 2
    }
    if (-not $ready) { throw 'The disposable PostgreSQL server did not become ready within 120 seconds.' }

    $tmpfsResult = Invoke-LocalProcess -FilePath $dockerExe -Arguments @(
        'inspect', '--format', '{{json .HostConfig.Tmpfs}}', $containerId
    )
    if ($tmpfsResult.ExitCode -ne 0) {
        throw 'Could not inspect the container tmpfs configuration; refusing to continue.'
    }
    $tmpfsJson = $tmpfsResult.Stdout.Trim()
    if (-not $tmpfsJson.StartsWith('{') -or -not $tmpfsJson.EndsWith('}') -or
        [regex]::Matches($tmpfsJson, '"' + [regex]::Escape($dataDirectory) + '"').Count -ne 1) {
        throw 'Container tmpfs configuration was missing, malformed, or ambiguous; refusing to continue.'
    }
    try {
        $tmpfsConfiguration = ConvertFrom-Json -InputObject $tmpfsJson -ErrorAction Stop
    }
    catch {
        throw 'Container tmpfs configuration was not valid JSON; refusing to continue.'
    }
    if ($null -eq $tmpfsConfiguration -or $tmpfsConfiguration -isnot [System.Management.Automation.PSCustomObject]) {
        throw 'Container tmpfs configuration had an unexpected structure; refusing to continue.'
    }
    $tmpfsEntries = @($tmpfsConfiguration.PSObject.Properties)
    if ($tmpfsEntries.Count -ne 1 -or $tmpfsEntries[0].Name -cne $dataDirectory -or
        $tmpfsEntries[0].Value -isnot [string]) {
        throw 'Container tmpfs configuration did not identify only the PostgreSQL data directory; refusing to continue.'
    }
    $tmpfsOptions = @(([string]$tmpfsEntries[0].Value -split ',') | ForEach-Object { $_.Trim() })
    $requiredTmpfsOptions = [System.Collections.Generic.HashSet[string]]::new([StringComparer]::OrdinalIgnoreCase)
    foreach ($option in @('rw', 'noexec', 'nosuid', 'size=512m')) { [void]$requiredTmpfsOptions.Add($option) }
    $actualTmpfsOptions = [System.Collections.Generic.HashSet[string]]::new([StringComparer]::OrdinalIgnoreCase)
    foreach ($option in $tmpfsOptions) {
        if (-not $option -or -not $actualTmpfsOptions.Add($option)) {
            throw 'Container tmpfs options were empty or ambiguous; refusing to continue.'
        }
    }
    if ($actualTmpfsOptions.Count -ne $requiredTmpfsOptions.Count -or
        -not $requiredTmpfsOptions.SetEquals($actualTmpfsOptions)) {
        throw 'Container tmpfs options did not match the required rw,noexec,nosuid,size=512m settings.'
    }

    $mountResult = Invoke-LocalProcess -FilePath $dockerExe -Arguments @(
        'inspect', '--format', '{{json .Mounts}}', $containerId
    )
    if ($mountResult.ExitCode -ne 0) {
        throw 'Could not inspect container mounts; refusing to continue.'
    }
    $mountJson = $mountResult.Stdout.Trim()
    $mountDiag = Format-SanitizedJsonDiagnostic -Label '.Mounts' -JsonText $mountJson
    $tmpfsDiag = Format-SanitizedJsonDiagnostic -Label 'HostConfig.Tmpfs' -JsonText $tmpfsJson

    $hostMountDiags = @()
    $hostMountJsons = @{}
    foreach ($hostMountField in @('Binds', 'Mounts')) {
        $hostMountResult = Invoke-LocalProcess -FilePath $dockerExe -Arguments @(
            'inspect', '--format', "{{json .HostConfig.$hostMountField}}", $containerId
        )
        if ($hostMountResult.ExitCode -ne 0) {
            throw "Could not inspect container HostConfig.$hostMountField; refusing to continue."
        }
        $hostMountJson = $hostMountResult.Stdout.Trim()
        $hostMountJsons[$hostMountField] = $hostMountJson
        $hostMountDiags += (Format-SanitizedJsonDiagnostic -Label "HostConfig.$hostMountField" -JsonText $hostMountJson)
    }

    $storageDiagnosticSummary = (@($tmpfsDiag, $mountDiag) + $hostMountDiags) -join ' | '
    Write-Host "Storage inspection structure: $storageDiagnosticSummary"

    foreach ($hostMountField in @('Binds', 'Mounts')) {
        $hostMountJson = $hostMountJsons[$hostMountField]
        if ($hostMountJson -ceq 'null') { continue }
        if (-not $hostMountJson.StartsWith('[') -or -not $hostMountJson.EndsWith(']')) {
            throw "Container HostConfig.$hostMountField had an unexpected structure ($storageDiagnosticSummary); refusing to continue."
        }
        try {
            $parsedHostMounts = ConvertFrom-JsonArraySafe -JsonText $hostMountJson
        }
        catch {
            throw "Container HostConfig.$hostMountField was not valid JSON ($storageDiagnosticSummary); refusing to continue."
        }
        if ($parsedHostMounts.Count -ne 0) {
            throw "Unexpected persistent volume or bind mount found in HostConfig.$hostMountField ($storageDiagnosticSummary); refusing to continue."
        }
    }

    if ($mountJson.StartsWith('{') -and $mountJson.EndsWith('}')) {
        if ([regex]::Matches($mountJson, '"' + [regex]::Escape($dataDirectory) + '"').Count -ne 1) {
            throw "Container mount object map was malformed or ambiguous ($storageDiagnosticSummary); refusing to continue."
        }
        try {
            $parsedMounts = ConvertFrom-Json -InputObject $mountJson -ErrorAction Stop
        }
        catch {
            throw "Container mount information was not valid JSON ($storageDiagnosticSummary); refusing to continue."
        }
        if ($null -eq $parsedMounts -or $parsedMounts -isnot [System.Management.Automation.PSCustomObject]) {
            throw "Container mount information had an unexpected structure ($storageDiagnosticSummary); refusing to continue."
        }
        $mountEntries = @($parsedMounts.PSObject.Properties)
        if ($mountEntries.Count -ne 1 -or $mountEntries[0].Name -cne $dataDirectory -or
            $mountEntries[0].Value -isnot [string] -or [string]$mountEntries[0].Value -cne '') {
            throw "Container mount map did not contain only the expected PostgreSQL tmpfs data directory ($storageDiagnosticSummary); refusing to continue."
        }
    }
    elseif ($mountJson.StartsWith('[') -and $mountJson.EndsWith(']')) {
        try {
            $parsedMountArray = ConvertFrom-JsonArraySafe -JsonText $mountJson
        }
        catch {
            throw "Container mount array was not valid JSON ($storageDiagnosticSummary); refusing to continue."
        }
        # An empty .Mounts array ([]) is valid for --tmpfs because HostConfig.Tmpfs
        # has been independently verified and HostConfig.Binds/Mounts are empty.
        foreach ($mount in $parsedMountArray) {
            if ($null -eq $mount -or $mount -isnot [System.Management.Automation.PSCustomObject] -or
                -not $mount.PSObject.Properties['Type'] -or -not $mount.PSObject.Properties['Destination']) {
                throw "A container mount entry was incomplete or ambiguous ($storageDiagnosticSummary); refusing to continue."
            }
            $mountType = [string]$mount.Type
            $destination = [string]$mount.Destination
            if ($mountType -cne 'tmpfs') {
                throw "Rejected non-tmpfs mount type '$mountType' in .Mounts ($storageDiagnosticSummary); refusing to continue."
            }
            if ($destination.Length -gt 1) { $destination = $destination.TrimEnd('/') }
            if ($destination -cne $dataDirectory) {
                throw "Rejected unexpected tmpfs destination '$destination' in .Mounts ($storageDiagnosticSummary); refusing to continue."
            }
        }
    }
    else {
        throw "Container mount information had an unsupported format ($storageDiagnosticSummary); refusing to continue."
    }

    $published = Invoke-LocalProcess -FilePath $dockerExe -Arguments @('port', $containerId, '5432/tcp')
    $portMatch = [regex]::Match($published.Stdout.Trim(), '^127\.0\.0\.1:(\d+)$')
    if ($published.ExitCode -ne 0 -or -not $portMatch.Success) {
        throw 'The database port was not published exclusively on 127.0.0.1.'
    }
    $hostPort = $portMatch.Groups[1].Value
    if ($hostPort -eq '5432') { throw 'Docker selected the standard PostgreSQL host port; refusing to risk the existing Windows service.' }

    $version = Invoke-LocalProcess -FilePath $dockerExe -Arguments @(
        'exec', $containerId, 'psql', '-U', $databaseUser, '-d', $databaseName,
        '-Atqc', 'SHOW server_version'
    )
    if ($version.ExitCode -ne 0 -or $version.Stdout.Trim() -notmatch '^16\.') {
        throw 'The temporary database did not report PostgreSQL 16.'
    }
    Write-Host "Disposable PostgreSQL version: $($version.Stdout.Trim())"
    Write-Host "Container is loopback-only at 127.0.0.1:$hostPort; data directory is tmpfs and no persistent volume is mounted."

    $url = "postgresql+psycopg://${databaseUser}:${password}@127.0.0.1:${hostPort}/${databaseName}"
    $childEnvironment = @{
        DATABASE_URL = $url
        RECONCILEPRO_TEST_DATABASE_URL = $url
        ENVIRONMENT = 'integration'
        PYTHON_DOTENV_DISABLED = '1'
        JWT_SECRET = $jwtSecret
        RECONCILEPRO_PG_RUN_ID = $runId
    }

    Push-Location $backendDir
    try {
        Write-Host 'Applying Alembic revisions 0001 through 0004 to the disposable database...'
        $migration = Invoke-LocalProcess -FilePath $pythonExe -Arguments @(
            '-m', 'alembic', '-c', 'alembic.ini', 'upgrade', 'head'
        ) -Environment $childEnvironment -WorkingDirectory $backendDir
        Write-ProcessOutput $migration -Redact @($url, $password, $jwtSecret)
        if ($migration.ExitCode -ne 0) { throw "Disposable PostgreSQL migration failed with exit code $($migration.ExitCode)." }

        Write-Host 'Running PostgreSQL-only integration tests (SQLite tests/conftest.py is excluded)...'
        $testEnvironment = @{} + $childEnvironment
        $testEnvironment['RECONCILEPRO_PG_INTEGRATION'] = '1'
        $tests = Invoke-LocalProcess -FilePath $pythonExe -Arguments @(
            '-m', 'pytest', '-c', 'pytest.ini', '--confcutdir=postgres_integration_tests',
            'postgres_integration_tests', '-q', '-p', 'no:cacheprovider'
        ) -Environment $testEnvironment -WorkingDirectory $backendDir
        Write-ProcessOutput $tests -Redact @($url, $password, $jwtSecret)
        if ($tests.ExitCode -ne 0) { throw "PostgreSQL integration tests failed with exit code $($tests.ExitCode)." }
        $overallExit = 0
    }
    finally {
        Pop-Location
    }
}
catch {
    Write-Host "ERROR: $($_.Exception.Message)"
    $overallExit = 1
}
finally {
    if (-not $containerCreationAttempted) {
        Write-Host 'Container creation was not attempted; skipping Docker cleanup recovery.'
    }
    elseif (-not $script:validatedDockerContext) {
        Write-Host 'ERROR: Validated local Docker context is unavailable; refusing unvalidated Docker cleanup.'
        $cleanupOk = $false
    }
    else {
    if (-not $createdContainer) {
        try {
            $recovery = Invoke-LocalProcess -FilePath $dockerExe -Arguments @(
                'inspect', '--format', "{{.Id}}|{{index .Config.Labels `"$labelKey`"}}", $containerName
            )
            if ($recovery.ExitCode -eq 0) {
                $parts = $recovery.Stdout.Trim().Split('|')
                if ($parts.Count -eq 2 -and $parts[1] -eq $runId -and $parts[0] -match '^[0-9a-f]{64}$') {
                    $containerId = $parts[0]
                    $createdContainer = $true
                }
                else {
                    Write-Host 'ERROR: Docker found a container by the unique task name, but its identity/ownership label could not be verified.'
                    $cleanupOk = $false
                }
            }
            elseif (
                ($recovery.Stdout.Trim() -ceq '' -or $recovery.Stdout.Trim() -ceq '[]') -and
                (Test-MissingDockerContainerResponse $recovery.Stderr $containerName)
            ) {
                # Only Docker's specific missing-object response proves that
                # the task container was never created (or is already absent).
                Write-Host 'No task-owned container was found during cleanup recovery.'
            }
            else {
                Write-Host 'ERROR: Docker could not determine whether the task container exists; cleanup is unconfirmed.'
                $cleanupOk = $false
            }
        }
        catch {
            Write-Host 'ERROR: Could not check whether Docker created the uniquely labelled container before returning an error.'
            $cleanupOk = $false
        }
    }
    if ($createdContainer -and $containerId) {
        try {
            $identity = Invoke-LocalProcess -FilePath $dockerExe -Arguments @(
                'inspect', '--format', "{{.Id}}|{{index .Config.Labels `"$labelKey`"}}|{{json .Mounts}}", $containerId
            )
            $expectedLabel = "$containerId|$runId|"
            if ($identity.ExitCode -eq 0 -and $identity.Stdout.Trim().StartsWith($expectedLabel, [StringComparison]::OrdinalIgnoreCase)) {
                $mountJson = ($identity.Stdout.Trim() -split '\|', 3)[2]
                $containerRemove = Invoke-LocalProcess -FilePath $dockerExe -Arguments @('container', 'rm', '--force', '--volumes', $containerId)
                if ($containerRemove.ExitCode -ne 0) {
                    Write-ProcessOutput $containerRemove
                    $cleanupOk = $false
                }
                else {
                    try {
                        $trimmedMountJson = $mountJson.Trim()
                        $cleanupMountDiag = Format-SanitizedJsonDiagnostic -Label 'Cleanup.Mounts' -JsonText $trimmedMountJson
                        if ($trimmedMountJson.StartsWith('{') -and $trimmedMountJson.EndsWith('}')) {
                            if ([regex]::Matches($trimmedMountJson, '"' + [regex]::Escape($dataDirectory) + '"').Count -ne 1) {
                                throw "Unexpected mount object keys during cleanup ($cleanupMountDiag)."
                            }
                            $parsedCleanupMounts = ConvertFrom-Json -InputObject $trimmedMountJson -ErrorAction Stop
                            if ($null -eq $parsedCleanupMounts -or $parsedCleanupMounts -isnot [System.Management.Automation.PSCustomObject]) {
                                throw "Unexpected mount object structure during cleanup ($cleanupMountDiag)."
                            }
                            $cleanupMountEntries = @($parsedCleanupMounts.PSObject.Properties)
                            if ($cleanupMountEntries.Count -ne 1 -or $cleanupMountEntries[0].Name -cne $dataDirectory -or
                                $cleanupMountEntries[0].Value -isnot [string] -or [string]$cleanupMountEntries[0].Value -cne '') {
                                throw "Unexpected mount object map entries during cleanup ($cleanupMountDiag)."
                            }
                            $mounts = @()
                        }
                        elseif ($trimmedMountJson.StartsWith('[') -and $trimmedMountJson.EndsWith(']')) {
                            $mounts = ConvertFrom-JsonArraySafe -JsonText $trimmedMountJson
                        }
                        else {
                            throw "Unexpected mount inspection format during cleanup ($cleanupMountDiag)."
                        }
                        foreach ($mount in $mounts) {
                            if ($null -eq $mount -or $mount -isnot [System.Management.Automation.PSCustomObject] -or
                                -not $mount.PSObject.Properties['Type']) {
                                throw "Incomplete or unexpected mount entry during cleanup ($cleanupMountDiag)."
                            }
                            $mountType = [string]$mount.Type
                            if ($mountType -ceq 'tmpfs') {
                                if (-not $mount.PSObject.Properties['Destination']) {
                                    throw "Tmpfs mount entry missing Destination during cleanup ($cleanupMountDiag)."
                                }
                                $destination = [string]$mount.Destination
                                if ($destination.Length -gt 1) { $destination = $destination.TrimEnd('/') }
                                if ($destination -cne $dataDirectory) {
                                    throw "Unexpected tmpfs mount destination '$destination' during cleanup ($cleanupMountDiag)."
                                }
                                continue
                            }
                            if ($mountType -cne 'volume') {
                                throw "Rejected unsupported mount type '$mountType' during cleanup ($cleanupMountDiag)."
                            }
                            if (-not $mount.PSObject.Properties['Name']) {
                                throw "Volume mount entry missing Name during cleanup ($cleanupMountDiag)."
                            }
                            $volumeName = [string]$mount.Name
                            # Remove only an anonymous volume attached to this run's
                            # container if any remained after container rm --volumes.
                            if ($volumeName -notmatch '^[0-9a-f]{64}$') { throw 'Unexpected non-anonymous volume found; left untouched.' }
                            if ($preexistingVolumeNames.Contains($volumeName)) { throw 'Volume existed before this run; left untouched.' }
                            $volumeExists = Invoke-LocalProcess -FilePath $dockerExe -Arguments @('volume', 'inspect', $volumeName)
                            if ($volumeExists.ExitCode -ne 0) {
                                $volumeStdout = $volumeExists.Stdout.Trim()
                                if (
                                    ($volumeStdout -ceq '' -or $volumeStdout -ceq '[]') -and
                                    (Test-MissingDockerVolumeResponse $volumeExists.Stderr $volumeName)
                                ) {
                                    continue
                                }
                                throw "Could not confirm whether disposable volume $volumeName is absent; cleanup is unconfirmed."
                            }
                            $volumeUsers = Invoke-LocalProcess -FilePath $dockerExe -Arguments @(
                                'ps', '--all', '--quiet', '--filter', "volume=$volumeName"
                            )
                            if ($volumeUsers.ExitCode -ne 0 -or $volumeUsers.Stdout.Trim()) { throw 'Volume is still attached; left untouched.' }
                            $volumeRemove = Invoke-LocalProcess -FilePath $dockerExe -Arguments @('volume', 'rm', $volumeName)
                            if ($volumeRemove.ExitCode -ne 0) { throw 'Could not remove the task-created anonymous volume.' }
                        }
                    }
                    catch {
                        Write-Host "ERROR: Disposable volume cleanup check failed: $($_.Exception.Message)"
                        $cleanupOk = $false
                    }
                }
                $remaining = Invoke-LocalProcess -FilePath $dockerExe -Arguments @('container', 'inspect', $containerId)
                $remainingStdout = $remaining.Stdout.Trim()
                if (
                    $remaining.ExitCode -eq 0 -or
                    ($remainingStdout -cne '' -and $remainingStdout -cne '[]') -or
                    -not (Test-MissingDockerContainerResponse $remaining.Stderr $containerId)
                ) {
                    $cleanupOk = $false
                }
            }
            else {
                Write-Host 'ERROR: Cleanup refused because the container identity/ownership label could not be verified.'
                $cleanupOk = $false
            }
        }
        catch {
            Write-Host 'ERROR: Docker cleanup inspection or removal failed; cleanup is unconfirmed.'
            $cleanupOk = $false
        }
    }
    }
}

if ($cleanupOk) { Write-Host 'Disposable PostgreSQL container cleanup: confirmed.' }
else { Write-Host 'ERROR: Disposable PostgreSQL cleanup could not be fully confirmed; inspect only the task-specific container before retrying cleanup.' }
if ($overallExit -eq 0 -and $cleanupOk) { Write-Host 'PostgreSQL validation completed successfully.' }
else { Write-Host 'PostgreSQL validation did not complete successfully.' }
$scriptExit = if ($overallExit -eq 0 -and $cleanupOk) { 0 } else { 1 }
Write-Host "Runner exit status: $scriptExit"
$global:LASTEXITCODE = $scriptExit
