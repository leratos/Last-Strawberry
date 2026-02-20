[CmdletBinding()]
param(
    [string]$BaseUrl = "http://localhost:8002",
    [string]$EnvFile = "backend_v2/.env",
    [int]$UserId = 991,
    [string]$Username = "monitoring-bot",
    [int]$AuthFailures = 8,
    [switch]$SkipProviderError,
    [switch]$SkipTimeout,
    [switch]$SkipFallback,
    [switch]$KeepModifiedEnv
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Write-Step {
    param([string]$Message)
    Write-Host ""
    Write-Host "==> $Message" -ForegroundColor Cyan
}

function Get-EnvMapFromFile {
    param([string]$Path)
    $map = @{}
    if (-not (Test-Path $Path)) {
        return $map
    }
    foreach ($line in Get-Content -Path $Path) {
        if ($line -match '^\s*#') {
            continue
        }
        if ($line -match '^\s*([A-Za-z0-9_]+)\s*=\s*(.*)\s*$') {
            $key = $matches[1]
            $value = $matches[2]
            $map[$key] = $value
        }
    }
    return $map
}

function Set-EnvValuesInFile {
    param(
        [string]$Path,
        [hashtable]$Values
    )
    $lines = [System.Collections.Generic.List[string]]::new()
    if (Test-Path $Path) {
        foreach ($line in Get-Content -Path $Path) {
            $lines.Add($line)
        }
    }

    $seen = @{}
    for ($i = 0; $i -lt $lines.Count; $i++) {
        foreach ($key in $Values.Keys) {
            if ($lines[$i] -match ("^\s*" + [regex]::Escape($key) + "\s*=")) {
                $lines[$i] = "$key=$($Values[$key])"
                $seen[$key] = $true
            }
        }
    }

    foreach ($key in $Values.Keys) {
        if (-not $seen.ContainsKey($key)) {
            $lines.Add("$key=$($Values[$key])")
        }
    }

    $utf8NoBom = [System.Text.UTF8Encoding]::new($false)
    [System.IO.File]::WriteAllLines((Resolve-Path $Path), $lines, $utf8NoBom)
}

function Invoke-ApiRequest {
    param(
        [ValidateSet("GET", "POST")]
        [string]$Method,
        [string]$Url,
        [hashtable]$Headers = @{},
        [object]$Body = $null
    )
    $statusCode = 0
    $content = ""

    $requestParams = @{
        Method          = $Method
        Uri             = $Url
        Headers         = $Headers
        UseBasicParsing = $true
        TimeoutSec      = 30
    }
    if ($null -ne $Body) {
        $requestParams["Body"] = ($Body | ConvertTo-Json -Compress -Depth 8)
        $requestParams["ContentType"] = "application/json"
    }

    try {
        $response = Invoke-WebRequest @requestParams
        $statusCode = [int]$response.StatusCode
        $content = [string]$response.Content
    }
    catch {
        $webResponse = $_.Exception.Response
        if ($webResponse) {
            try { $statusCode = [int]$webResponse.StatusCode } catch {}
            try {
                $stream = $webResponse.GetResponseStream()
                if ($stream) {
                    $reader = New-Object System.IO.StreamReader($stream)
                    $content = $reader.ReadToEnd()
                    $reader.Dispose()
                    $stream.Dispose()
                }
            } catch {}
        } else {
            $content = [string]$_.Exception.Message
        }
    }

    $json = $null
    if ($content) {
        try {
            $json = $content | ConvertFrom-Json
        } catch {
            $json = $null
        }
    }
    return [pscustomobject]@{
        StatusCode = $statusCode
        Content    = $content
        Json       = $json
    }
}

function Wait-ForBackend {
    param(
        [string]$Base,
        [int]$MaxSeconds = 90
    )
    $deadline = (Get-Date).AddSeconds($MaxSeconds)
    while ((Get-Date) -lt $deadline) {
        $resp = Invoke-ApiRequest -Method GET -Url "$Base/v2/health"
        if ($resp.StatusCode -eq 200) {
            return $true
        }
        Start-Sleep -Seconds 2
    }
    return $false
}

function Request-ManualRestartAndWait {
    param([string]$Base)
    [void](Read-Host "Bitte backend_v2 neu starten und dann ENTER druecken")
    if (-not (Wait-ForBackend -Base $Base)) {
        throw "Backend wurde nach Restart nicht erreichbar (timeout)."
    }
}

function Login {
    param([string]$Base, [int]$Uid, [string]$User)
    $resp = Invoke-ApiRequest -Method POST -Url "$Base/v2/auth/login" -Body @{
        user_id  = $Uid
        username = $User
    }
    if ($resp.StatusCode -ne 200 -or -not $resp.Json -or -not $resp.Json.access_token) {
        throw "Login fehlgeschlagen (status=$($resp.StatusCode)). Body: $($resp.Content)"
    }
    return [string]$resp.Json.access_token
}

function CreateWorld {
    param([string]$Base, [string]$Token, [string]$Name)
    $resp = Invoke-ApiRequest -Method POST -Url "$Base/v2/worlds" -Headers @{
        Authorization = "Bearer $Token"
    } -Body @{
        name        = $Name
        description = "monitoring-event-generation"
    }
    if ($resp.StatusCode -ne 201 -or -not $resp.Json -or -not $resp.Json.id) {
        throw "World create fehlgeschlagen (status=$($resp.StatusCode)). Body: $($resp.Content)"
    }
    return [int]$resp.Json.id
}

function RunTurn {
    param(
        [string]$Base,
        [string]$Token,
        [int]$WorldId,
        [string]$Command
    )
    return Invoke-ApiRequest -Method POST -Url "$Base/v2/game/turn" -Headers @{
        Authorization = "Bearer $Token"
    } -Body @{
        world_id       = $WorldId
        player_id      = 77
        player_command = $Command
    }
}

if (-not (Test-Path $EnvFile)) {
    throw "Env file nicht gefunden: $EnvFile"
}

$backupFile = "$EnvFile.monitoring_events_backup"
$base = $BaseUrl.TrimEnd("/")
Copy-Item -Path $EnvFile -Destination $backupFile -Force
$original = Get-EnvMapFromFile -Path $backupFile

Write-Step "Backup erstellt: $backupFile"

try {
    if (-not (Wait-ForBackend -Base $base -MaxSeconds 20)) {
        throw "Backend ist nicht erreichbar unter $base."
    }

    Write-Step "1) Auth-Failures erzeugen ($AuthFailures x 401)"
    for ($i = 1; $i -le $AuthFailures; $i++) {
        $r = Invoke-ApiRequest -Method GET -Url "$base/v2/worlds/1"
        Write-Host "auth_failed request $i -> status $($r.StatusCode)"
    }

    if (-not $SkipProviderError) {
        Write-Step "2) Provider-Errors erzeugen (ungueltiger API-Key)"
        Set-EnvValuesInFile -Path $EnvFile -Values @{
            LS_OPENROUTER_API_KEY    = "invalid-monitoring-key"
            LS_TURN_TIMEOUT_SECONDS  = "60"
            LS_ANALYSIS_FALLBACK_MODELS = ""
            LS_NARRATIVE_FALLBACK_MODELS = ""
        }
        Request-ManualRestartAndWait -Base $base

        $token = Login -Base $base -Uid $UserId -User $Username
        $world = CreateWorld -Base $base -Token $token -Name "Monitoring-Provider-Error"
        $resp = RunTurn -Base $base -Token $token -WorldId $world -Command "Ich teste Providerfehler."
        Write-Host "provider scenario status -> $($resp.StatusCode)"
    }

    if (-not $SkipTimeout) {
        Write-Step "3) Timeout-Events erzeugen (LS_TURN_TIMEOUT_SECONDS=1)"
        if (-not $original.ContainsKey("LS_OPENROUTER_API_KEY") -or [string]::IsNullOrWhiteSpace($original["LS_OPENROUTER_API_KEY"])) {
            Write-Warning "Timeout-Szenario uebersprungen: Kein LS_OPENROUTER_API_KEY im originalen .env."
        } else {
            Set-EnvValuesInFile -Path $EnvFile -Values @{
                LS_OPENROUTER_API_KEY   = $original["LS_OPENROUTER_API_KEY"]
                LS_TURN_TIMEOUT_SECONDS = "1"
            }
            Request-ManualRestartAndWait -Base $base

            $token = Login -Base $base -Uid $UserId -User $Username
            $world = CreateWorld -Base $base -Token $token -Name "Monitoring-Timeout"

            $hit504 = $false
            for ($i = 1; $i -le 3; $i++) {
                $resp = RunTurn -Base $base -Token $token -WorldId $world -Command "Ich teste Timeout #$i."
                Write-Host "timeout scenario attempt $i -> status $($resp.StatusCode)"
                if ($resp.StatusCode -eq 504) {
                    $hit504 = $true
                    break
                }
            }
            if (-not $hit504) {
                Write-Warning "Kein 504 im Timeout-Szenario gesehen. Pruefe Modell-Latenz/Turn-Timeout-Konfiguration."
            }
        }
    }

    if (-not $SkipFallback) {
        Write-Step "4) Fallback-Route erzeugen (ungueltiges Analysis-Modell + Fallback)"
        if (
            -not $original.ContainsKey("LS_OPENROUTER_API_KEY") -or
            [string]::IsNullOrWhiteSpace($original["LS_OPENROUTER_API_KEY"]) -or
            -not $original.ContainsKey("LS_ANALYSIS_MODEL") -or
            [string]::IsNullOrWhiteSpace($original["LS_ANALYSIS_MODEL"])
        ) {
            Write-Warning "Fallback-Szenario uebersprungen: LS_OPENROUTER_API_KEY oder LS_ANALYSIS_MODEL fehlt im originalen .env."
        } else {
            Set-EnvValuesInFile -Path $EnvFile -Values @{
                LS_OPENROUTER_API_KEY      = $original["LS_OPENROUTER_API_KEY"]
                LS_TURN_TIMEOUT_SECONDS    = "60"
                LS_ANALYSIS_MODEL          = "invalid/monitoring-model-does-not-exist"
                LS_ANALYSIS_FALLBACK_MODELS = $original["LS_ANALYSIS_MODEL"]
            }
            Request-ManualRestartAndWait -Base $base

            $token = Login -Base $base -Uid $UserId -User $Username
            $world = CreateWorld -Base $base -Token $token -Name "Monitoring-Fallback"
            $resp = RunTurn -Base $base -Token $token -WorldId $world -Command "Ich teste Fallback."
            Write-Host "fallback scenario status -> $($resp.StatusCode)"
            if ($resp.Json -and $resp.Json.models -and $resp.Json.models.analysis) {
                Write-Host "analysis model used -> $($resp.Json.models.analysis)"
            }
        }
    }

    Write-Step "Monitoring-Event-Generierung abgeschlossen"
    Write-Host "Prometheus Query Tipps:"
    Write-Host "  increase(ls_backend_v2_error_category_total{category=`"provider`"}[10m])"
    Write-Host "  increase(ls_backend_v2_audit_event_total{event=`"turn_timeout`"}[10m])"
    Write-Host "  increase(ls_backend_v2_audit_event_total{event=`"auth_failed`"}[10m])"
    Write-Host "  100 * (sum(increase(ls_backend_v2_model_route_total{fallback=`"true`"}[10m])) / clamp_min(sum(increase(ls_backend_v2_model_route_total[10m])), 1))"
}
finally {
    if (-not $KeepModifiedEnv) {
        Write-Step "Originales .env wiederherstellen"
        Copy-Item -Path $backupFile -Destination $EnvFile -Force
        Remove-Item -Path $backupFile -Force -ErrorAction SilentlyContinue
        [void](Read-Host "Bitte backend_v2 jetzt mit originaler Konfiguration neu starten und ENTER druecken")
    } else {
        Write-Warning "KeepModifiedEnv aktiv: .env wurde NICHT automatisch zurueckgesetzt."
    }
}
