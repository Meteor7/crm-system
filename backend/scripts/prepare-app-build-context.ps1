param(
    [string]$SourceDirectory = (Join-Path $PSScriptRoot '..\apps\rayher_crm'),
    [string]$OutputArchive = (Join-Path $PSScriptRoot '..\build\rayher_crm.zip'),
    [switch]$IncludeTests
)

$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.IO.Compression
Add-Type -AssemblyName System.IO.Compression.FileSystem

$sourceRoot = (Resolve-Path -LiteralPath $SourceDirectory).Path
$backendRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
$buildRoot = Join-Path $backendRoot 'build'
$resolvedOutput = [IO.Path]::GetFullPath($OutputArchive)

if (-not $resolvedOutput.StartsWith($buildRoot + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase)) {
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
$textExtensions = @('.py', '.toml', '.in', '.rst', '.txt', '.json', '.csv', '.md')
$sourceFiles = @(Get-ChildItem -LiteralPath $sourceRoot -Recurse -File |
    Where-Object {
        $relative = $_.FullName.Substring($sourceRoot.Length + 1).Replace('\', '/')
        $IncludeTests -or ($relative -notmatch '(^|/)tests?/|(^|/)__pycache__/|(^|/)test_[^/]+\.py$|(^|/)conftest\.py$')
    } |
    Sort-Object FullName)

if ($sourceFiles.Count -eq 0) {
    throw 'App source is empty.'
}

$archiveStream = [IO.File]::Open($resolvedOutput, [IO.FileMode]::Create, [IO.FileAccess]::ReadWrite, [IO.FileShare]::None)
try {
    $archive = [IO.Compression.ZipArchive]::new($archiveStream, [IO.Compression.ZipArchiveMode]::Create, $false)
    try {
        foreach ($file in $sourceFiles) {
            if ($file.Attributes -band [IO.FileAttributes]::ReparsePoint) {
                throw "Reparse points are forbidden in app source: $($file.FullName)"
            }

            $bytes = [IO.File]::ReadAllBytes($file.FullName)
            $prefixLength = [Math]::Min(18, $bytes.Length)
            $prefix = if ($prefixLength -gt 0) { [Text.Encoding]::ASCII.GetString($bytes, 0, $prefixLength) } else { '' }
            if ($prefix.StartsWith($protectedMarker)) {
                throw "Protected wrapper remains in app source: $($file.FullName)"
            }
            if ($textExtensions -contains $file.Extension.ToLowerInvariant() -and ($bytes -contains 0)) {
                throw "Null byte remains in text app source: $($file.FullName)"
            }

            if (-not $file.FullName.StartsWith($sourceRoot + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase)) {
                throw "App source file escaped the source root: $($file.FullName)"
            }
            $relativePath = $file.FullName.Substring($sourceRoot.Length + 1).Replace('\', '/')
            $entry = $archive.CreateEntry($relativePath, [IO.Compression.CompressionLevel]::Optimal)
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

$inspection = [IO.Compression.ZipFile]::OpenRead($resolvedOutput)
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

$archiveItem = Get-Item -LiteralPath $resolvedOutput
Write-Output "Prepared verified app build archive: entries=$($sourceFiles.Count), bytes=$($archiveItem.Length)."
