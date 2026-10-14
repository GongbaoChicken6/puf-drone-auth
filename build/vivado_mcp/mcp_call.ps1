param([string]$Session, [string]$ReqFile)
$h = @{ Accept = 'application/json, text/event-stream'; 'Mcp-Session-Id' = $Session }
$body = Get-Content $ReqFile -Raw -Encoding UTF8
$resp = Invoke-WebRequest -Uri 'http://127.0.0.1:18090/mcp' -Method Post -ContentType 'application/json' -Body $body -Headers $h -UseBasicParsing -TimeoutSec 60
Write-Output $resp.Content
