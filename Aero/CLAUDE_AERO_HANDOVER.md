# Aero Studio — Handover für Claude und weitere Bearbeiter

Stand: 2026-09-14
Branch: `chatgpt/aero-kaskade-endplates`
PR: #1

## Zweck

Dieses Dokument ist der Übergabestand für Claude und jeden weiteren Entwickler, der am Formula-Student-Aerodynamiktool weiterarbeitet.

**Wichtig:** Bestehende Änderungen nicht neu erfinden oder durch eine zweite Fachlogik ersetzen. Die vorhandenen Module sind bewusst getrennt in Geometrie, lokale 2D-Kaskade, segmentiertes 3D-Flügelsystem und UI.

## Aktueller Architekturstand

### 1. Profil / lokale Geometrie
- `aerostudio/geometrie/profil.py`
- `aerostudio/geometrie/kaskade.py`
- Kaskadenparameter: Profil, Sehne, relativer Winkel, Gap, Overlap.
- Gap/Overlap werden geometrisch aufgelöst; Kollisionen und tatsächlicher Spalt werden berücksichtigt.

### 2. Lokale Kaskaden-Aerodynamik
- `aerostudio/aero/kaskade.py`
- Panelmethode für die gegenseitige 2D-Beeinflussung.
- Profilverluste über vorhandene Profilpolaren.
- Abriss über Saugspitze / Profilgrenze.
- Bewusste Modellgrenzen: keine echte Slot-Grenzschichtmodellierung.

### 3. Kaskaden-Editor
- `aerostudio/ui/kaskade_editor.py`
- Bis zu **6 Elemente**.
- Jedes Element kann einen eigenen Spannweitenbereich `y_von ... y_bis` besitzen.
- Eine Spannweitenlücke ist erlaubt.
- Elemente werden in Gruppen organisiert.
- Eine Gruppe ist ein lokaler 2D-Kaskadenquerschnitt.
- Rolle `Haupt` oder `Flap`.
- Damit sind Frontflügel, getrennte linke/rechte Segmente, Bullwing, Seitenkasten und Heckflügel konzeptionell abbildbar.

### 4. Allgemeines Flügelsystem
- `aerostudio/geometrie/fluegel_system.py`
- `FluegelSystem` begrenzt den aktuellen Editor auf 6 Elemente.
- `Spannweitenbereich` beschreibt `y_von`, `y_bis` in mm.
- `FluegelElement` enthält Profil, Sehne, Winkel, x/z-Position, Gruppe und Baugruppe.
- Baugruppen:
  - `Frontfluegel`
  - `Seitenkasten`
  - `Bullwing`
  - `Heckfluegel`
  - `Beamwing`
  - `Sonstige`

### 5. Gekoppelte 3D-Traglinie
- `aerostudio/aero/traglinie_system.py`
- Gemeinsames Hufeisenwirbelsystem über alle aktiven Spannweitenpanels.
- Panels werden je Element separat über `y_von/y_bis` erzeugt.
- Eine echte y-Lücke wird nicht aufgefüllt.
- Unterschiedliche Baugruppen können sich in y überlappen und trotzdem eigene Wirbelreihen besitzen.
- Die Lösung erfolgt als gemeinsames lineares Gleichungssystem, nicht als künstliche Relaxationsiteration.
- Induzierter Widerstand wird aus der Nachlaufinduktion bestimmt.

**Physikalische Grenze:** Das ist die gekoppelte inviscide 3D-Grundrechnung. Sie ist noch kein CFD-Modell und ersetzt keine Validierung. Die aktuelle 3D-Schicht nutzt lokale Sehnen/Winkel und koppelt die Wirbel, aber noch keine vollständige viskose Polarenkorrektur je Panel.

### 6. Fahrzeug-Aero-Integration
- `aerostudio/aero/fahrzeug_aero.py`
- Lokale/segmentierte Aero-Ergebnisse können in dynamischen Druck, Kräfte, Momente und Aero-Balance überführt werden.
- Ziel: später Frontflügel + Seitenkasten/Bullwing + Heckflügel als gemeinsames Fahrzeugmodell.

### 7. Sweep
- `aerostudio/aero/kaskaden_sweep.py`
- `aerostudio/ui/kaskade_sweep.py`
- Parametrischer Sweep über Gap, Overlap und Winkel.
- Filterung nach Modellgrenze/Abriss und Ranking nach `|CL|/CD`.

### 8. Endplatten
- `aerostudio/aero/endplatten.py`
- Bewusst kalibrierbarer Hook statt erfundenem Prozentaufschlag.
- `wirkungsgrad=0` ist Standard.
- Noch nicht als validierte Endplattenphysik in die zentrale 3D-Rechnung einbauen, solange keine CFD-/Messdaten existieren.

## Tests

Wichtige Tests:
- `tests/test_endplatten.py`
- `tests/test_fluegel_system.py`
- `tests/test_kaskade_editor.py`
- `tests/test_kaskaden_sweep.py`
- `tests/test_traglinie_system.py`

Empfohlener lokaler Aufruf aus `Aero/`:

```text
pytest -q
```

Die vollständige Suite konnte in der ChatGPT-Arbeitsumgebung nicht ausgeführt werden, weil ein lokaler Git-Clone durch die Netzwerkisolation scheitert. Daher **nicht behaupten, dass die gesamte Suite grün ist**, bevor sie auf einem echten Entwicklerrechner/CI gelaufen ist.

## Was als Nächstes sinnvoll ist

### Priorität 1 — viskose Kopplung des 3D-Solvers
Nicht einfach `CL` pauschal skalieren. Stattdessen:
1. lokale Reynoldszahl je Panel bestimmen,
2. passende Profilpolare laden,
3. effektiven Anstellwinkel aus geometrischem Winkel und induziertem Winkel bestimmen,
4. lokalen viskosen `CL/CD` gegen den invisciden Panelwert setzen,
5. Abriss-/Vertrauensgrenzen je Panel ausweisen,
6. Iteration nur dort verwenden, wo die viskose Korrektur wirklich die Zirkulation verändert.

### Priorität 2 — echte 3D-Elementdaten
Der aktuelle `FluegelElement`-Datensatz ist bewusst kompakt. Für die nächste Stufe sollen ergänzt werden:
- `twist(y)` bzw. Winkelverteilung,
- `chord(y)`,
- `x_le(y)`, `z_le(y)`,
- unterschiedliche Profile entlang y,
- Endplatten als Randbedingung/Tip-Modell,
- optionaler Sweep/Dihedral.

### Priorität 3 — Aero-Baugruppen
Eine sinnvolle Standardkonfiguration für das Team ist:
- Frontflügel links/rechts,
- mittleres Frontflügel-/Bullwing-Segment,
- Seitenkasten-Flügel,
- Heckflügel Mainplane,
- Heckflügel Flap.

Nicht erzwingen, dass alle Baugruppen Teil derselben 2D-Kaskade sind.

### Priorität 4 — Fahrzeugzustand
Danach:
- Geschwindigkeit,
- Ride Height vorne/hinten,
- Pitch,
- Roll,
- Steering/Slip-Envelope,
- Aero Balance,
- Front-/Rear-Axle-Downforce,
- Gesamtwiderstand.

Die Ergebnisse sollen als Kennfelder statt nur als Einzelpunktwerte ausgegeben werden.

### Priorität 5 — CFD/Messdaten
Es liegen derzeit im Aero-Repo keine belastbaren CFD-/Messdaten zur Kaskaden- oder Endplattenkalibrierung vor. Sobald sie vorhanden sind:
- Importer nicht mit Fachlogik vermischen,
- Geometrie/Operating Point als Metadaten speichern,
- Vergleich `Tool vs CFD vs Messung`,
- Kalibrierparameter nur datengetrieben bestimmen,
- keine manuell erfundenen Prozentkorrekturen.

## Was ausdrücklich nicht gemacht werden soll

- Keine pauschalen `+10 % Abtrieb`- oder `-15 % Widerstand`-Korrekturen.
- Keine zusätzliche zweite Profil-/Kaskadenphysik in der UI.
- Keine echte 3D-Gültigkeit behaupten, nur weil die Geometrie 3D aussieht.
- Keine Endplattenwirkung als validiert betrachten.
- Keine CFD- oder Messwerte erfinden.
- Keine Änderungen direkt auf `main` während der Entwicklung.

## Zusammenarbeit ChatGPT ↔ Claude

1. **Zuerst dieses Dokument lesen.**
2. Danach `MEILENSTEINE.md` und `KONZEPT_AeroStudio.md` lesen.
3. Bestehende Fachlogik wiederverwenden.
4. Vor größeren physikalischen Änderungen Tests ergänzen.
5. Nach jeder fachlichen Änderung dieses Handover-Dokument aktualisieren, wenn sich Architektur oder Modellgrenzen ändern.
6. Jede nicht validierte Modellannahme explizit als solche markieren.
7. Vor Merge die komplette Test-Suite auf einem Rechner mit funktionierendem Python-/Package-Setup ausführen.

## Aktueller Abschlussstand dieses Arbeitsblocks

Der Arbeitsblock ist **architektonisch abgeschlossen**:
- 6-Element-Kaskade,
- getrennte Spannweitenbereiche,
- segmentiertes Flügelsystem,
- lokale Kaskadenrechnung,
- gekoppelte inviscide 3D-Traglinie,
- Fahrzeug-Aero-Integrationsschicht,
- Sweep,
- Endplatten-Hook,
- Tests und UI-Starter.

Der nächste Entwicklungsblock ist nicht noch mehr UI, sondern die **viskose Panelkopplung + belastbare Validierung**. Danach folgen Endplatten, Fahrzeuginteraktion und CFD-Datenanbindung.
