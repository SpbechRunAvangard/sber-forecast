# Меню управления сервисом прогноза (Windows, PowerShell 5.1+). Запускается через start.bat в корне репозитория.
# Без параметров показывает меню. Для автоматизации: start.bat start | forecast | test | open | stop | rebuild | logs
param([string]$Action = "")

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root
$Image = "sber-forecast"
$Container = "sber-forecast"
$Port = if ($env:SBER_PORT) { $env:SBER_PORT } else { "8000" }
$Base = "http://localhost:$Port"
$ResultsDir = Join-Path $Root "results"
$DefaultCutoff = "2026-07-26"
try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch {}
Add-Type -AssemblyName System.Net.Http

function Say($text, $color = "Gray") { Write-Host $text -ForegroundColor $color }
function Ok($text) { Say "  [OK] $text" "Green" }
function Warn($text) { Say "  [!] $text" "Yellow" }
function Fail($text) { Say "  [X] $text" "Red" }

function Invoke-Docker {
    # Запуск docker с выводом в консоль; возвращает только код выхода
    $old = $ErrorActionPreference; $ErrorActionPreference = "Continue"
    & docker @args | Out-Host
    $code = $LASTEXITCODE; $ErrorActionPreference = $old
    return $code
}

function Invoke-DockerQuiet {
    # То же без вывода (для проверок)
    $old = $ErrorActionPreference; $ErrorActionPreference = "Continue"
    & docker @args *> $null
    $code = $LASTEXITCODE; $ErrorActionPreference = $old
    return $code
}

function Test-DockerReady {
    if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
        Fail "Docker не установлен. Установите Docker Desktop: https://www.docker.com/products/docker-desktop/"
        Say  "      После установки перезагрузите компьютер, запустите Docker Desktop и снова откройте start.bat."
        return $false
    }
    if ((Invoke-DockerQuiet info) -eq 0) { return $true }
    $desktop = Join-Path $env:ProgramFiles "Docker\Docker\Docker Desktop.exe"
    if (Test-Path $desktop) {
        Warn "Docker Desktop не запущен - запускаю и жду (до 2 минут)..."
        Start-Process $desktop
        for ($i = 0; $i -lt 60; $i++) {
            Start-Sleep -Seconds 2
            if ((Invoke-DockerQuiet info) -eq 0) { Ok "Docker запущен"; return $true }
        }
    }
    Fail "Docker не отвечает. Запустите Docker Desktop вручную, дождитесь зелёного статуса и повторите."
    return $false
}

function Test-Health {
    try { return (Invoke-RestMethod "$Base/health" -TimeoutSec 3).status -eq "ok" } catch { return $false }
}

function Test-ImageExists {
    return (Invoke-DockerQuiet image inspect $Image) -eq 0
}

function Build-Image {
    Say "Собираю образ $Image (первый раз 3-10 минут, нужен интернет)..." "Cyan"
    $code = Invoke-Docker build -t $Image .
    if ($code -ne 0) { Fail "Сборка не удалась (см. сообщения выше)"; return $false }
    Ok "Образ собран"; return $true
}

function Start-Forecast-Service {
    if (-not (Test-DockerReady)) { return $false }
    if (Test-Health) { Ok "Сервис уже работает: $Base"; return $true }
    if (-not (Test-ImageExists)) { if (-not (Build-Image)) { return $false } }
    $null = Invoke-DockerQuiet rm -f $Container
    Say "Запускаю контейнер на порту $Port..." "Cyan"
    $code = Invoke-Docker run -d --name $Container -p "${Port}:8000" --restart unless-stopped $Image
    if ($code -ne 0) {
        Fail "Не удалось запустить контейнер. Если порт $Port занят: set SBER_PORT=8001 и снова start.bat"
        return $false
    }
    for ($i = 0; $i -lt 60; $i++) {
        Start-Sleep -Seconds 1
        if (Test-Health) { Ok "Сервис работает: $Base  (веб-интерфейс: $Base/ , API: $Base/docs)"; return $true }
    }
    Fail "Сервис не ответил за минуту. Журнал контейнера:"; $null = Invoke-Docker logs --tail 30 $Container
    return $false
}

function Ensure-Running {
    if (Test-Health) { return $true }
    Warn "Сервис не запущен - запускаю."
    return (Start-Forecast-Service)
}

function Stop-Forecast-Service {
    if (-not (Test-DockerReady)) { return }
    $null = Invoke-DockerQuiet rm -f $Container
    Ok "Сервис остановлен"
}

function Find-DataFile($name) {
    # Ищем в корне репозитория, в data\raw и в двух папках выше (например, C:\Hackaton 3)
    $dirs = @($Root, (Join-Path $Root "data\raw"))
    $up = Split-Path $Root -Parent
    if ($up) { $dirs += $up; $up2 = Split-Path $up -Parent; if ($up2) { $dirs += $up2 } }
    foreach ($d in $dirs) {
        $c = Join-Path $d $name
        if (Test-Path $c) { return (Resolve-Path $c).Path }
    }
    return $null
}

function Select-CsvFile($title) {
    Add-Type -AssemblyName System.Windows.Forms
    $dlg = New-Object System.Windows.Forms.OpenFileDialog
    $dlg.Title = $title; $dlg.Filter = "CSV (*.csv)|*.csv|Все файлы (*.*)|*.*"; $dlg.InitialDirectory = $Root
    if ($dlg.ShowDialog() -eq [System.Windows.Forms.DialogResult]::OK) { return $dlg.FileName }
    return $null
}

function Choose-File($label, $defaultName) {
    $found = Find-DataFile $defaultName
    if ($found) {
        Say "  $label`: найден $found"
        $ans = Read-Host "    Enter - взять его, 2 - выбрать другой файл"
        if ($ans -ne "2") { return $found }
    }
    Say "  Выберите файл: $label (откроется окно выбора)"
    return (Select-CsvFile "Выберите файл: $label")
}

function Choose-Cutoff {
    Say ""
    Say "  Какие даты использовать?"
    Say "    1 - по 26.07.2026, как в основном submission (прогноз с 27.07.2026)  [по умолчанию]"
    Say "    2 - все даты из файлов"
    Say "    3 - указать свою последнюю дату"
    $c = Read-Host "  Ваш выбор"
    switch ($c) {
        "2" { return "" }
        "3" { return (Read-Host "  Последняя дата в формате ГГГГ-ММ-ДД") }
        default { return $DefaultCutoff }
    }
}

function Send-Forecast($salesPath, $stockPath, $cutoff, $outPath) {
    # multipart POST через .NET: работает с любыми путями (в том числе с кириллицей) и без curl
    $client = New-Object System.Net.Http.HttpClient
    $client.Timeout = [TimeSpan]::FromMinutes(15)
    $form = New-Object System.Net.Http.MultipartFormDataContent
    $streams = @()
    foreach ($pair in @(@("sales", $salesPath), @("stock", $stockPath))) {
        $fs = [System.IO.File]::OpenRead($pair[1]); $streams += $fs
        $content = New-Object System.Net.Http.StreamContent($fs)
        $content.Headers.ContentType = [System.Net.Http.Headers.MediaTypeHeaderValue]::Parse("text/csv")
        $form.Add($content, $pair[0], [System.IO.Path]::GetFileName($pair[1]))
    }
    $url = "$Base/predict"
    if ($cutoff) { $url += "?cutoff=$cutoff" }
    try {
        $resp = $client.PostAsync($url, $form).GetAwaiter().GetResult()
        $body = $resp.Content.ReadAsByteArrayAsync().GetAwaiter().GetResult()
        if (-not $resp.IsSuccessStatusCode) {
            $text = [System.Text.Encoding]::UTF8.GetString($body)
            try { $text = ($text | ConvertFrom-Json).detail } catch {}
            Fail "Сервис вернул ошибку $([int]$resp.StatusCode): $text"
            return $false
        }
        [System.IO.File]::WriteAllBytes($outPath, $body)
        return $true
    } catch {
        $e = $_.Exception; while ($e.InnerException) { $e = $e.InnerException }
        Fail "Не удалось получить прогноз от сервиса: $($e.Message)"
        return $false
    } finally {
        foreach ($s in $streams) { $s.Dispose() }
        $client.Dispose()
    }
}

function Show-Summary($csvPath) {
    # Быстрый подсчёт без Import-Csv: week,warehouse_name,article,quantity
    $lines = [System.IO.File]::ReadAllLines($csvPath)
    $firstWeek = $lines[1].Split(',')[0]; $lastWeek = $firstWeek
    $pairs = 0; $nonzero = 0; [long]$total = 0
    for ($i = 1; $i -lt $lines.Length; $i++) {
        $f = $lines[$i].Split(','); $q = [int]$f[3]; $total += $q
        if ($f[0] -eq $firstWeek) { $pairs++; if ($q -gt 0) { $nonzero++ } }
        if ($f[0] -gt $lastWeek) { $lastWeek = $f[0] }
    }
    Ok "Строк: $($lines.Length - 1); недели: $firstWeek ... $lastWeek"
    Ok "Пар склад x артикул с ненулевым прогнозом: $nonzero из $pairs; всего за 9 недель: $total шт."
}

function Run-Forecast {
    if (-not (Ensure-Running)) { return }
    Say ""; Say "Прогноз из файлов CSV" "Cyan"
    $sales = Choose-File "Продажи (sales)" "sales_dataset_hakaton_train.csv"
    if (-not $sales) { Warn "Файл продаж не выбран"; return }
    $stock = Choose-File "Остатки (stock)" "stock_dataset_hakaton_train.csv"
    if (-not $stock) { Warn "Файл остатков не выбран"; return }
    $cutoff = Choose-Cutoff
    New-Item -ItemType Directory -Force -Path $ResultsDir | Out-Null
    $out = Join-Path $ResultsDir ("forecast_" + (Get-Date -Format "yyyy-MM-dd_HH-mm") + ".csv")
    Say ""; Say "Считаю прогноз (на полных данных 30-60 секунд)..." "Cyan"
    $sw = [Diagnostics.Stopwatch]::StartNew()
    if (Send-Forecast $sales $stock $cutoff $out) {
        Ok ("Готово за {0:N0} с: {1}" -f $sw.Elapsed.TotalSeconds, $out)
        Show-Summary $out
        $ref = Join-Path $Root "data\submission_weekly_v6.csv"
        if ($cutoff -eq $DefaultCutoff -and (Test-Path $ref)) {
            if ((Get-FileHash $out).Hash -eq (Get-FileHash $ref).Hash) { Ok "Совпадает с основным submission (data\submission_weekly_v6.csv)" }
        }
        Start-Process explorer.exe "/select,`"$out`""
    }
}

function Run-Lookup {
    if (-not (Ensure-Running)) { return }
    Say ""; Say "Прогноз по артикулу и/или складу (из последнего расчёта)" "Cyan"
    $art = Read-Host "  Артикул, например char_article_1 (Enter - любой)"
    $wh = Read-Host "  Склад, например warehouse_name_3 (Enter - любой)"
    if (-not $art -and -not $wh) { Warn "Нужно указать хотя бы одно"; return }
    $q = @()
    if ($art) { $q += "article=" + [uri]::EscapeDataString($art) }
    if ($wh) { $q += "warehouse=" + [uri]::EscapeDataString($wh) }
    try {
        $text = (Invoke-WebRequest "$Base/predict?$($q -join '&')" -UseBasicParsing).Content
        if ($text -is [byte[]]) { $text = [System.Text.Encoding]::UTF8.GetString($text) }
        $rows = $text -split "`r?`n" | Where-Object { $_ } | ConvertFrom-Csv
        if (-not $rows) { Warn "Ничего не найдено"; return }
        $rows | Select-Object -First 60 | Format-Table -AutoSize | Out-Host
        if (@($rows).Count -gt 60) { Say "  ...показаны первые 60 из $(@($rows).Count) строк" }
    } catch {
        $msg = $_.ErrorDetails.Message
        try { $msg = ($msg | ConvertFrom-Json).detail } catch {}
        if (-not $msg) { $msg = $_.Exception.Message }
        Fail $msg
    }
}

function Run-SelfTest {
    if (-not (Ensure-Running)) { return }
    Say ""; Say "Самопроверка API на примере data\sample_*.csv" "Cyan"
    $script:passed = 0; $script:failed = 0
    function Check($name, $cond) {
        if ($cond) { Ok $name; $script:passed++ } else { Fail $name; $script:failed++ }
    }
    Check "GET /health" (Test-Health)
    $tmp = Join-Path $env:TEMP "sber_forecast_test.csv"
    $okPost = Send-Forecast (Join-Path $Root "data\sample_sales.csv") (Join-Path $Root "data\sample_stock.csv") "" $tmp
    $lines = if ($okPost) { (Get-Content $tmp).Count } else { 0 }
    Check "POST /predict -> $($lines - 1) строк прогноза (ожидается 79101)" ($lines -eq 79102)
    try { $r = Invoke-WebRequest "$Base/predict?article=char_article_1" -UseBasicParsing; $okA = $r.StatusCode -eq 200 } catch { $okA = $false }
    Check "GET /predict?article=" $okA
    try { $r = Invoke-WebRequest "$Base/predict/all?format=json" -UseBasicParsing; $okJ = $r.StatusCode -eq 200 } catch { $okJ = $false }
    Check "GET /predict/all?format=json" $okJ
    try { Invoke-WebRequest "$Base/predict" -UseBasicParsing | Out-Null; $code = 200 } catch { $code = [int]$_.Exception.Response.StatusCode }
    Check "GET /predict без параметров -> 400" ($code -eq 400)
    Say ""
    if ($script:failed -eq 0) { Say "Все проверки пройдены ($script:passed)" "Green" }
    else { Say "Не пройдено: $script:failed из $($script:passed + $script:failed)" "Red" }
}

function Show-Menu {
    while ($true) {
        $state = if (Test-Health) { "работает на $Base" } else { "не запущен" }
        Say ""
        Say "==============  Прогноз продаж (команда Авангард)  ==============" "Cyan"
        Say "  Сервис: $state"
        Say "  1 - Запустить сервис (при первом запуске соберёт образ)"
        Say "  2 - Открыть веб-интерфейс в браузере"
        Say "  3 - Сделать прогноз из CSV-файлов (результат в папке results)"
        Say "  4 - Посмотреть прогноз по артикулу или складу"
        Say "  5 - Самопроверка"
        Say "  6 - Журнал контейнера"
        Say "  7 - Пересобрать образ (после изменения кода)"
        Say "  8 - Остановить сервис"
        Say "  0 - Выход"
        $choice = Read-Host "Выберите пункт"
        switch ($choice) {
            "1" { $null = Start-Forecast-Service }
            "2" { if (Ensure-Running) { Start-Process "$Base/" } }
            "3" { Run-Forecast }
            "4" { Run-Lookup }
            "5" { Run-SelfTest }
            "6" { if (Test-DockerReady) { $null = Invoke-Docker logs --tail 40 $Container } }
            "7" { if ((Test-DockerReady) -and (Build-Image)) { Stop-Forecast-Service; $null = Start-Forecast-Service } }
            "8" { Stop-Forecast-Service }
            "0" { return }
            default { Warn "Нет такого пункта" }
        }
    }
}

switch ($Action.ToLower()) {
    ""         { Show-Menu }
    "start"    { if (Start-Forecast-Service) { Start-Process "$Base/" } }
    "open"     { if (Ensure-Running) { Start-Process "$Base/" } }
    "forecast" { Run-Forecast }
    "test"     { Run-SelfTest }
    "logs"     { if (Test-DockerReady) { $null = Invoke-Docker logs --tail 40 $Container } }
    "rebuild"  { if ((Test-DockerReady) -and (Build-Image)) { Stop-Forecast-Service; $null = Start-Forecast-Service } }
    "stop"     { Stop-Forecast-Service }
    default    { Warn "Неизвестное действие '$Action'. Доступно: start, open, forecast, test, logs, rebuild, stop" }
}
