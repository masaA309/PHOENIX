#requires -Version 5.1
param(
 [string]$OutputDir = (Join-Path $env:USERPROFILE 'Desktop\Q_Claude_Handoff'),
 [switch]$IncludeSource
)
$ErrorActionPreference='Stop'
$stamp=Get-Date -Format 'yyyyMMdd_HHmmss'
$work=Join-Path $OutputDir "Q_HANDOFF_$stamp"
$files=Join-Path $work 'FILES'
New-Item -ItemType Directory -Path $files -Force | Out-Null
$records=New-Object 'System.Collections.Generic.List[object]'
$notes=New-Object 'System.Collections.Generic.List[string]'
$homeRoot=Join-Path $env:USERPROFILE 'Documents\Codex'
$roots=@(
 (Join-Path $homeRoot '2026-10-18\referenced-chatgpt-conversation-this-is-an\work\QRC_DIRECT_GATEWAY_V2'),
 'C:\QRC_149_RC6_Product_Development_Candidate'
)
# No broad disk crawl. Existing known roots only.
$patterns=@('AGENTS.md','*MANIFEST*.sha256','*QRC*SPEC*.md','*QRC*REQUIREMENT*.md','*QRC*ACCEPTANCE*.md',
 '*GATEWAY*.md','*VERMILION*.md','*PHOENIX*.md','*AZURE*.md','*SHORT*.md',
 '*LONG*.md','*QRC*HANDOFF*.md','*QRC*PROTOCOL*.md')
$deny='(?i)(secret|credential|token|password|private.?key|hmac.?key|\.env|id_rsa|\.pem$|\.pfx$|\.db$|\.sqlite|\.git\\)'
$limit=3MB
$maxTotal=35MB
$total=0L
foreach($base in $roots) {
 if(!(Test-Path -LiteralPath $base)){ $notes.Add("NOT_FOUND root: $base");continue }
 $notes.Add("FOUND root: $base")
 foreach($pattern in $patterns){
  Get-ChildItem -LiteralPath $base -File -Recurse -Filter $pattern -ErrorAction SilentlyContinue |
   ForEach-Object {
    $f=$_
    if($f.FullName -match $deny -or $f.Length -gt $limit -or $total+$f.Length -gt $maxTotal){return}
    $relative=$f.FullName.Substring($base.Length).TrimStart('\')
    $label=if($base -like 'C:\QRC*'){'QRC_PRODUCT'}else{'GATEWAY_V2'}
    $dest=Join-Path (Join-Path $files $label) $relative
    if(Test-Path -LiteralPath $dest){return}
    $parent=Split-Path $dest -Parent
    New-Item -ItemType Directory -Path $parent -Force | Out-Null
    try {
     Copy-Item -LiteralPath $f.FullName -Destination $dest -ErrorAction Stop
     $hash=(Get-FileHash -LiteralPath $dest -Algorithm SHA256).Hash
     $records.Add([pscustomobject]@{Origin=$f.FullName;Collected=$dest.Substring($work.Length+1);SHA256=$hash;Bytes=$f.Length;ModifiedUTC=$f.LastWriteTimeUtc.ToString('o')})
     $total+=$f.Length
    }catch{$notes.Add("SKIP: $($f.FullName)")}
   }
 }
}
# Optional code: only source files from known QRC Gateway root, never .env/keys.
if($IncludeSource -and (Test-Path $roots[0])) {
 Get-ChildItem -LiteralPath $roots[0] -File -Filter '*.py' -ErrorAction SilentlyContinue |
  ForEach-Object {
   $f=$_; if($f.FullName -match $deny -or $f.Length -gt $limit -or $total+$f.Length -gt $maxTotal){return}
   $dest=Join-Path (Join-Path $files 'GATEWAY_V2\SOURCE') $f.Name
   New-Item -ItemType Directory -Path (Split-Path $dest -Parent) -Force | Out-Null
   Copy-Item -LiteralPath $f.FullName -Destination $dest
   $records.Add([pscustomobject]@{Origin=$f.FullName;Collected=$dest.Substring($work.Length+1);SHA256=(Get-FileHash $dest -Algorithm SHA256).Hash;Bytes=$f.Length;ModifiedUTC=$f.LastWriteTimeUtc.ToString('o')})
   $total+=$f.Length
  }
}
# Record process metadata, no command invocation into QRC and no secrets.
try {
 $proc=Get-CimInstance Win32_Process -Filter "Name = 'python.exe' OR Name = 'pythonw.exe'" |
 Where-Object {$_.CommandLine -match '(?i)QRC|gateway|startup_limited'} |
 Select-Object ProcessId,ParentProcessId,Name,ExecutablePath,CreationDate
 $proc | ConvertTo-Json -Depth 3 | Set-Content -LiteralPath (Join-Path $work 'QRC_PROCESS_METADATA.json') -Encoding UTF8
}catch{$notes.Add('NOT_PROVEN: process metadata')}
$records | Export-Csv -LiteralPath (Join-Path $work 'MANIFEST.csv') -NoTypeInformation -Encoding UTF8
$report=[pscustomobject]@{
 CreatedUTC=(Get-Date).ToUniversalTime().ToString('o')
 Mode='READ_ONLY_COLLECTION'
 FilesCollected=$records.Count
 BytesCollected=$total
 Sources=$roots
 Notes=@($notes)
 Warnings=@('No runtime execution, no QRC authorization, no Claude connection test','Source files only when -IncludeSource specified','Inspect contents before sharing; secret scanning is name-based and not a guarantee')
}
$report | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath (Join-Path $work 'COLLECTION_REPORT.json') -Encoding UTF8
$zip=Join-Path $OutputDir "Q_HANDOFF_EVIDENCE_$stamp.zip"
Get-ChildItem -LiteralPath $work | Compress-Archive -DestinationPath $zip -Force
Write-Output "COLLECTED_ZIP=$zip"
Write-Output "FILES=$($records.Count)"
