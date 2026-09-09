# Aero-Studio-Plugin für Creo Parametric 8

Ersetzt den Mapkey. Zwei Befehle im Menü **Werkzeuge**:

| Befehl | Wirkung |
|---|---|
| **Aero Studio: IBL importieren** | Datei wählen, als Bezugskurve einfügen, Pfad und Feature-Nummer im Modell merken |
| **Aero Studio: IBL aktualisieren** | Dieselbe Datei erneut einlesen, ohne Dialog |

Der zweite Befehl ist der eigentliche Zweck. Creo liest eine importierte Bezugskurve beim Regenerieren nicht neu ein, und *Definition bearbeiten* öffnet den Import DataDoctor statt des Dateidialogs. Über die API geht es sauber: `WFeature.RedefineImportFeature()` liest die Datei in das **bestehende** Feature neu ein. Alle nachgelagerten Features — Boundary Blend, Verdicken, Verrundungen — bleiben erhalten und regenerieren einfach mit.

---

## ⚠ Lizenzvorbehalt — bitte zuerst lesen

Der IBL-Import ist in der Creo-API **nur über `wfc*` erreichbar**, also über das kostenpflichtige **Creo Object TOOLKIT Java**. Belegt durch die Fabrikmethoden in `otk.jar`:

| Fabrik | Formate |
|---|---|
| `pfcModel` (freies J-Link) | IGES, STEP, VDA, DXF, ACIS, STL, Parasolid, CATIA, UG, JT … |
| `wfcModel` (kostenpflichtig) | **IBL**, PTS, Inventor, Solid Edge |

Die auf diesem Rechner hinterlegte Lizenz ist eine Studentenlizenz mit den Optionen `CREOPMA_Student6`, `CREODMA_Student3`, `CREOLAY_Student3`, `CREOILLUS_STANDARD`. **Keine TOOLKIT-Option darunter.** Es ist deshalb wahrscheinlich, dass Creo das Plugin mit einem Lizenzfehler ablehnt.

**Trotzdem testen** — es kostet zwei Minuten, und an Hochschulen liegen TOOLKIT-Lizenzen manchmal auf einem Lizenzserver, der in der lokalen Datei nicht auftaucht.

Wenn es an der Lizenz scheitert, gibt es einen **lizenzfreien Weg**: IGES statt IBL. `pfcModel.IntfIges_Create` und `Solid.CreateImportFeat` gehören zur freien Ebene und tragen keinen Lizenzvermerk. Dafür müsste der Exporter IGES-Kurven statt IBL schreiben — machbar, aber eine bewusste Formatentscheidung.

---

## Bauen

```
powershell -ExecutionPolicy Bypass -File .\bauen.ps1
```

Erzeugt `aerostudio.jar` und schreibt `protk.dat` mit den absoluten Pfaden dieses Rechners. Braucht ein **JDK 11** — das ist die von Creo 8 unterstützte Java-Version. Neuere JDKs erzeugen Bytecode, den die JVM in Creo nicht lädt. Auf diesem Rechner liegt es unter `C:\Program Files\Java\jdk-11.0.15.1`.

Liegt Creo woanders:

```
powershell -ExecutionPolicy Bypass -File .\bauen.ps1 -CreoLoadpoint "D:\PTC\Creo 8.0.x.x"
```

`protk.dat` wird beim Bauen erzeugt und ist deshalb **nicht** im Git — die Pfade sind rechnerabhängig.

---

## Registrieren

1. Creo starten.
2. **Werkzeuge → Hilfsanwendungen** (Auxiliary Applications).
3. **Registrieren**, die erzeugte `protk.dat` in diesem Ordner wählen.
4. Der Eintrag `AeroStudio` erscheint. **Starten**.
5. Im Menü **Werkzeuge** stehen jetzt die beiden Befehle.

Damit das Plugin bei jedem Creo-Start automatisch lädt, den Pfad zur `protk.dat` in der `config.pro` unter `toolkit_registry_file` eintragen.

---

## Benutzen

1. Teil öffnen oder neu anlegen.
2. **Werkzeuge → Aero Studio: IBL importieren**, Datei wählen.
3. Die Kurve erscheint. Pfad und Feature-Nummer werden als Modellparameter `AERO_IBL_PFAD` und `AERO_IBL_FEAT_ID` gespeichert — sichtbar unter Werkzeuge → Parameter.
4. Nach jeder Änderung der Datei durch das Werkzeug: **Werkzeuge → Aero Studio: IBL aktualisieren**. Kein Dialog, keine Auswahl.

Der Ablauf ist absichtlich idempotent: Aktualisieren lässt sich beliebig oft auslösen. Wurde das Feature zwischenzeitlich gelöscht, importiert das Plugin neu, statt eine Fehlermeldung zu werfen.

---

## Koordinatensystem

Das Plugin sucht ein Koordinatensystem namens `CS_AERO` und nimmt, falls keines existiert, das erste im Modell. Seit der Exporter die Koordinaten bereits in das System der Creo-Vorlage dreht, genügt das Standard-Koordinatensystem — `CS_AERO` wird nur noch bevorzugt, falls jemand eines angelegt hat.

---

## Wenn etwas nicht funktioniert

Meldungen des Plugins landen im **Creo-Startfenster** (dem Konsolenfenster hinter Creo), erkennbar am Präfix `[Aero Studio]`. Fehler erscheinen zusätzlich als Dialog.

| Symptom | Ursache |
|---|---|
| Eintrag erscheint nicht in den Hilfsanwendungen | Pfad in `protk.dat` falsch, oder Datei nicht ASCII |
| Start schlägt mit Lizenzfehler fehl | Object TOOLKIT Java nicht lizenziert — siehe Lizenzvorbehalt oben |
| `ClassNotFoundException` | `java_app_classpath` zeigt nicht auf die gebaute `aerostudio.jar` |
| `UnsupportedClassVersionError` | mit einem anderen JDK als 11 gebaut |
| Befehle fehlen im Menü | `text_dir` zeigt nicht auf den Ordner `text` mit `msg_aerostudio.txt` |

---

## Aufbau

```
plugin/
├── src/de/rennschmiede/aerostudio/
│   ├── AeroStudioPlugin.java   Einstiegspunkt, Befehle, Menüeinträge
│   └── IblImport.java          Import- und Aktualisierungslogik
├── text/msg_aerostudio.txt     Beschriftungen der Menüeinträge
├── bauen.ps1                   Übersetzen, JAR packen, protk.dat schreiben
└── README.md
```
