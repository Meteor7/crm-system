#Requires -Version 7.0

[CmdletBinding()]
param(
    [string]$BackendRoot = (Split-Path -Parent $PSScriptRoot),
    [string]$ArchivePath = (Join-Path (Split-Path -Parent $PSScriptRoot) 'build/rayher_crm.zip'),
    [switch]$IncludeTests
)

$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.IO.Compression
Add-Type -AssemblyName System.IO.Compression.FileSystem
$protectedMarker = '%TSD-Header-###%'
$textExtensions = @('.py', '.toml', '.in', '.rst', '.txt', '.json', '.csv', '.md', '.html', '.css', '.js', '.svg', '.xml', '.yml', '.yaml', '.map', '.ts', '.tsx', '.vue', '.sh', '.ps1', '.jinja', '.jinja2')
$strictUtf8 = [Text.UTF8Encoding]::new($false, $true)

function Assert-ArchiveContract {
    param(
        [bool]$Condition,
        [string]$Message
    )

    if (-not $Condition) {
        throw "App archive contract failed: $Message"
    }
}

function Test-ArchiveEntryIncluded {
    param([string]$RelativePath)

    if ($RelativePath -match '(^|/)(__pycache__|[^/]+\.egg-info)/' -or $RelativePath -match '\.py[co]$') {
        return $false
    }
    return $IncludeTests -or ($RelativePath -notmatch '(^|/)tests?/|(^|/)test_[^/]+\.py$|(^|/)conftest\.py$')
}

function Get-GitHeadEntries {
    param(
        [string]$RepositoryRoot,
        [string]$AppRepositoryPath
    )

    $startInfo = [Diagnostics.ProcessStartInfo]::new()
    $startInfo.FileName = 'git'
    $startInfo.UseShellExecute = $false
    $startInfo.RedirectStandardOutput = $true
    $startInfo.RedirectStandardError = $true
    foreach ($argument in @('-C', $RepositoryRoot, 'archive', '--format=zip', 'HEAD', '--', $AppRepositoryPath)) {
        [void]$startInfo.ArgumentList.Add($argument)
    }

    $process = [Diagnostics.Process]::new()
    $process.StartInfo = $startInfo
    $memory = [IO.MemoryStream]::new()
    try {
        [void]$process.Start()
        $copyTask = $process.StandardOutput.BaseStream.CopyToAsync($memory)
        $errorTask = $process.StandardError.ReadToEndAsync()
        $process.WaitForExit()
        [void]$copyTask.GetAwaiter().GetResult()
        $errorText = $errorTask.GetAwaiter().GetResult()
        Assert-ArchiveContract ($process.ExitCode -eq 0) "could not archive Git HEAD app source: $errorText"

        $entries = [Collections.Generic.Dictionary[string, byte[]]]::new([StringComparer]::Ordinal)
        $trackedPrefix = "$AppRepositoryPath/"
        $memory.Position = 0
        $headArchive = [IO.Compression.ZipArchive]::new($memory, [IO.Compression.ZipArchiveMode]::Read, $true)
        try {
            foreach ($entry in $headArchive.Entries) {
                if ($entry.FullName.EndsWith('/', [StringComparison]::Ordinal)) {
                    continue
                }
                Assert-ArchiveContract ($entry.FullName.StartsWith($trackedPrefix, [StringComparison]::Ordinal)) "Git HEAD entry escaped the app root: $($entry.FullName)"
                $relativePath = $entry.FullName.Substring($trackedPrefix.Length)
                if (-not (Test-ArchiveEntryIncluded $relativePath)) {
                    continue
                }
                $entryStream = $entry.Open()
                $entryMemory = [IO.MemoryStream]::new()
                try {
                    $entryStream.CopyTo($entryMemory)
                    $entries.Add($relativePath, $entryMemory.ToArray())
                }
                finally {
                    $entryMemory.Dispose()
                    $entryStream.Dispose()
                }
            }
        }
        finally {
            $headArchive.Dispose()
        }
        return ,$entries
    }
    finally {
        $memory.Dispose()
        $process.Dispose()
    }
}

function ConvertTo-NormalizedTextBytes {
    param([byte[]]$Bytes)

    $text = $strictUtf8.GetString($Bytes).Replace("`r`n", "`n").Replace("`r", "`n")
    return ,$strictUtf8.GetBytes($text)
}

$backendRootPath = (Resolve-Path -LiteralPath $BackendRoot).Path
$sourceRoot = (Resolve-Path -LiteralPath (Join-Path $backendRootPath 'apps/rayher_crm')).Path
$buildRoot = [IO.Path]::GetFullPath((Join-Path $backendRootPath 'build'))
$resolvedArchive = [IO.Path]::GetFullPath($ArchivePath)
$pathComparison = if ($IsWindows) { [StringComparison]::OrdinalIgnoreCase } else { [StringComparison]::Ordinal }

Assert-ArchiveContract ($resolvedArchive.StartsWith($buildRoot + [IO.Path]::DirectorySeparatorChar, $pathComparison)) 'archive must remain inside backend/build'
Assert-ArchiveContract (Test-Path -LiteralPath $resolvedArchive -PathType Leaf) 'built app archive is missing'
$archiveItem = Get-Item -LiteralPath $resolvedArchive -Force
Assert-ArchiveContract (-not ($archiveItem.Attributes -band [IO.FileAttributes]::ReparsePoint)) 'built app archive must not be a reparse point'

$repositoryRootOutput = @(& git -C $backendRootPath rev-parse --show-toplevel)
Assert-ArchiveContract ($LASTEXITCODE -eq 0 -and $repositoryRootOutput.Count -eq 1) 'could not resolve the Git repository root'
$repositoryRoot = (Resolve-Path -LiteralPath $repositoryRootOutput[0]).Path
$repositoryPrefix = $repositoryRoot + [IO.Path]::DirectorySeparatorChar
Assert-ArchiveContract ($sourceRoot.StartsWith($repositoryPrefix, $pathComparison)) 'app source must remain inside the Git repository'
$appRepositoryPath = $sourceRoot.Substring($repositoryPrefix.Length).Replace('\', '/')

$trackedEntries = Get-GitHeadEntries -RepositoryRoot $repositoryRoot -AppRepositoryPath $appRepositoryPath

$expectedEntries = [Collections.Generic.Dictionary[string, string]]::new([StringComparer]::Ordinal)
foreach ($relativePath in $trackedEntries.Keys) {
    $sourcePath = Join-Path $sourceRoot ($relativePath -replace '/', [IO.Path]::DirectorySeparatorChar)
    Assert-ArchiveContract (Test-Path -LiteralPath $sourcePath -PathType Leaf) "tracked source is missing from the archive input: $relativePath"
    $expectedEntries.Add($relativePath, $sourcePath)
}

$generatedFrontendRoot = Join-Path $sourceRoot 'rayher_crm/public/crm'
if (Test-Path -LiteralPath $generatedFrontendRoot -PathType Container) {
    Get-ChildItem -LiteralPath $generatedFrontendRoot -Recurse -File -Force | ForEach-Object {
        $relativePath = $_.FullName.Substring($sourceRoot.Length + 1).Replace('\', '/')
        if (-not $expectedEntries.ContainsKey($relativePath)) {
            $expectedEntries.Add($relativePath, $_.FullName)
        }
    }
}

$seenEntries = [Collections.Generic.HashSet[string]]::new([StringComparer]::Ordinal)
$archive = [IO.Compression.ZipFile]::OpenRead($archiveItem.FullName)
try {
    Assert-ArchiveContract ($archive.Entries.Count -eq $expectedEntries.Count) "archive entry count mismatch: expected $($expectedEntries.Count), got $($archive.Entries.Count)"
    $previousEntryName = $null
    foreach ($entry in $archive.Entries) {
        if ($null -ne $previousEntryName) {
            Assert-ArchiveContract ([StringComparer]::Ordinal.Compare($previousEntryName, $entry.FullName) -lt 0) "archive entries are not in strict ordinal order: $previousEntryName, $($entry.FullName)"
        }
        $previousEntryName = $entry.FullName
        Assert-ArchiveContract ($expectedEntries.ContainsKey($entry.FullName)) "unexpected archive entry: $($entry.FullName)"
        Assert-ArchiveContract ($seenEntries.Add($entry.FullName)) "duplicate archive entry: $($entry.FullName)"
        $entryTimestamp = $entry.LastWriteTime
        $hasDeterministicTimestamp = $entryTimestamp.Year -eq 1980 -and $entryTimestamp.Month -eq 1 -and $entryTimestamp.Day -eq 1 -and $entryTimestamp.TimeOfDay -eq [TimeSpan]::Zero
        Assert-ArchiveContract $hasDeterministicTimestamp "non-deterministic archive timestamp: $($entry.FullName)"

        $entryStream = $entry.Open()
        $memory = [IO.MemoryStream]::new()
        try {
            $entryStream.CopyTo($memory)
            $archiveBytes = $memory.ToArray()
        }
        finally {
            $memory.Dispose()
            $entryStream.Dispose()
        }

        $prefixLength = [Math]::Min(18, $archiveBytes.Length)
        $prefix = if ($prefixLength -gt 0) { [Text.Encoding]::ASCII.GetString($archiveBytes, 0, $prefixLength) } else { '' }
        Assert-ArchiveContract (-not $prefix.StartsWith($protectedMarker)) "protected wrapper found inside archive: $($entry.FullName)"
        $isTextEntry = $textExtensions -contains [IO.Path]::GetExtension($entry.FullName).ToLowerInvariant()
        if ($isTextEntry) {
            Assert-ArchiveContract (-not ($archiveBytes -contains 0)) "null byte found inside text archive entry: $($entry.FullName)"
        }

        $sourceBytes = [IO.File]::ReadAllBytes($expectedEntries[$entry.FullName])
        if ($isTextEntry) {
            $archiveComparisonBytes = ConvertTo-NormalizedTextBytes $archiveBytes
            $sourceComparisonBytes = ConvertTo-NormalizedTextBytes $sourceBytes
        }
        else {
            $archiveComparisonBytes = $archiveBytes
            $sourceComparisonBytes = $sourceBytes
        }
        Assert-ArchiveContract ([Collections.StructuralComparisons]::StructuralEqualityComparer.Equals($archiveComparisonBytes, $sourceComparisonBytes)) "archive entry differs from source: $($entry.FullName)"
        if ($trackedEntries.ContainsKey($entry.FullName)) {
            $headBytes = $trackedEntries[$entry.FullName]
            if ($isTextEntry) {
                $headComparisonBytes = ConvertTo-NormalizedTextBytes $headBytes
            }
            else {
                $archiveComparisonBytes = $archiveBytes
                $headComparisonBytes = $headBytes
            }
            Assert-ArchiveContract ([Collections.StructuralComparisons]::StructuralEqualityComparer.Equals($archiveComparisonBytes, $headComparisonBytes)) "archive entry differs from Git HEAD: $($entry.FullName)"
        }
    }
}
finally {
    $archive.Dispose()
}

foreach ($relativePath in $expectedEntries.Keys) {
    Assert-ArchiveContract ($seenEntries.Contains($relativePath)) "missing archive entry: $relativePath"
}

$generatedEntryCount = $expectedEntries.Count - $trackedEntries.Count
Write-Output "App archive contract passed: entries=$($expectedEntries.Count), tracked=$($trackedEntries.Count) (verified against Git HEAD), generated=$generatedEntryCount (verified against current frontend output; the builder independently enforces a clean rebuild match)."
