# RSP Aero Studio — Meilensteinplan

Arbeitsplan zum Durchgehen. Jeder Meilenstein endet mit etwas, das man **in Creo anfassen kann**, plus Commit und Push. Kein Meilenstein wird abgehakt, bevor sein "Fertig, wenn"-Kriterium nachweislich erfüllt ist.

Begleitdokument: [KONZEPT_AeroStudio.md](KONZEPT_AeroStudio.md)

---

## Die Plugin-Frage vorab beantwortet

Es gibt drei Ausbaustufen der Creo-Anbindung. Sie bauen aufeinander auf — wir müssen uns jetzt nicht festlegen, aber die Architektur muss von Anfang an auf Stufe 2 zulaufen.

| Stufe | Was | PTC-Lizenz nötig? | Aufwand | Wann |
|---|---|---|---|---|
| **0 — Dateiübergabe** | Tool schreibt `.ibl`, du importierst von Hand (3 Klicks) | keine | — | ab M1 nutzbar |
| **1 — CREOSON-Automatisierung** | Python steuert Creo: Parameter setzen, Mapkey für den Import feuern, regenerieren, STEP exportieren | **keine** — CREOSON läuft ab Creo 3.0 ohne Zusatzlizenz auf dem kostenlosen J-Link | mittel | **M5, das realistische Ziel** |
| **2 — Echtes Ribbon-Plugin** | Eigener Reiter "Aero Studio" in Creo mit Buttons "Spec laden", "Update", "Regelcheck" | Ribbon-Buttons und Menüs: **kostenloses J-Link reicht.** Nur eingebettete PTC-Dialoge (uifc) brauchen die kostenpflichtige Object-TOOLKIT-Lizenz — ein normales Java-Swing-Fenster geht auch ohne | hoch | M6, optional |

**Empfehlung: Stufe 1 als Zielbild, Stufe 2 nur wenn das Team es wirklich täglich benutzt.** Stufe 1 liefert 95 % des Nutzens (ein Klick in Python statt in Creo) bei einem Bruchteil des Aufwands. Ein Ribbon-Button ist Komfort, keine Funktion.

**Eine harte technische Randbedingung, die den Plan prägt:** Eine importierte Bezugskurve in Creo liest ihre Quelldatei **nicht** bei der Regenerierung neu ein — *Edit Definition* öffnet den Import DataDoctor, nicht den Dateidialog. Ein geändertes Profil bedeutet also immer: altes Import-Feature löschen, neu importieren. Genau dafür gibt es in CREOSON die Funktion `interface.mapkey`, die einen aufgezeichneten Mapkey in Creo abspielt. Das ist der Kern von M5.

Daraus folgt die Aufteilung, die sich durch den ganzen Plan zieht:

- **Punktgeometrie** (Profilkonturen) → Datei + Re-Import per Mapkey
- **Layoutparameter** (Sehne, Anstellwinkel, Gap, Overlap, Spannweite) → echte Creo-Parameter mit Relations, per CREOSON setzbar, regeneriert automatisch

---

## M0 — Umgebung und Machbarkeitsnachweis

**Ziel:** Bevor eine Zeile Anwendungscode entsteht, ist bewiesen, dass der Creo-Weg trägt.

**Aufgaben**
1. Creo-Version und Datecode feststellen.
2. Prüfen, ob bei der Creo-Installation die Komponente **API Toolkits** mitinstalliert wurde. Erkennbar am Ordner `<creo_loadpoint>\<datecode>\Common Files\otk\otk_java` bzw. `otk_java_free`. Falls nicht: nachinstallieren (kostenlos, gleiche CD/Installer).
3. Creo-Starttemplate anlegen: Einheiten **mmNs**, Koordinatensystem `CS_AERO` (Ursprung Vorderachsmitte/Boden, x nach hinten, y nach rechts, z nach oben), Bodenebene.
4. Eine handgeschriebene Test-IBL mit einem bekannten Rechteck importieren (Model → Get Data → Import → Import type: Curve → Placement: `CS_AERO`) und in Creo **nachmessen**.
5. Denselben Import als **Mapkey aufzeichnen** und abspielen.

**Fertig, wenn:** Eine Kurve mit bekannten Sollmaßen sitzt in Creo auf ±0,01 mm richtig, und der Mapkey wiederholt den Import ohne Handeingriff.

**Risiko:** Einheitenverwechslung (Template auf Zoll), falsches KS. Beides hier billig zu finden, in M4 teuer.

**Was ich von dir brauche:** Creo-Version, und ob du auf dem Rechner Software nachinstallieren darfst.

---

## M1 — Profilkern und IBL-Export

**Ziel:** Ein echtes Profil aus dem Tool sitzt maßhaltig in Creo und lässt sich extrudieren.

**Aufgaben**
1. Projektgerüst `aerostudio/` mit pydantic-Datenmodell für ein Einzelprofil.
2. Profilimport aus UIUC-`.dat` (beide gängigen Formatvarianten robust einlesen).
3. NACA-4/5-Generator als analytische Referenz.
4. CST/Kulfan-Repräsentation, Konvertierung Punktwolke ↔ CST, Rückrechnungsfehler messbar machen.
5. Repanelisierung mit Cosinus-Clustering, 60–120 Punkte, Ober-/Unterseite getrennt, Knick an Nase und Hinterkante.
6. Fertigungscheck: Hinterkantendicke ≥ 2,0 mm, Nasenradius ≥ 3,0 mm (T 2.4.1), Mindestdicke über die Sehne. Bei Verletzung: Vorschlag zur Korrektur, nicht nur Fehlermeldung.
7. Krümmungsplot in Plotly — ein zappelnder Krümmungsverlauf ist der beste Frühwarnindikator für schlechte Profile.
8. **IBL-Writer** nach verifiziertem PTC-Format (`open` / `arclength` / `begin section ! n` / `begin curve` / XYZ), Koordinaten in mm im Fahrzeug-KS.
9. DXF-Writer (ezdxf) als Nebenstrecke für Fertigungsvorlagen.
10. Unit-Tests inkl. Regression auf Referenzprofile (E423, S1223).

**Fertig, wenn:** Ein E423 mit 250 mm Sehne, −4° Anstellung, an definierter Position, wird aus dem Tool exportiert, in Creo importiert, in einer Skizze über *Referenzen projizieren* übernommen und extrudiert. Nachgemessene Sehnenlänge und Anstellwinkel stimmen. Screenshot ins Repo.

**Risiko:** Zu viele Punkte → wellige Splines. Gegenmittel ist Teil der Aufgabe (Punktzahl als Parameter, visuelle Kontrolle).

---

## M2 — Mehrelement-Kaskade und Regelvalidator

**Ziel:** Kaskaden lassen sich auslegen und werden live gegen das Reglement geprüft.

**Aufgaben**
1. Element- und Kaskadenmodell mit **Gap / Overlap / aoa_rel** relativ zum Vorgänger (nicht absolute x/y — siehe Konzept 4.4).
2. Geometrische Auflösung: aus Gap/Overlap die absoluten Lagen rechnen, inkl. korrekter senkrechter Gap-Messung zur Hinterkantentangente.
3. Kollisionsprüfung zwischen Elementen (shapely).
4. **Schlitzkonvergenz-Check:** Kanalbreite über die Lauflänge plotten, Warnung bei nicht monoton fallendem Verlauf.
5. Gurney-Flap als Parameter (Höhe in % Sehne).
6. `rules/rules_2026.yaml` mit allen T-8.2-Grenzen, T 2.1.3, T 2.2, T 2.4.1 als Daten.
7. `vehicle_ref.yaml` — Radpositionen, Reifenmaße, Kopfstützenebene, AIP-Position, Federungs-Envelope. Erste Version aus den vorhandenen RSP26-Kinematikdaten.
8. Validator, der **über den gesamten Fahrzustands-Envelope** prüft, nicht nur statisch (T 8.2 verlangt Einhaltung "with any suspension setup with or without a driver").
9. Ampel-Report: Regelnummer, Sollwert, Istwert, kritischster Fahrzustand.

**Fertig, wenn:** Eine 3-Element-Frontflügelkaskade ist definiert, der Validator meldet grün, und eine absichtlich zu hoch gesetzte Variante wird mit korrekter Regelnummer und Millimeterangabe abgelehnt.

---

## M3 — 2D-Aerodynamik und Bewertung

**Ziel:** Aus "sieht gut aus" wird "ist messbar besser".

**Aufgaben**
1. NeuralFoil-Adapter: CL, CD, Cm über AoA- und Reynolds-Sweep, Millisekunden pro Auswertung.
2. XFOIL-Adapter als Referenz und für Grenzschichtdetails, mit sauberem Umgang mit Nichtkonvergenz.
3. Reynoldszahl aus Fahrgeschwindigkeit und Sehne; typischer FS-Bereich dokumentieren.
4. Bodeneffekt: `h/c` als Parameter, Abtriebsverlauf über `h/c`, Balanceverschiebung über den Federungs-Envelope.
5. Zielfunktion `J` mit Gewichten aus Rundenzeit-Sensitivitäten, **integriert über einen AoA- und Höhenbereich** — nicht über einen Punkt. Das war der explizite Fehler in der KTH-Arbeit.
6. Vergleichsplot mehrerer Kandidaten.

**Fertig, wenn:** Ein Screening über mindestens fünf Profile (E423, S1223, LNV109A, NACA 7412, plus ein CST-Kandidat) läuft in unter einer Minute durch und liefert eine begründete Rangfolge mit dokumentierten Randbedingungen.

**Ehrliche Grenze, die im Report stehen muss:** NeuralFoil und XFOIL sind Einzelprofilwerkzeuge. Für die finale Gap/Overlap-Optimierung braucht es 2D-CFD. Das Tool wählt hier das Grundprofil und den groben Arbeitsbereich, nicht die Kaskadenfeinabstimmung.

---

## M4 — 3D-Sektionsstapel und Creo-Skelett

**Ziel:** Ein kompletter, verwundener 3D-Flügel entsteht aus dem Spec heraus.

**Aufgaben**
1. Spannweitenverteilungen `chord(y)`, `twist(y)`, `z(y)`, `x(y)` mit PCHIP-Interpolation.
2. Sektionsstapel-Export: alle Stationen in **einer** IBL pro Element, identische Punktzahl, identischer Startpunkt, identische Umlaufrichtung — sonst verdreht der Boundary Blend.
3. Endplates und Footplates als 2D-Umriss + Dicke, inkl. Keep-out-Check nach T 2.1.3.
4. **Creo-Skelettmodell** `AERO_SKELETON.PRT`: `CS_AERO`, Bodenebene, Radpositionen und die T-8.2-Grenzen als echte Bezugsebenen. Das Reglement wird damit im CAD sichtbar.
5. Boundary Blend über die Sektionskurven, Verdicken, Verrundungen — als dokumentierte, wiederholbare Featurekette.
6. Publish Geometry im Skelett, Copy Geometry in `FW_EL1.PRT`, `FW_EL2.PRT`, `FW_ENDPL.PRT`, Zusammenbau zu `AERO_FRONT.ASM`.

**Fertig, wenn:** Der Frontflügel steht als Baugruppe in Creo, hängt ausschließlich am Skelett, und eine Änderung der Sehnenverteilung im Spec führt nach Neuimport zu einem korrekt regenerierten Modell.

**Risiko:** Boundary-Blend-Fehler bei ungleich strukturierten Sektionen. Deshalb ist die Strukturgleichheit in Punkt 2 hart getestet, nicht gehofft.

---

## M5 — CREOSON-Automatisierung (die eigentliche "Plugin"-Stufe)

**Ziel:** Ein Kommando. Spec rein, aktualisiertes Creo-Modell und STEP für CFD raus.

**Aufgaben**
1. CREOSON-Server aufsetzen, Verbindung aus Python über creopyson prüfen.
2. Layoutparameter als **Creo-Parameter mit Relations** im Skelett anlegen (`FW_E1_CHORD`, `FW_E2_AOA`, `FW_E2_GAP`, …).
3. `bridge.py`: Modell öffnen, Parameter setzen, regenerieren, exportieren.
4. **Mapkey-Generator** für den Ablauf "altes Import-Feature löschen → IBL neu importieren auf `CS_AERO`", abgespielt über `interface.mapkey`.
5. `AERO_SPEC_HASH` als Creo-Parameter setzen → jedes CAD-Modell ist eindeutig einem Git-Stand zugeordnet.
6. STEP-Export für CFD, benannt nach Spec-Hash.
7. Ein CLI-Kommando: `aerostudio push --spec rsp27_front_v3.yaml`.

**Fertig, wenn:** Änderung einer Zahl im YAML → ein Kommando → das Creo-Modell zeigt die Änderung, ohne dass jemand Creo angefasst hat. Und die exportierte STEP trägt den richtigen Hash.

**Risiko:** Mapkeys sind versionsabhängig und brechen bei Creo-Updates. Gegenmittel: Mapkey-Definition in einer eigenen Datei pro Creo-Version, plus ein Selbsttest, der nach jedem Creo-Update anschlägt.

---

## M6 — Ribbon-Plugin in Creo *(optional)*

**Ziel:** Das Team benutzt das Tool aus Creo heraus, ohne Python zu kennen.

**Aufgaben**
1. J-Link-Anwendung (Java), registriert über `protk.dat` in den Auxiliary Applications, `STARTUP` auf `spawn` oder `dll`.
2. Eigener Ribbon-Reiter "Aero Studio" mit den Befehlen *Spec laden*, *Update aus Spec*, *Regelcheck*, *STEP für CFD*.
3. Die Buttons rufen die bestehende Python-CLI aus M5 — die Fachlogik bleibt in Python, das Plugin ist nur Bedienoberfläche.
4. Ausgabe in einem Swing-Fenster (funktioniert mit dem kostenlosen J-Link; eingebettete PTC-Dialoge über uifc bräuchten die kostenpflichtige Object-TOOLKIT-Lizenz).
5. Installationsanleitung für die Teamrechner.

**Fertig, wenn:** Auf einem zweiten Rechner installiert ein Teammitglied das Plugin nach Anleitung und aktualisiert den Flügel per Klick.

**Ehrliche Einschätzung:** Dieser Meilenstein ist reiner Komfort. Wenn die Zeit knapp wird, fällt er zuerst — nicht M5.

---

## M7 — Undertray, DoE und Optimierung

**Ziel:** Optimierungsläufe statt Handiterationen. Hier liegt der größte aerodynamische Hebel.

**Aufgaben**
1. Undertray-Tunnelschnitte durch dieselbe 2D-Pipeline: Einlasshöhe, Kehlenhöhe vorne und hinten (= Neigung), Diffusorhöhe und -winkel — exakt die Parameter, die im KTH-Ansatz per DoE optimiert wurden.
2. Rake als Fahrzeugparameter (1° ≈ +15 % Abtrieb laut Cologne-Fallstudie — im eigenen Setup nachrechnen, nicht übernehmen).
3. Optuna-Anbindung, multikriteriell: Abtrieb gegen Widerstand gegen Breite des Arbeitsbereichs.
4. Batch-Runner: Spec-Varianten → Creo → STEP → CFD-Warteschlange → Ergebnisse zurück in die Zielfunktion.
5. DRS als zwei `aoa`-Zustände, exportiert als Zeilen einer Creo-Familientabelle.

**Fertig, wenn:** Ein DoE über mindestens 50 Varianten läuft ohne Handeingriff durch und liefert eine Pareto-Front.

---

## M8 — Report und Scrutineering-Paket

**Ziel:** Das, was am Ende in der Design-Jury und bei der Technical Inspection auf dem Tisch liegt.

**Aufgaben**
1. Regelkonformitäts-Report je Design: Regelnummer, Sollwert, Istwert, kritischster Fahrzustand.
2. Nachweis der Frontflügelanbindung hinter der AIP (T 3.20.2) und der 120-kN-Rechnung nach T 3.19.4 aus Schraubenbild und Strebenknicklast.
3. Steifigkeitsnachweis nach T 8.3 (200 N auf 225 cm² ≤ 10 mm; 50 N ≤ 25 mm) — FEM-Export oder Handrechnung.
4. Design-Report-Grafiken automatisch aus dem Spec: Profilvergleiche, Kaskadenlayout, Abtriebsverteilung, h/c-Sensitivität.
5. Fertigungsableitungen: Rippen- und Schablonen-DXF, Formtrennebenen.

**Fertig, wenn:** Für ein Design entsteht per Kommando ein PDF, das man ohne Nacharbeit in den Design Report übernehmen kann.

---

## Reihenfolge und Abhängigkeiten

```
M0 Umgebung
 └─ M1 Profilkern + IBL ────────────┐
     ├─ M2 Kaskade + Regelvalidator │
     │   └─ M3 2D-Aero              │
     └─ M4 3D-Stapel + Skelett ◄────┘
         └─ M5 CREOSON  ──► M6 Ribbon-Plugin (optional)
             └─ M7 Undertray + DoE
                 └─ M8 Report
```

**Kritischer Pfad: M0 → M1 → M4 → M5.** Alles andere ist parallelisierbar oder verschiebbar.

---

## Arbeitsweise

- Ein Meilenstein pro Sitzung, am Ende Commit und Push.
- Jeder Meilenstein endet mit einem **Nachweis in Creo**, nicht mit "Code läuft durch".
- Wenn ein "Fertig, wenn"-Kriterium nicht erfüllt ist, wird der Meilenstein nicht abgehakt, sondern der Plan angepasst.
- Regelstand wird bei jedem Meilenstein mitgeführt: Sobald die FS Rules 2027 erscheinen, kommt eine `rules_2027.yaml` dazu und alle Designs laufen erneut durch den Validator.

---

## Quellen zur Plugin-Entscheidung

- [Installing and Working with J-Link (PTC Help)](https://support.ptc.com/help/creo_toolkit/otk_java_pma/r11.0/usascii/creo_toolkit/user_guide/Installing_J_Link.html) — J-Link wird als Teil der Komponente „API Toolkits" mitinstalliert
- [Creating Ribbon Tabs, Groups, and Menu Items (PTC Help)](https://support.ptc.com/help/creo_toolkit/otk_java_pma/r11.0/usascii/creo_toolkit/user_guide/Creating_Ribbon_Tabs_Groups_and_Menu_Items.html)
- [Registry File — protk.dat (PTC Help)](https://support.ptc.com/help/creo_toolkit/otk_cpp_plus/usascii/creo_toolkit/user_guide/Registry_File.html)
- [CS35654 — Synchrone Toolkit-Anwendung beim Start registrieren](https://www.ptc.com/en/support/article/CS35654)
- [CS60620 — Wann ist eine TOOLKIT-Lizenz erforderlich?](https://www.ptc.com/en/support/article/CS60620)
- [CREOSON — Voraussetzungen und Funktionsumfang](https://www.creoson.com/?page_id=5) — ab Creo 3.0, keine Zusatzlizenz
- [creopyson `interface` — u. a. `mapkey`](https://creopyson.readthedocs.io/en/latest/_modules/creopyson/interface.html)
- [To Edit the Definition of Imported Datum Curves (PTC Help)](https://support.ptc.com/help/creo/creo_pma/r11.0/usascii/part_modeling/part_modeling/To_Edit_the_Definition_of_Imported_Datum_Curves.html) — öffnet den Import DataDoctor, kein Neueinlesen der Datei
