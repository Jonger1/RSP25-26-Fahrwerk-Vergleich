# Aero Studio

Werkzeug zum Entwerfen von Formula-Student-Flügeln: Profil wählen oder formen,
zur Kaskade anordnen, über die Spannweite verteilen, gegen das Reglement
prüfen, als `.ibl` nach Creo exportieren.

## Starten

**Doppelklick auf `Aero Studio.bat`.** Beim ersten Mal legt der Starter eine
eigene Python-Umgebung unter `.venv` an und installiert die Pakete aus
`requirements.txt`; das dauert ein paar Minuten und passiert nur einmal.
Danach öffnet sich der Browser auf <http://127.0.0.1:8051>.

Wenn etwas schiefgeht: Der Ordner `.venv` kann gefahrlos gelöscht werden, beim
nächsten Start wird er neu angelegt.

## Von Hand, für Entwicklungsarbeit

```
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt -r requirements-dev.txt
.venv\Scripts\python -m aerostudio.ui.app
```

Tests (rund drei Minuten, aus diesem Ordner heraus oder aus der
Projektwurzel — `conftest.py` sorgt für beides):

```
.venv\Scripts\python -m pytest
```

## Wo was liegt

| Ordner | Inhalt |
|---|---|
| `aerostudio/geometrie/` | Profil, Spline, Kaskadenanordnung, Spannweitenverteilung, Verwindung |
| `aerostudio/aero/` | Panelverfahren, Traglinie, Profilpolare, Bodeneffekt, Entwurfsvorschlag, Generator |
| `aerostudio/regeln/` | Reglement als YAML (`rules_2026.yaml`, `rules_2027_draft.yaml`) und der Prüfer darüber |
| `aerostudio/spec/` | Datenmodell des AeroSpec und der Fahrzeugbezug `vehicle_ref.yaml` |
| `aerostudio/formate/` | IBL-Schreiber, Exportplanung, Creo-Skelett |
| `aerostudio/creo/` | Versionsprofile, Prüfkurve und Prüfprotokoll aus M0, Plugin-Ansatz |
| `aerostudio/ui/` | Dash-Oberfläche |
| `tests/` | Testfälle, `test_umgebung.py` wacht über die Paketliste |
| `profile/` | Profilkatalog als `.dat` mit Notizen |

## Zwei Regeln, die das Projekt tragen

**Der einzige Zustand ist das AeroSpec-YAML.** Die Oberfläche liest es, stellt
es dar und schreibt hinein — sonst nirgendwohin. Jede Rechnung, jeder Export,
jede Regelprüfung leitet sich allein daraus ab. Deshalb sind Oberfläche und
Kommandozeile gleichwertig und jeder Designstand ist eine diffbare Textdatei.

**Reglement und Creo-Version sind Konfiguration, kein Code.** Beide sind
versioniert und stehen in YAML-Dateien. Wer das durchhält, übersteht sowohl
die Rules 2027 als auch das nächste Creo-Upgrade ohne Umbau.

## Weiterlesen

* [KONZEPT_AeroStudio.md](KONZEPT_AeroStudio.md) — warum das Werkzeug so
  aufgebaut ist, wie es aufgebaut ist
* [MEILENSTEINE.md](MEILENSTEINE.md) — Arbeitsplan M0 bis M9, aktueller Stand,
  was als Nächstes ansteht
* [ANLEITUNG_Creo.md](ANLEITUNG_Creo.md) — von der `.ibl`-Datei zum Bauteil in
  Creo, Schritt für Schritt
