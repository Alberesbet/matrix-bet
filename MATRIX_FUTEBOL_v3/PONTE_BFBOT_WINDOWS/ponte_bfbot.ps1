$ErrorActionPreference="Continue"
$MatrixUrl="https://matrix-bet.onrender.com"
$Endpoint="$MatrixUrl/api/bfbot/bridge/import"
$IntervalSeconds=10

$Folders=@(
  [Environment]::GetFolderPath("Desktop"),
  [Environment]::GetFolderPath("MyDocuments"),
  (Join-Path $env:USERPROFILE "Downloads"),
  "C:\MATRIX_BFBOT"
) | Where-Object { $_ -and (Test-Path $_) } | Select-Object -Unique

$Seen=@{}

function HashText([string]$Text){
  $sha=[System.Security.Cryptography.SHA256]::Create()
  try{
    $bytes=[System.Text.Encoding]::UTF8.GetBytes($Text)
    return ([BitConverter]::ToString($sha.ComputeHash($bytes))).Replace("-","")
  } finally {$sha.Dispose()}
}

function LooksLikeBFBot([string]$Text){
  if(-not $Text){return $false}
  $h=$Text.Substring(0,[Math]::Min($Text.Length,16000)).ToLowerInvariant()
  $tokens=@("evento/mercado","marketid","market id","id do mercado","hora de início","hora de inicio","total correspondido","vencedor(es)","vencedores","1º favorito","1o favorito")
  foreach($t in $tokens){if($h.Contains($t)){return $true}}
  return $false
}

function SendCsv($File){
  try{
    Start-Sleep -Milliseconds 700
    $text=Get-Content -LiteralPath $File.FullName -Raw -Encoding UTF8
    if(-not (LooksLikeBFBot $text)){return}
    $hash=HashText $text
    if($Seen.ContainsKey($File.FullName) -and $Seen[$File.FullName] -eq $hash){return}

    $body=@{filename=$File.Name;kind="auto";csv=$text} | ConvertTo-Json -Depth 4
    $r=Invoke-RestMethod -Uri $Endpoint -Method Post -ContentType "application/json; charset=utf-8" -Body $body -TimeoutSec 25

    if($r.ok){
      $Seen[$File.FullName]=$hash
      $t=Get-Date -Format "HH:mm:ss"
      Write-Host "[$t] ENVIADO: $($File.Name) | tipo=$($r.kind) | linhas=$($r.rows) | ao vivo=$($r.live) | resultados=$($r.resultados_com_vencedor)" -ForegroundColor Green
      if($r.liquidacao){
        Write-Host "       Finalizadas agora: $($r.liquidacao.alteradas) | Pendentes: $($r.liquidacao.pendentes)" -ForegroundColor Cyan
      }
    }
  }catch{
    Write-Host "ERRO $($File.Name): $($_.Exception.Message)" -ForegroundColor Red
  }
}

Write-Host ""
Write-Host "MATRIX FUTEBOL - PONTE BF BOT V3.23" -ForegroundColor Cyan
Write-Host "Servidor: $MatrixUrl"
Write-Host "Deixe esta janela aberta." -ForegroundColor Yellow
Write-Host "Pastas monitoradas:"
$Folders | ForEach-Object { Write-Host " - $_" }
Write-Host ""

while($true){
  foreach($folder in $Folders){
    Get-ChildItem -LiteralPath $folder -Filter *.csv -File -ErrorAction SilentlyContinue |
      Where-Object {$_.LastWriteTime -gt (Get-Date).AddDays(-2)} |
      Sort-Object LastWriteTime |
      ForEach-Object {SendCsv $_}
  }
  Start-Sleep -Seconds $IntervalSeconds
}
