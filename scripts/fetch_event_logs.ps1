<#
.SYNOPSIS
    Downloads the four public event logs used by the WF-Adapt benchmark.

.DESCRIPTION
    The benchmark is built on public Business Process Intelligence Challenge
    event logs.  The files are large, so they are not kept in version
    control; this script fetches them into carma-backend\data and verifies
    the result.

    Sources
        bpi2017  BPI Challenge 2017 — loan application (Dutch financial
                 institute).  4TU.ResearchData, DOI 10.4121/uuid:
                 5f3067df-f10b-45da-b98b-86ae4c7a310b
        bpi2019  BPI Challenge 2019 — purchase-to-pay.  4TU.ResearchData,
                 DOI 10.4121/uuid:d06aff4b-79f0-45e6-8ec8-e19730c248f1
        bpi2020  BPI Challenge 2020 — travel permits.  4TU.ResearchData,
                 DOI 10.4121/uuid:52fb97d4-4588-43c9-9d04-3604d4613b51
        rtfm     Road Traffic Fine Management.  4TU.ResearchData,
                 DOI 10.4121/uuid:270fd440-1057-4fb9-89a9-b699b47990f5

.PARAMETER Datasets
    Which logs to fetch.  Defaults to all four.

.EXAMPLE
    pwsh scripts/fetch_event_logs.ps1
    pwsh scripts/fetch_event_logs.ps1 -Datasets bpi2017
#>
[CmdletBinding()]
param(
    [ValidateSet('bpi2017', 'bpi2019', 'bpi2020', 'rtfm')]
    [string[]] $Datasets = @('bpi2017', 'bpi2019', 'bpi2020', 'rtfm')
)

$ErrorActionPreference = 'Stop'
$ProgressPreference    = 'SilentlyContinue'

$RepoRoot = Split-Path -Parent $PSScriptRoot
$DataDir  = Join-Path $RepoRoot 'data'
$UserAgent = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 ' +
             '(KHTML, like Gecko) Chrome/125.0 Safari/537.36'

New-Item -ItemType Directory -Force -Path $DataDir | Out-Null

# Landing pages of the 4TU.ResearchData records.  Each of them embeds the
# id of the ndownloader item that serves the files.
$Sources = @{
    'bpi2017' = @{
        Landing = 'https://data.4tu.nl/articles/dataset/BPI_Challenge_2017/12696884'
        File    = 'BPI_Challenge_2017.xes'
    }
    'bpi2019' = @{
        Landing = 'https://data.4tu.nl/articles/dataset/BPI_Challenge_2019/12715853'
        File    = 'BPI_Challenge_2019.xes'
    }
    'bpi2020' = @{
        Landing = 'https://data.4tu.nl/collections/BPI_Challenge_2020/5065541'
        File    = 'PermitLog.xes'
    }
    'rtfm'    = @{
        Landing = 'https://data.4tu.nl/articles/dataset/Road_Traffic_Fine_Management_Process/12689204'
        File    = 'Road_Traffic_Fine_Management.xes'
    }
}

function Resolve-ItemId {
    param([string] $Landing)
    $html = (Invoke-WebRequest -Uri $Landing -UseBasicParsing -UserAgent $UserAgent).Content
    $match = [regex]::Match($html, 'https://data\.4tu\.nl/ndownloader/items/([0-9a-f-]+)/versions/\d+')
    if (-not $match.Success) {
        throw "Could not resolve the download id of $Landing"
    }
    return $match.Groups[1].Value
}

function Expand-ArchiveSafe {
    param([string] $Archive, [string] $Destination)
    $temp = Join-Path $env:TEMP ("carma-xes-" + [guid]::NewGuid().ToString('N'))
    New-Item -ItemType Directory -Force -Path $temp | Out-Null
    try {
        Expand-Archive -LiteralPath $Archive -DestinationPath $temp -Force
        $xes = Get-ChildItem -Path $temp -Recurse -Filter '*.xes' | Select-Object -First 1
        if (-not $xes) {
            throw "No .xes file found inside $Archive"
        }
        Copy-Item -LiteralPath $xes.FullName -Destination (Join-Path $Destination $xes.Name) -Force
        Write-Host "  extracted $($xes.Name) ($([math]::Round($xes.Length / 1MB, 1)) MB)"
    }
    finally {
        Remove-Item -LiteralPath $temp -Recurse -Force -ErrorAction SilentlyContinue
    }
}

foreach ($dataset in $Datasets) {
    $source = $Sources[$dataset]
    $target = Join-Path $DataDir $source.File

    if (Test-Path $target) {
        Write-Host "$dataset : already present ($([math]::Round((Get-Item $target).Length / 1MB, 1)) MB)"
        continue
    }

    Write-Host "$dataset : resolving $($source.Landing)"
    $itemId = Resolve-ItemId -Landing $source.Landing
    $url    = "https://data.4tu.nl/ndownloader/items/$itemId/versions/1"

    $archive = Join-Path $env:TEMP ("carma-" + $dataset + ".zip")
    Write-Host "$dataset : downloading $url"
    Invoke-WebRequest -Uri $url -OutFile $archive -UseBasicParsing -UserAgent $UserAgent
    Write-Host ("  downloaded {0:N1} MB" -f ((Get-Item $archive).Length / 1MB))

    Expand-ArchiveSafe -Archive $archive -Destination $DataDir
    Remove-Item -LiteralPath $archive -Force -ErrorAction SilentlyContinue

    # The 4TU archives do not always use the name we want; normalise it.
    $found = Get-ChildItem -Path $DataDir -Filter '*.xes' |
             Where-Object { $_.Name -ne $source.File } |
             Sort-Object LastWriteTime -Descending | Select-Object -First 1
    if ($found -and -not (Test-Path $target)) {
        Rename-Item -LiteralPath $found.FullName -NewName $source.File
    }
}

Write-Host ''
Get-ChildItem -Path $DataDir -Filter '*.xes' |
    Select-Object Name, @{n = 'MB'; e = { [math]::Round($_.Length / 1MB, 1) } } |
    Format-Table -AutoSize
