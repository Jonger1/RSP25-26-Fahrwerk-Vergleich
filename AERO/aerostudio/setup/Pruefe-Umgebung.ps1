<#
    RSP Aero Studio - Umgebungspruefung

    Prueft, ob auf diesem Rechner alles vorhanden ist, was Aero Studio braucht.
    Aendert NICHTS, liest nur. Gefahrlos beliebig oft ausfuehrbar.

    Aufruf:
        powershell -ExecutionPolicy Bypass -File .\Pruefe-Umgebung.ps1

    Dieses Skript ist der erste Baustein des spaeteren Installers (M6).
#>

[CmdletBinding()]
param(
    [string] $PtcRoot = "C:\Program Files\PTC"
)

$ErrorActionPreference = 'Continue'
$script:Fehler   = @()
$script:Warnung  = @()
$script:Befunde  = [ordered]@{}

function Write-Titel([string] $t) {
    Write-Host ""
    Write-Host "== $t " -NoNewline -ForegroundColor Cyan
    Write-Host ("=" * [Math]::Max(0, 60 - $t.Length)) -ForegroundColor Cyan
}
function Ok([string] $m)   { Write-Host "  [ok]    $m" -ForegroundColor Green }
function Warn([string] $m) { Write-Host "  [warn]  $m" -ForegroundColor Yellow; $script:Warnung += $m }
function Fehl([string] $m) { Write-Host "  [FEHLT] $m" -ForegroundColor Red;    $script:Fehler  += $m }
function Info([string] $m) { Write-Host "          $m" -ForegroundColor DarkGray }

<#
    Creo legt Modelldateien versioniert ab: "teil.prt.1", "teil.prt.2", ...
    In der config.pro steht dagegen der versionslose Name, und Creo loest ihn
    auf die hoechste vorhandene Version auf. Ein blosses Test-Path auf den
    versionslosen Namen meldet deshalb faelschlich "fehlt".
    Diese Funktion prueft beides und liefert die tatsaechlich gefundene Datei.
#>
function Get-CreoDatei([string] $pfad) {
    if (Test-Path $pfad) { return (Get-Item $pfad) }
    $ordner = Split-Path $pfad -Parent
    $name   = Split-Path $pfad -Leaf
    if (-not $ordner -or -not (Test-Path $ordner)) { return $null }
    $muster = [regex]::Escape($name) + '\.\d+$'
    $treffer = Get-ChildItem -Path $ordner -File -ErrorAction SilentlyContinue |
               Where-Object { $_.Name -match $muster } |
               Sort-Object { [int]($_.Name -replace '^.*\.(\d+)$', '$1') } -Descending
    if ($treffer) { return $treffer[0] }
    return $null
}

Write-Host ""
Write-Host "  RSP Aero Studio - Umgebungspruefung" -ForegroundColor White
Write-Host "  $(Get-Date -Format 'yyyy-MM-dd HH:mm')  auf  $env:COMPUTERNAME / $env:USERNAME" -ForegroundColor DarkGray

# ---------------------------------------------------------------- Creo finden
Write-Titel "Creo Parametric"

$creo = $null
if (Test-Path $PtcRoot) {
    $kandidaten = Get-ChildItem -Path $PtcRoot -Directory -ErrorAction SilentlyContinue |
                  Where-Object { $_.Name -match '^Creo\s' } |
                  Sort-Object Name -Descending
    if ($kandidaten) {
        $creo = $kandidaten[0]
        Ok "$($creo.Name)"
        Info $creo.FullName
        $script:Befunde['creo_version']  = $creo.Name
        $script:Befunde['creo_loadpoint'] = $creo.FullName
        if ($kandidaten.Count -gt 1) {
            Warn "Mehrere Creo-Versionen installiert: $($kandidaten.Name -join ', ')"
            Info "Modelldateien immer in der AELTESTEN produktiv genutzten Version speichern."
            Info "Creo oeffnet aeltere Dateien, aber niemals neuere."
        }
    } else {
        Fehl "Unter $PtcRoot ist keine Creo-Installation zu finden."
    }
} else {
    Fehl "Verzeichnis $PtcRoot existiert nicht. Ist Creo woanders installiert? Dann: -PtcRoot <Pfad>"
}

# ------------------------------------------------------------------- J-Link
Write-Titel "J-Link / API Toolkits  (fuer M5 CREOSON, M7 Plugin)"

if ($creo) {
    $jarPfad = Join-Path $creo.FullName "Common Files\text\java\otk.jar"
    if (Test-Path $jarPfad) {
        $mb = [Math]::Round((Get-Item $jarPfad).Length / 1MB, 1)
        Ok "otk.jar vorhanden ($mb MB)"
        Info $jarPfad
        $script:Befunde['otk_jar'] = $true
    } else {
        Warn "otk.jar fehlt - Komponente 'API Toolkits' nicht installiert."
        Info "Erst ab M5 noetig. Nachinstallieren ueber denselben PTC-Installer, kostenlos."
        $script:Befunde['otk_jar'] = $false
    }
    Info "Hinweis: Ein vorhandener Ordner 'otk_java_examples' beweist nichts - nur die JAR zaehlt."
}

# ---------------------------------------------------------------- Vorlagen
Write-Titel "Vorlagen und Genauigkeit"

$configDateien = @()
if ($creo) {
    $configDateien += (Join-Path $creo.FullName "Common Files\text\config.pro")
    $configDateien += (Join-Path $creo.FullName "Parametric\bin\config.pro")
}
$configDateien += (Join-Path $env:USERPROFILE "config.pro")
$configDateien += (Join-Path ([Environment]::GetFolderPath('MyDocuments')) "config.pro")

$gefundeneConfigs = $configDateien | Where-Object { Test-Path $_ } | Select-Object -Unique
if ($gefundeneConfigs) {
    foreach ($c in $gefundeneConfigs) { Ok "config.pro: $c" }
} else {
    Warn "Keine config.pro gefunden - Creo laeuft mit reinen Werkseinstellungen."
}

# Die zuletzt gelesene Zuweisung gewinnt in Creo.
$vorlage = $null; $absAcc = $null; $absOn = $null; $unitSys = $null
foreach ($c in $gefundeneConfigs) {
    foreach ($zeile in (Get-Content $c -ErrorAction SilentlyContinue)) {
        $z = $zeile.Trim()
        if ($z -match '^\s*template_solidpart\s+(.+)$')        { $vorlage = $Matches[1].Trim() }
        if ($z -match '^\s*default_abs_accuracy\s+(.+)$')       { $absAcc  = $Matches[1].Trim() }
        if ($z -match '^\s*enable_absolute_accuracy\s+(\S+)')   { $absOn   = $Matches[1].Trim() }
        if ($z -match '^\s*pro_unit_sys\s+(\S+)')               { $unitSys = $Matches[1].Trim() }
    }
}

if ($vorlage) {
    $vorlageDatei = Get-CreoDatei $vorlage
    if ($vorlageDatei) {
        Ok "Teilevorlage: $(Split-Path $vorlage -Leaf)"
        Info "gefunden als $($vorlageDatei.Name)"
        Info $vorlageDatei.FullName
        $script:Befunde['template_solidpart'] = $vorlage
    } else {
        Fehl "Teilevorlage in config.pro eingetragen, aber nicht vorhanden: $vorlage"
        $script:Befunde['template_solidpart'] = "FEHLT: $vorlage"
    }
} else {
    Warn "Keine eigene Teilevorlage konfiguriert - Creo nutzt seine Werksvorlagen."
    if ($creo) {
        $ptcVorlage = Join-Path $creo.FullName "Common Files\templates\mmns_part_solid_abs.prt"
        if (Test-Path $ptcVorlage) { Info "Ersatzweise verwendbar: mmns_part_solid_abs.prt" }
    }
}

if ($absOn -eq 'yes') { Ok "enable_absolute_accuracy yes" }
else { Warn "enable_absolute_accuracy steht nicht auf yes - absolute Genauigkeit nicht umschaltbar." }

if ($absAcc) {
    Ok "default_abs_accuracy $absAcc"
    if ([double]::TryParse($absAcc, [ref]([double]0))) {
        $wert = [double]$absAcc
        if ($wert -gt 0.01) {
            Warn "Genauigkeit groeber als 0.01 mm - an 2-mm-Hinterkanten und 3-mm-Nasenradien zu grob."
        }
    }
} else {
    Warn "default_abs_accuracy nicht gesetzt."
}

if ($unitSys) { Info "pro_unit_sys $unitSys  (nur Rueckfallebene; die Vorlage selbst traegt die Einheiten)" }

# ----------------------------------------------------------------- Python
Write-Titel "Python  (ab M1)"

$py = $null
foreach ($kandidat in @('python', 'py')) {
    $cmd = Get-Command $kandidat -ErrorAction SilentlyContinue
    if ($cmd) { $py = $cmd; break }
}
if ($py) {
    $ver = (& $py.Source --version 2>&1) -join ' '
    if ($ver -match '(\d+)\.(\d+)\.(\d+)') {
        $maj = [int]$Matches[1]; $min = [int]$Matches[2]
        if ($maj -eq 3 -and $min -ge 10) { Ok "$ver" } else { Warn "$ver - Aero Studio braucht Python 3.10 oder neuer." }
        $script:Befunde['python'] = $ver
    } else {
        Warn "Python gefunden, Version nicht lesbar: $ver"
    }
    Info $py.Source
} else {
    Fehl "Kein Python gefunden. Ab M1 noetig: Python 3.10 oder neuer."
}

# ------------------------------------------------------------------- Java
Write-Titel "Java  (erst ab M5 fuer CREOSON)"

$javaCmd = Get-Command java -ErrorAction SilentlyContinue
if ($javaCmd) {
    $jv = (& java -version 2>&1) -join ' '
    if ($jv -match '"(\d+)') {
        $jmaj = [int]$Matches[1]
        if ($jmaj -eq 11) {
            Ok "Java $jmaj - passt zu Creo 8"
        } else {
            Warn "Java $jmaj installiert. Creo 8 unterstuetzt fuer J-Link Java 11."
            Info "Fuer M5 wird vermutlich zusaetzlich ein JDK 11 gebraucht. Heute kein Problem."
        }
        $script:Befunde['java'] = $jmaj
    }
} else {
    Warn "Kein Java im PATH. Erst ab M5 relevant."
}

# --------------------------------------------------------------- Ergebnis
Write-Titel "Ergebnis"

if ($script:Fehler.Count -eq 0 -and $script:Warnung.Count -eq 0) {
    Write-Host "  Alles vorhanden. Nichts zu installieren." -ForegroundColor Green
} elseif ($script:Fehler.Count -eq 0) {
    Write-Host "  Einsatzbereit fuer M0 bis M4." -ForegroundColor Green
    Write-Host "  $($script:Warnung.Count) Hinweis(e) fuer spaetere Meilensteine:" -ForegroundColor Yellow
    foreach ($w in $script:Warnung) { Write-Host "    - $w" -ForegroundColor Yellow }
} else {
    Write-Host "  $($script:Fehler.Count) Problem(e), die behoben werden muessen:" -ForegroundColor Red
    foreach ($f in $script:Fehler) { Write-Host "    - $f" -ForegroundColor Red }
}

Write-Host ""
Write-Host "  Werte fuer creo8.yaml:" -ForegroundColor White
foreach ($k in $script:Befunde.Keys) {
    Write-Host ("    {0,-20} {1}" -f $k, $script:Befunde[$k]) -ForegroundColor DarkGray
}
Write-Host ""

if ($script:Fehler.Count -gt 0) { exit 1 }
exit 0
