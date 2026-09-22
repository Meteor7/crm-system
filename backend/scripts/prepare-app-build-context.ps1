#Requires -Version 7.0

[CmdletBinding()]
param(
    [string]$SourceDirectory = (Join-Path (Split-Path -Parent $PSScriptRoot) 'apps/rayher_crm'),
    [string]$OutputArchive = (Join-Path (Split-Path -Parent $PSScriptRoot) 'build/rayher_crm.zip'),
    [switch]$IncludeTests
)

$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.IO.Compression
Add-Type -AssemblyName System.IO.Compression.FileSystem

function Test-ArchiveEntryIncluded {
    param([string]$RelativePath)

    if ($RelativePath -match '(^|/)(__pycache__|[^/]+\.egg-info)/' -or $RelativePath -match '\.py[co]$') {
        return $false
    }
    return $IncludeTests -or ($RelativePath -notmatch '(^|/)tests?/|(^|/)test_[^/]+\.py$|(^|/)conftest\.py$')
}

$sourceRoot = (Resolve-Path -LiteralPath $SourceDirectory).Path
$backendRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
$buildRoot = Join-Path $backendRoot 'build'
$resolvedOutput = [IO.Path]::GetFullPath($OutputArchive)
$pathComparison = if ($IsWindows) { [StringComparison]::OrdinalIgnoreCase } else { [StringComparison]::Ordinal }

if (-not $resolvedOutput.StartsWith($buildRoot + [IO.Path]::DirectorySeparatorChar, $pathComparison)) {
    throw 'Build archive must remain inside backend/build.'
}

New-Item -ItemType Directory -Path $buildRoot -Force | Out-Null

if (Test-Path -LiteralPath $resolvedOutput) {
    $existing = Get-Item -LiteralPath $resolvedOutput -Force
    if ($existing.PSIsContainer -or ($existing.Attributes -band [IO.FileAttributes]::ReparsePoint)) {
        throw 'Existing build archive is not a regular file.'
    }
}

$protectedMarker = '%TSD-Header-###%'
$textExtensions = @('.py', '.toml', '.in', '.rst', '.txt', '.json', '.csv', '.md', '.html', '.css', '.js', '.svg', '.xml', '.yml', '.yaml', '.map', '.ts', '.tsx', '.vue', '.sh', '.ps1', '.jinja', '.jinja2')
$strictUtf8 = [Text.UTF8Encoding]::new($false, $true)

function Assert-SafeSourceFile {
    param([IO.FileInfo]$File)

    if ($File.Attributes -band [IO.FileAttributes]::ReparsePoint) {
        throw "Reparse points are forbidden in app source: $($File.FullName)"
    }
    $bytes = [IO.File]::ReadAllBytes($File.FullName)
    $prefixLength = [Math]::Min(18, $bytes.Length)
    $prefix = if ($prefixLength -gt 0) { [Text.Encoding]::ASCII.GetString($bytes, 0, $prefixLength) } else { '' }
    if ($prefix.StartsWith($protectedMarker)) {
        throw "Protected wrapper remains in app source: $($File.FullName)"
    }
    if ($textExtensions -contains $File.Extension.ToLowerInvariant() -and ($bytes -contains 0)) {
        throw "Null byte remains in text app source: $($File.FullName)"
    }
    return ,$bytes
}

function ConvertTo-ReproducibleBytes {
    param(
        [string]$Path,
        [byte[]]$Bytes
    )

    if ($textExtensions -notcontains [IO.Path]::GetExtension($Path).ToLowerInvariant()) {
        return ,$Bytes
    }
    $text = $strictUtf8.GetString($Bytes).Replace("`r`n", "`n").Replace("`r", "`n")
    return ,$strictUtf8.GetBytes($text)
}

$frontendContractScript = Join-Path $backendRoot 'tests/frappe-frontend-contract.ps1'
$powerShellExecutable = Join-Path $PSHOME $(if ($IsWindows) { 'pwsh.exe' } else { 'pwsh' })
& $powerShellExecutable -NoProfile -File $frontendContractScript -BackendRoot $backendRoot -VerifyRebuild
if ($LASTEXITCODE -ne 0) {
    throw "Frappe frontend rebuild verification failed with exit code $LASTEXITCODE."
}

$repositoryRootOutput = @(& git -C $sourceRoot rev-parse --show-toplevel)
if ($LASTEXITCODE -ne 0 -or $repositoryRootOutput.Count -ne 1) {
    throw 'Could not resolve the Git repository root for the app source.'
}
$repositoryRoot = (Resolve-Path -LiteralPath $repositoryRootOutput[0]).Path
$repositoryPrefix = $repositoryRoot + [IO.Path]::DirectorySeparatorChar
if (-not $sourceRoot.StartsWith($repositoryPrefix, $pathComparison)) {
    throw 'App source must remain inside the Git repository.'
}
$sourceRepositoryPath = $sourceRoot.Substring($repositoryPrefix.Length).Replace('\', '/')
$trackedPrefix = "$sourceRepositoryPath/"
$trackedOutput = (& git -C $repositoryRoot -c core.quotePath=false ls-files -z -- $sourceRepositoryPath) -join ''
if ($LASTEXITCODE -ne 0) {
    throw 'Could not enumerate tracked app source.'
}
if ([string]::IsNullOrEmpty($trackedOutput)) {
    throw 'No Git-tracked app source was found.'
}

$sourceFileMap = [Collections.Generic.Dictionary[string, byte[]]]::new([StringComparer]::Ordinal)
$trackedPaths = [Collections.Generic.HashSet[string]]::new([StringComparer]::Ordinal)
foreach ($trackedPath in ($trackedOutput -split "`0" | Where-Object { $_ })) {
    $normalizedPath = $trackedPath.Replace('\', '/')
    if (-not $normalizedPath.StartsWith($trackedPrefix, [StringComparison]::Ordinal)) {
        throw "Tracked file escaped the app root: $normalizedPath"
    }
    $relativePath = $normalizedPath.Substring($trackedPrefix.Length)
    if (-not $trackedPaths.Add($relativePath)) {
        throw "Duplicate tracked app path; resolve the Git index before packaging: $relativePath"
    }
    $filePath = Join-Path $repositoryRoot ($normalizedPath -replace '/', [IO.Path]::DirectorySeparatorChar)
    if (-not (Test-Path -LiteralPath $filePath -PathType Leaf)) {
        throw "Tracked app source is missing: $normalizedPath"
    }
    $sourceBytes = Assert-SafeSourceFile (Get-Item -LiteralPath $filePath -Force)
    if (-not (Test-ArchiveEntryIncluded $relativePath)) {
        continue
    }
    $sourceFileMap.Add($relativePath, (ConvertTo-ReproducibleBytes $relativePath $sourceBytes))
}

$generatedFrontendRoot = Join-Path $sourceRoot 'rayher_crm/public/crm'
if (Test-Path -LiteralPath $generatedFrontendRoot -PathType Container) {
    Get-ChildItem -LiteralPath $generatedFrontendRoot -Recurse -File -Force | ForEach-Object {
        if (-not $_.FullName.StartsWith($sourceRoot + [IO.Path]::DirectorySeparatorChar, $pathComparison)) {
            throw "Generated frontend file escaped the source root: $($_.FullName)"
        }
        $relativePath = $_.FullName.Substring($sourceRoot.Length + 1).Replace('\', '/')
        if (-not $sourceFileMap.ContainsKey($relativePath)) {
            $sourceBytes = Assert-SafeSourceFile $_
            $sourceFileMap.Add($relativePath, (ConvertTo-ReproducibleBytes $relativePath $sourceBytes))
        }
    }
}
[string[]]$sourceFiles = @($sourceFileMap.Keys)
[Array]::Sort($sourceFiles, [StringComparer]::Ordinal)

if ($sourceFiles.Count -eq 0) {
    throw 'App source is empty.'
}

$temporaryOutput = Join-Path $buildRoot ("{0}.tmp-{1}" -f [IO.Path]::GetFileName($resolvedOutput), [Guid]::NewGuid().ToString('N'))
$primaryError = $null
try {
    $archiveStream = [IO.File]::Open($temporaryOutput, [IO.FileMode]::CreateNew, [IO.FileAccess]::ReadWrite, [IO.FileShare]::None)
    try {
        $archive = [IO.Compression.ZipArchive]::new($archiveStream, [IO.Compression.ZipArchiveMode]::Create, $false)
        try {
            foreach ($relativePath in $sourceFiles) {
                $bytes = $sourceFileMap[$relativePath]
                $entry = $archive.CreateEntry($relativePath, [IO.Compression.CompressionLevel]::Optimal)
                $entry.LastWriteTime = [DateTimeOffset]::new(1980, 1, 1, 0, 0, 0, [TimeSpan]::Zero)
                $entryStream = $entry.Open()
                try {
                    $entryStream.Write($bytes, 0, $bytes.Length)
                }
                finally {
                    $entryStream.Dispose()
                }
            }
        }
        finally {
            $archive.Dispose()
        }
    }
    finally {
        $archiveStream.Dispose()
    }

    $inspection = [IO.Compression.ZipFile]::OpenRead($temporaryOutput)
    try {
        if ($inspection.Entries.Count -ne $sourceFiles.Count) {
            throw "Archive entry count mismatch: expected $($sourceFiles.Count), got $($inspection.Entries.Count)."
        }

        foreach ($entry in $inspection.Entries) {
            $entryStream = $entry.Open()
            $memory = [IO.MemoryStream]::new()
            try {
                $entryStream.CopyTo($memory)
                $bytes = $memory.ToArray()
            }
            finally {
                $memory.Dispose()
                $entryStream.Dispose()
            }

            $prefixLength = [Math]::Min(18, $bytes.Length)
            $prefix = if ($prefixLength -gt 0) { [Text.Encoding]::ASCII.GetString($bytes, 0, $prefixLength) } else { '' }
            if ($prefix.StartsWith($protectedMarker)) {
                throw "Protected wrapper found inside build archive: $($entry.FullName)"
            }
            if ($textExtensions -contains [IO.Path]::GetExtension($entry.FullName).ToLowerInvariant() -and ($bytes -contains 0)) {
                throw "Null byte found inside text archive entry: $($entry.FullName)"
            }
        }
    }
    finally {
        $inspection.Dispose()
    }

    [IO.File]::Move($temporaryOutput, $resolvedOutput, $true)
}
catch {
    $primaryError = $_
    throw
}
finally {
    if (Test-Path -LiteralPath $temporaryOutput -PathType Leaf) {
        try {
            Remove-Item -LiteralPath $temporaryOutput -Force -ErrorAction Stop
        }
        catch {
            if ($null -eq $primaryError) {
                throw
            }
            Write-Warning "Could not remove temporary archive '$temporaryOutput': $($_.Exception.Message)"
        }
    }
}

$archiveItem = Get-Item -LiteralPath $resolvedOutput
Write-Output "Prepared verified app build archive: entries=$($sourceFiles.Count), bytes=$($archiveItem.Length)."
