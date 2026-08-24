$ErrorActionPreference="Continue"

$MatrixUrl="https://matrix-bet.onrender.com"
$ImportEndpoint="$MatrixUrl/api/bfbot/bridge/import"
$HeartbeatEndpoint="$MatrixUrl/api/bfbot/bridge/heartbeat"
$IntervalSeconds=8
$HeartbeatSeconds=15
$BridgeVersion="3.24"

$Folders=@(
  [Environment]::GetFolderPath("Desktop"),
  [Environment]::GetFolderPath("MyDocuments"),
  (Join-Path $env:USERPROFILE "Downloads"),
  "C:\MATRIX_BFBOT"
) | Where-Object { $_ -and (Test-Path $_) } | Select-Object -Unique

$Seen=@{}
$Attempted=@{}
$LastHeartbeat=[DateTime]::MinValue

function HashBytes([byte[]]$Bytes){
  $sha=[System.Security.Cryptography.SHA256]::Create()
  try{
    return ([BitConverter]::ToString($sha.ComputeHash($Bytes))).Replace("-","")
  } finally {$sha.Dispose()}
}

function ShouldIgnore($File){
  $n=$File.Name.ToLowerInvariant()
  if($n -like "test_*"){return $true}
  if($n -like "tips*.csv"){return $true}
  if($n -like "*matrix*tips*.csv"){return $true}
  if($File.Length -lt 8){return $true}
  return $false
}

function SendHeartbeat(){
  try{
    $body=@{
      computer=$env:COMPUTERNAME
      bridge_version=$BridgeVersion
    } | ConvertTo-Json
    Invoke-RestMethod -Uri $HeartbeatEndpoint -Method Post -ContentType "application/json" -Body $body -TimeoutSec 12 | Out-Null
  }catch{}
  $script:LastHeartbeat=Get-Date
}

function SendCsv($File){
  if(ShouldIgnore $File){return}

  try{
    Start-Sleep -Milliseconds 600
    [byte[]]$bytes=[IO.File]::ReadAllBytes($File.FullName)
    $hash=HashBytes $bytes

    if($Seen.ContainsKey($File.FullName) -and $Seen[$File.FullName] -eq $hash){
      return
    }

    if($Attempted.ContainsKey($File.FullName) -and $Attempted[$File.FullName] -eq $hash){
      return
    }

    $Attempted[$File.FullName]=$hash

    $body=@{
      filename=$File.Name
      kind="auto"
      csv_b64=[Convert]::ToBase64String($bytes)
      bridge_version=$BridgeVersion
    } | ConvertTo-Json -Depth 4

    try{
      $r=Invoke-RestMethod -Uri $ImportEndpoint -Method Post -ContentType "application/json; charset=utf-8" -Body $body -TimeoutSec 30

      if($r.ok){
        $Seen[$File.FullName]=$hash
        $t=Get-Date -Format "HH:mm:ss"

        if($r.ignored){
          Write-Host "[$t] IGNORADO: $($File.Name)" -ForegroundColor DarkGray
          return
        }

        $enc=$r.encoding
        $sep=$r.diagnostico.delimiter
        Write-Host "[$t] ENVIADO: $($File.Name) | tipo=$($r.kind) | linhas=$($r.rows) | ao vivo=$($r.live) | resultados=$($r.resultados_com_vencedor)" -ForegroundColor Green
        Write-Host "          leitura: encoding=$enc | separador=$sep" -ForegroundColor DarkCyan

        if($r.liquidacao){
          Write-Host "          Finalizadas agora: $($r.liquidacao.alteradas) | Pendentes: $($r.liquidacao.pendentes) | Aguardando final: $($r.liquidacao.aguardando_final)" -ForegroundColor Cyan
        }
      }
    }catch{
      $msg=$_.Exception.Message
      $detail=""
      try{
        $resp=$_.Exception.Response
        if($resp -and $resp.GetResponseStream){
          $reader=New-Object IO.StreamReader($resp.GetResponseStream())
          $detail=$reader.ReadToEnd()
        }
      }catch{}
      Write-Host "ERRO $($File.Name): $msg" -ForegroundColor Red
      if($detail){Write-Host "     $detail" -ForegroundColor DarkRed}
    }
  }catch{
    Write-Host "ERRO lendo $($File.Name): $($_.Exception.Message)" -ForegroundColor Red
  }
}

Clear-Host
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host " MATRIX FUTEBOL - PONTE BF BOT V3.24" -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "Servidor: $MatrixUrl"
Write-Host "Leitura: bytes originais (UTF-8 / UTF-16 / ANSI automático)"
Write-Host "Heartbeat: a cada $HeartbeatSeconds segundos"
Write-Host "Deixe esta janela aberta." -ForegroundColor Yellow
Write-Host ""
Write-Host "Pastas monitoradas:"
$Folders | ForEach-Object {Write-Host " - $_"}
Write-Host ""

SendHeartbeat

while($true){
  if(((Get-Date)-$LastHeartbeat).TotalSeconds -ge $HeartbeatSeconds){
    SendHeartbeat
  }

  foreach($folder in $Folders){
    try{
      Get-ChildItem -LiteralPath $folder -Filter *.csv -File -ErrorAction SilentlyContinue |
        Where-Object {$_.LastWriteTime -gt (Get-Date).AddDays(-3)} |
        Sort-Object LastWriteTime |
        ForEach-Object {SendCsv $_}
    }catch{}
  }

  Start-Sleep -Seconds $IntervalSeconds
}
