# Aero Studio einrichten

Diese Anleitung wächst mit den Meilensteinen mit. Ab **M6** ersetzt ein Installer den manuellen Teil — bis dahin ist das hier die Wahrheit.

---

## Umgebung prüfen

Immer zuerst:

```
powershell -ExecutionPolicy Bypass -File .\Pruefe-Umgebung.ps1
```

Das Skript **ändert nichts**, es liest nur. Es findet die Creo-Installation, prüft J-Link, Vorlagen, Genauigkeitseinstellungen, Python und Java und gibt am Ende die Werte aus, die in `creo/profiles/creo8.yaml` gehören.

Liegt Creo woanders:

```
powershell -ExecutionPolicy Bypass -File .\Pruefe-Umgebung.ps1 -PtcRoot "D:\PTC"
```

---

## Was gebraucht wird, und ab wann

| Bestandteil | Ab | Installation |
|---|---|---|
| **Creo Parametric 8** | M0 | vorhanden, Standardinstallation des Lehrstuhls |
| **Teamvorlagen** (gtstarter / stools-se) | M0 | vorhanden, über `config.pro` eingebunden |
| **J-Link** (`otk.jar`) | M5 | Teil der Creo-Komponente „API Toolkits". Fehlt sie, über denselben PTC-Installer nachinstallieren — kostenlos, keine Zusatzlizenz |
| **Python 3.10+** | M1 | python.org, beim Setup „Add to PATH" ankreuzen |
| **Python-Pakete** | M1 | `pip install -r requirements.txt` (kommt mit M1) |
| **CREOSON 2.8.0+** | M5 | Open Source, Release von GitHub `SimplifiedLogic/creoson` |
| **JDK 11** | M5 | nur falls CREOSON mit dem vorhandenen Java nicht startet |

**Für M0 ist nichts zu installieren.** Auf dem geprüften Rechner (Creo 8.0.3.0) war bereits alles vorhanden, `otk.jar` eingeschlossen.

---

## Stand auf dem Referenzrechner

Erhoben am 05.09.2026:

| | |
|---|---|
| Creo | 8.0.3.0, `C:\Program Files\PTC\Creo 8.0.3.0` |
| J-Link | `otk.jar` vorhanden, 4 MB |
| Teilevorlage | `sut_de_startt.prt` aus dem gtstarter-Paket |
| Genauigkeit | absolut, 0,01 mm — bereits korrekt in der `config.pro` |
| Python | 3.10.11 |
| Java | 25 — Creo 8 erwartet für J-Link Java 11, zu klären in M5 |

---

## Zwei Eigenheiten, über die jeder stolpert

**Creo-Dateien sind versioniert.** Auf der Platte liegt `sut_de_startt.prt.4`, in der `config.pro` steht `sut_de_startt.prt`. Creo löst den versionslosen Namen auf die höchste vorhandene Version auf. Jeder Code, der Creo-Dateien sucht, muss beide Formen prüfen — sonst meldet er fälschlich „fehlt". `Pruefe-Umgebung.ps1` macht das in `Get-CreoDatei`, und der IBL-Writer in M1 wird dieselbe Regel brauchen.

**Die Vorlage hat Y als Hochachse, das Tool rechnet mit Z.** Aufgelöst wird das an genau einer Stelle: `CS_AERO` wird gegenüber dem Standard-Koordinatensystem um −90° um X gedreht. Nicht im Exporter — sonst steckt die Konvention an zwei Orten und driftet auseinander. Details im [M0-Prüfprotokoll](../creo/test/M0_PRUEFPROTOKOLL.md).

---

## Geplant für M6: ein richtiger Installer

Heute ist das hier ein Prüfskript plus Anleitung. In M6 wird daraus:

- `Aero Studio Setup.exe` — prüft die Umgebung, richtet die Python-Umgebung ein, legt eine Verknüpfung an
- `Aero Studio.bat` beziehungsweise eine `.exe` zum Starten per Doppelklick, ohne Terminal
- Bedienungsanleitung mit Screenshots

Bis dahin gilt: **Alles, was hier von Hand gemacht wird, wird hier dokumentiert.** Was in dieser Datei fehlt, existiert für andere Teammitglieder nicht.
