# jules_centinela_reactivo.ps1
# Centinela ligero a nivel de sistema operativo para monitoreo asíncrono de Jules
# Coste CERO de tokens de LLM y CERO minutos de GitHub Actions

param (
    [int]$PrNumber,
    [string]$Repo = "Orlandho/LM-Chat",
    [int]$IntervalSeconds = 30,
    [int]$TimeoutMinutes = 30
)

$startTime = Get-Date
$maxWaitTime = $startTime.AddMinutes($TimeoutMinutes)
$headers = @{
    "User-Agent" = "Jules-Centinela-OS"
}
if ($env:GITHUB_TOKEN) {
    $headers["Authorization"] = "Bearer $env:GITHUB_TOKEN"
}

Write-Host "🛡️ Centinela Reactivo iniciado para PR #$PrNumber en $Repo (Intervalo: ${IntervalSeconds}s, Timeout: ${TimeoutMinutes}m)"

while ((Get-Date) -lt $maxWaitTime) {
    Start-Sleep -Seconds $IntervalSeconds

    try {
        $uri = "https://api.github.com/repos/$Repo/pulls/$PrNumber"
        $pr = Invoke-RestMethod -Uri $uri -Headers $headers -Method GET

        if ($pr.state -eq "closed") {
            if ($pr.merged -eq $true) {
                Write-Host "🎉 PR #$PrNumber FUSIONADO exitosamente en GitHub. Concluyendo centinela."
                exit 0
            } else {
                Write-Host "ℹ️ PR #$PrNumber fue CERRADO sin fusionar. Concluyendo centinela."
                exit 0
            }
        }

        Write-Host "[Centinela T+$([int]((Get-Date) - $startTime).TotalSeconds)s] PR #$PrNumber en estado '$($pr.state)' (mergeable: $($pr.mergeable)). Esperando..."
    }
    catch {
        Write-Warning "Aviso: Error transitorio al consultar API de GitHub: $_"
    }
}

Write-Error "🚨 Timeout alcanzado esperando resolucion del PR #$PrNumber ($TimeoutMinutes minutos)."
exit 1
