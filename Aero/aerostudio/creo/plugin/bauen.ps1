<#
    Baut das Aero-Studio-Plugin fuer Creo Parametric 8.

    Erzeugt aerostudio.jar aus den Quellen unter src/.
    Braucht ein JDK 11 - das ist die von Creo 8 unterstuetzte Java-Version.

    Aufruf:
        powershell -ExecutionPolicy Bypass -File .\bauen.ps1
#>

[CmdletBinding()]
param(
    [string] $CreoLoadpoint = "C:\Program Files\PTC\Creo 8.0.3.0",
    [string] $JdkHome
)

$ErrorActionPreference = "Stop"
$hier = Split-Path -Parent $MyInvocation.MyCommand.Path

function Fehl([string] $m) { Write-Host "  [FEHLER] $m" -ForegroundColor Red }
function Ok([string] $m)   { Write-Host "  [ok]     $m" -ForegroundColor Green }
function Info([string] $m) { Write-Host "           $m" -ForegroundColor DarkGray }

Write-Host ""
Write-Host "  Aero Studio - Creo-Plugin bauen" -ForegroundColor White

# --------------------------------------------------------------- JDK 11
if (-not $JdkHome) {
    $kandidaten = Get-ChildItem "C:\Program Files\Java" -Directory -ErrorAction SilentlyContinue |
                  Where-Object { $_.Name -match "jdk-11" } |
                  Sort-Object Name -Descending
    if ($kandidaten) { $JdkHome = $kandidaten[0].FullName }
}
if (-not $JdkHome -or -not (Test-Path (Join-Path $JdkHome "bin\javac.exe"))) {
    Fehl "Kein JDK 11 gefunden. Mit -JdkHome '<Pfad>' angeben."
    Info "Creo 8 unterstuetzt fuer J-Link Java 11. Neuere JDKs erzeugen Bytecode,"
    Info "den die JVM in Creo nicht laedt."
    exit 1
}
$javac = Join-Path $JdkHome "bin\javac.exe"
$jar   = Join-Path $JdkHome "bin\jar.exe"
Ok "JDK: $JdkHome"

# ---------------------------------------------------------------- otk.jar
$otk = Join-Path $CreoLoadpoint "Common Files\text\java\otk.jar"
if (-not (Test-Path $otk)) {
    Fehl "otk.jar nicht gefunden unter: $otk"
    Info "Die Creo-Komponente 'API Toolkits' ist nicht installiert."
    Info "Ueber denselben PTC-Installer nachinstallieren, kostenlos."
    exit 1
}
Ok "otk.jar: $otk"

# ------------------------------------------------------------ Uebersetzen
$build = Join-Path $hier "build"
if (Test-Path $build) { Remove-Item $build -Recurse -Force }
New-Item -ItemType Directory -Path $build | Out-Null

$quellen = Get-ChildItem (Join-Path $hier "src") -Recurse -Filter *.java | ForEach-Object { $_.FullName }
Info "$($quellen.Count) Quelldatei(en)"

& $javac -encoding UTF-8 -source 11 -target 11 -Xlint:-options -cp $otk -d $build $quellen
if ($LASTEXITCODE -ne 0) { Fehl "Uebersetzen fehlgeschlagen."; exit 1 }
Ok "uebersetzt"

# ------------------------------------------------------------------- JAR
$ziel = Join-Path $hier "aerostudio.jar"
if (Test-Path $ziel) { Remove-Item $ziel -Force }
& $jar --create --file $ziel -C $build .
if ($LASTEXITCODE -ne 0) { Fehl "JAR-Erstellung fehlgeschlagen."; exit 1 }
Ok "aerostudio.jar erstellt"

# --------------------------------------------------- protk.dat schreiben
# Der Klassenpfad muss absolut sein, deshalb wird die Datei hier erzeugt
# statt sie mit festen Pfaden im Repository zu halten.
$protk = Join-Path $hier "protk.dat"
@"
name                AeroStudio
startup             otk_java
toolkit             object
creo_type           parametric
java_app_class      de.rennschmiede.aerostudio.AeroStudioPlugin
java_app_classpath  $ziel
java_app_start      start
java_app_stop       stop
allow_stop          true
delay_start         false
text_dir            $(Join-Path $hier "text")
end
"@ | Set-Content -Path $protk -Encoding ASCII
Ok "protk.dat geschrieben"

Write-Host ""
Write-Host "  Fertig. Naechster Schritt in Creo:" -ForegroundColor White
Info "Datei -> Optionen -> Konfigurationseditor, oder"
Info "Werkzeuge -> Hilfsanwendungen -> Registrieren -> diese Datei waehlen:"
Write-Host "    $protk" -ForegroundColor Cyan
Write-Host ""
