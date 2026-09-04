# RSP Aero Studio — Konzept

**2D-Profildesigner + 3D-Aeroplattform mit parametrischer Creo-Anbindung**

Rennschmiede Pforzheim · Konzeptstand 05.09.2026

---

## 0. Kernaussagen vorab

1. **Das Reglement für 2027 existiert noch nicht.** Stand 05.09.2026 ist auf formulastudent.de ausschließlich `FS-Rules_2026_v1.1` (veröffentlicht 25.11.2025) verfügbar; die FSG-News enthalten kein 2027-Dokument. Die FSG Academy, auf der die Regeländerungen für die Folgesaison vorgestellt werden, fand 2025 am **25.10.2025** statt — der Termin für die 2027er-Runde liegt also noch vor uns. **Konsequenz für die Architektur: Das Regelwerk darf nicht hartcodiert werden, sondern muss als versionierte Config-Datei (`rules_2026.yaml`, später `rules_2027.yaml`) im Tool liegen.** Alles unten Beschriebene basiert auf FS Rules 2026 v1.1 als Baseline; die T8-Geometriegrenzen sind seit Jahren stabil, das Risiko einer Umstellung ist gering, aber nicht null — T 8.2.1 wurde für 2026 v1.0 bereits einmal geändert ("Changed height restriction").
2. **Der Flaschenhals ist nicht die Aerodynamik, sondern der CAD-Durchsatz.** Monash Motorsport schafft ~200 CFD-Iterationen in 3 Monaten bei 16–18 h Turnaround von der Designänderung bis zum Ergebnis — der Löwenanteil davon ist Geometrieaufbereitung. Genau hier setzt das Tool an.
3. **Empfohlener Creo-Weg: IBL-Kurvenimport in ein Skelettmodell, nicht DXF-Import in Skizzen.** Formatvergleich und Begründung in Kapitel 7. Die Skizze wird trotzdem gebaut — sie *projiziert* aber nur die importierte Kurve, statt Punkte zu enthalten.
4. **Parametrisierung über Gap/Overlap, nicht über absolute x/y.** Das ist die wichtigste Einzelentscheidung im Datenmodell (Kapitel 4.4).

---

## 1. Regelbasis

### 1.1 Status 2027

| Frage | Antwort (05.09.2026) |
|---|---|
| FS Rules 2027 veröffentlicht? | **Nein.** formulastudent.de/fsg/rules listet nur 2026er Dokumente. |
| Aktueller Stand | FS-Rules 2026 v1.1, aktualisiert 25.11.2025 |
| FSG-Aussage zu v1.1 | Änderungen sind Klarstellungen; keine weiteren Änderungen bis nach dem Event 2026 geplant |
| Wann kommt 2027? | Erfahrungsgemäß Herbst/Winter nach der FSG Academy (2025: 25.10.2025) |

**Handlungsempfehlung:** Regelparameter in `rules/rules_2026.yaml` kapseln, Validator liest die Config. Sobald die 2027er Rules erscheinen: Diff gegen 2026 fahren, neue YAML anlegen, alle bestehenden Designs erneut validieren (Regressionslauf). Das kostet dann eine Stunde statt einer Woche.

### 1.2 Relevante Regeln aus FS Rules 2026 v1.1

Diese Regeln sind die harten Randbedingungen des Designraums und werden 1:1 zu Validator-Checks.

**T 8.2.1 — Höhenbeschränkungen**
- Alle Aeroteile **vor** einer Vertikalebene durch den hintersten Punkt der Vorderfläche der Kopfstützenaufnahme (ohne Polster, hinterste Einstellposition): **< 500 mm** über Boden.
- Alle Aeroteile **vor der Vorderachse**, die weiter außen liegen als der innerste Punkt von Vorderrad/Reifen: **< 250 mm** über Boden.
- Alle Aeroteile **hinter** dieser Ebene: **< 1100 mm** über Boden.

**T 8.2.1 — Breitenbeschränkungen**
- Unter 500 mm Höhe und hinter der Vorderachse: nicht breiter als die Vertikalebene am äußersten Punkt von Vorder- und Hinterrad/Reifen.
- Über 500 mm Höhe: nicht außerhalb des innersten Punktes von Hinterrad/Reifen.

**T 8.2.4 — Längenbeschränkungen**
- Max. **250 mm** hinter dem hintersten Teil der Hinterreifen.
- Max. **700 mm** vor der Vorderseite der Vorderreifen.

**Alle T 8.2-Restriktionen gelten „mit Rädern geradeaus und bei jedem Federungssetup, mit oder ohne Fahrer im Fahrzeug".** → Das ist der Grund, warum dieses Tool ins selbe Repository gehört wie die Fahrwerkskinematik: Der Validator muss über den vollen Hub-/Nick-/Wank-Envelope prüfen, nicht nur über die statische Lage.

**T 8.3 — Steifigkeit und Festigkeit**
- 200 N verteilt auf min. 225 cm², Verformung in Lastrichtung ≤ 10 mm.
- 50 N in beliebiger Richtung an beliebigem Punkt, Verformung ≤ 25 mm.

**T 2.2.1 / T 2.2.2 — Bodenfreiheit**
- Min. 30 mm statisch (bei aktiver Federung in der niedrigsten einstellbaren Position), Reifen ausgenommen, mit Fahrer.
- Schleifschürzen oder Aeroteile, die konstruktiv, fertigungsbedingt oder bewegungsbedingt den Boden berühren: **verboten**.

**T 2.4.1 — Mindestkantenradien** (der praktisch relevanteste Fertigungs-Constraint)
- Für alle Kanten, die ein stehender Fußgänger ohne Hineingreifen berühren kann: **3 mm für alle nach vorne gerichteten Kanten, 1 mm für alle anderen.**
- → **Nasenradius ≥ 3 mm, Hinterkantendicke ≥ 2 mm (Radius 1 mm).** Das muss der Profilgenerator als Zwangsbedingung führen, sonst entwirft man Profile, die durch die Technical Inspection fallen oder in CFK nicht baubar sind.

**T 2.3.2 — Bodywork**
- In jeder Seitenschnittansicht vor der Cockpitöffnung und **außerhalb** des in T 8.2 definierten Bereichs darf Bodywork **keine externen konkaven Krümmungsradien** haben. → Profile müssen innerhalb des T 8.2-Envelopes liegen, sonst greift diese Regel.

**T 2.1.3 — Keep-out-Zone offene Räder**
- Kein Fahrzeugteil in einer Zone, die von zwei Vertikallinien 75 mm vor und 75 mm hinter dem Außendurchmesser von Vorder- und Hinterreifen in der Seitenansicht aufgespannt wird (lateral von der Außen- bis zur Innenebene des Rad/Reifen-Verbunds). Die Rad/Reifen-Ansicht von der Seite muss unverdeckt bleiben.
- → Begrenzt Endplates, Footplates und Undertray-Seitenwände hart.

**T 3.20.1 / T 3.20.2 — Anbindung vor dem Frontschott**
- Sensoren und Aeroteile dürfen vor die Anti-Intrusion-Platte (AIP) ragen, **ihr Chassis-Anbindungspunkt muss aber hinter der AIP liegen.**
- T 3.19.4: Fahrzeuge mit Aeroteilen vor dem Frontschott müssen nachweisen, dass die 120-kN-Spitzenlast nicht überschritten wird — entweder durch physischen Test oder rechnerisch (Standard-IA 95 kN + Versagenslast der Anbindung aus Schraubenabscheren und/oder Strebenknicken).
- → **Der Frontflügelträger muss als Sollbruchstelle ausgelegt und gerechnet werden.** Gehört als Deliverable in den Reportgenerator des Tools.

**IN 1.5.1 — Nach der Technical Inspection erlaubt**
- „Adjustment of winglet angles, but not the position of the complete aerodynamic device in relation to the vehicle."
- → Flapwinkel dürfen zwischen den Disziplinen verstellt werden, die Flügelposition nicht. Ein bewegliches Aerosystem (DRS) ist im Regelwerk nicht verboten; Monash setzt es seit Jahren ein.

---

## 2. Benchmark: Wie andere Teams arbeiten

Recherchestand aus öffentlich zugänglichen Team-Theses, Design-Berichten und Software-Fallstudien.

### 2.1 Monash Motorsport (AUS) — der Referenzprozess

- Paket: Front- und Heckflügel (je mehrelementig) + Undertray + DRS.
- M13 gegenüber M12: **+25 % Abtrieb bei nur +10 % Widerstand**; DRS reduziert den Widerstand auf Geraden um **über 50 %**; erwarteter Gewinn rund 50 Punkte.
- **Der Undertray ist die effizienteste Einzelkomponente: ca. 9× mehr Abtrieb pro Widerstandseinheit als der Heckflügel.**
- Prozess: automatisierte ANSYS-CFX-Workbench-Pipeline, ~20 Mio. Zellen, **16–18 h von der Designänderung bis zum Ergebnis**, ~200 Simulationen in einer dreimonatigen Designphase.
- Aus der zugehörigen Abschlussarbeit (Ockerby, 2015): Die vorherige Methodik war rein CFD-getrieben, Windkanal und Track nur als Validierung — Problem: Bei Abweichung ließ sich nichts mehr ändern. Lehre: **Designprozess so aufsetzen, dass Ergebnisse aus allen drei Werkzeugen zurück in die Geometrie fließen können.** Zusätzlich dokumentiert: In den ersten Wochen der Designphase schwankt die Aeroperformance stark, weil Chassis- und Fahrwerksgeometrie noch wandern — Aero braucht früh eine eingefrorene Schnittstelle.

### 2.2 KTH / Chalmers-Umfeld (Dahlberg, Aeroentwicklung eines FS-Fahrzeugs)

- Profil-Shortlist: **Eppler E423, Douglas/Liebeck LNV109A, NACA 7412, Selig S1223, MSHD** (letzteres speziell für Formula Student entwickelt, aus Pakkam, „High Downforce Aerodynamics for Motorsports").
- Batchläufe in **XFLR5** über AoA-Sweeps. MSHD hatte den höchsten Auftrieb, aber die dünne, lange Hinterkante war nicht fertigbar → **Entscheidung für E423** mit ähnlicher Auftriebscharakteristik.
- **Drei Elemente, alle mit demselben Profil** — historisch bewährter Weg zu hohem Abtrieb.
- Fehler, den man nicht wiederholen sollte: Erste Optimierung mit **festem** Anstellwinkel (−25°) → das Ergebnis war nur für genau diesen Winkel gut, mit Sprung in der Auftriebskurve und massiver Ablösung daneben. Zweiter Anlauf: **Flapwinkel begrenzen, DoE-Werkzeuge (ANSYS Workbench) über die restlichen Parameter laufen lassen** → Konfiguration mit breitem Arbeitsbereich.
- Frontflügel-Bodenabstand als **10 % der Gesamtsehnenlänge** angesetzt; CL des Frontflügels 0,73 (22°) → 0,77 (24°) → 0,78 (26°).
- Undertray: Doppeltunnel, DoE über Einlasshöhe, Diffusorhöhe und zwei Kehlenhöhen (vorne/hinten, für die Tunnelneigung); Längen durch Package und Regeln fixiert.

### 2.3 eMotorsports Cologne (Fallstudie via SimScale)

- Prozess: Profile in CAD importiert → **parametrische Modelle** → 2D-CFD-Screening (Sekunden pro Konfiguration) → 3D-CFD-Validierung → **Rundenzeitsimulation** als finale Bewertung. Rund 40.000 Core-Stunden über fünf Monate.
- Heckflügel: 3 Elemente + Leading-Edge-Flap + Gurneys; Low-Drag-Setup für Acceleration mit **−64,7 % Widerstand** gegenüber High-Downforce.
- **Frontflügel ist ca. 235 % effizienter als der Heckflügel** (Bodeneffekt, geringerer induzierter Widerstand).
- Frontflügel spannweitig segmentiert: innen kurze Sehne, außen am Reifen längste Sehne und höchster Anstellwinkel; Halbrohr-Wirbelgeneratoren an den Endplattenkanten.
- Undertray mit einem gewölbten Haupttunnel; **1° Rake ≈ +15 % Abtrieb.**

### 2.4 Formula Student Team Delft (NL)

- Typische Abtriebsaufteilung im Rennwagenbau: **Heckflügel ~40 %, Frontflügel ~33 %, Undertray ~27 %.**
- Historischer Bruch: Als die Regeln die Flügelbreite auf die Radaußenkanten begrenzten (vorher 1,5 m Heckflügel), musste das gesamte Paket neu gedacht werden — ein Vorgeschmack darauf, was ein Regelwechsel 2027 auslösen kann.

### 2.5 Auslegungsdaumenregeln aus der Literatur

- **Schlitzspalte müssen konvergent sein** (Düsenwirkung).
- Aus Abbott et al.: Maximaler Auftrieb bei **Overlap ≈ 1 % c** und **Gap ≈ 1,2 % c** (für NACA 23012) — profil- und reynoldszahlabhängig, also Startwert, nicht Zielwert.
- Zwei-Element-Auslegung typischerweise mit leicht positivem Overlap.
- **Gurney-Höhe 2–5 % der Sehne** ist der billigste Abtriebsgewinn überhaupt.
- Sehnenverhältnis Hauptelement : zweites Element häufig etwa 2:1.

### 2.6 Was daraus für das Tool folgt

| Beobachtung | Anforderung ans Tool |
|---|---|
| 2D-Screening in Sekunden, 3D in Stunden | Zweistufige Solver-Architektur: schnelles 2D im Tool, 3D nur für Finalisten |
| Fertigbarkeit killt die aerodynamisch besten Profile (MSHD) | Fertigungsconstraints als harte Nebenbedingungen in der Parametrisierung, nicht als Nachprüfung |
| Optimierung bei festem AoA erzeugt Scheinoptima | Zielfunktion über einen AoA- und Bodenabstands-**Bereich** integrieren, nicht über einen Punkt |
| Undertray ist am effizientesten | Undertray-Schnitte müssen durch dieselbe 2D-Pipeline laufen wie Flügelprofile |
| Rundenzeit ist die eigentliche Zielgröße | Kopplung an Rundenzeitsimulation bzw. Sensitivitäten aus den Fahrwerksdaten |
| Frühe Designphase = wandernde Schnittstellen | Fahrzeug-Referenzgeometrie als eigene, versionierte Eingangsdatei |

---

## 3. Systemarchitektur

### 3.1 Technologiestack

Python 3.11+, weil das zum bestehenden RSP-Werkzeugkasten passt (die Kinematik-Plots im Repo sind Plotly-Exporte) und weil die relevanten Bibliotheken dort leben.

```
numpy, scipy             Geometrie und Numerik
pydantic                 Schema und Validierung des AeroSpec-Datenmodells
shapely                  2D-Booleans, Kollisions- und Regelchecks
aerosandbox + neuralfoil 2D-Profilaerodynamik in Millisekunden
xfoil (subprocess)       Referenzlösung, Grenzschichtdetails
ezdxf                    DXF-Export
optuna                   DoE und Optimierung
plotly + dash            UI (konsistent zum bestehenden Repo)
creopyson                Creo-Automatisierung über CREOSON
pytest                   Regressionstests inkl. Regelvalidator
```

### 3.2 Schichtenmodell

```
aerostudio/
├── spec/          AeroSpec-Datenmodell (pydantic) + YAML-Serialisierung
├── geometry/
│   ├── airfoil.py       Profil: Punktwolke, CST/Kulfan, NACA-Generator
│   ├── panel.py         Repanelisierung, Cosinus-Clustering, Glättung
│   ├── element.py       Einzelelement: Profil + Sehne + AoA + Gurney
│   ├── cascade.py       Mehrelementanordnung über Gap/Overlap
│   ├── planform.py      Spannweitenverteilungen chord(y), twist(y), z(y), x(y)
│   └── surfaces.py      Endplates, Footplates, Undertray-Tunnelschnitte
├── rules/
│   ├── rules_2026.yaml  Regelparameter als Daten
│   └── validator.py     Checks gegen den Fahrwerks-Envelope
├── aero/
│   ├── neuralfoil_adapter.py
│   ├── xfoil_adapter.py
│   ├── ground_effect.py  h/c-Korrektur bzw. Surrogatmodell
│   └── objective.py      rundenzeitgewichtete Zielfunktion
├── io/
│   ├── dat.py            UIUC-Import
│   ├── ibl.py            Creo Imported Datum Curve
│   ├── pts.py            Creo Datum Points
│   ├── dxf.py            Sketcher-Import, Fertigungsvorlagen
│   ├── step_iges.py      über CadQuery/OCC, für die CFD-Übergabe
│   └── mesh.py           2D-Netzexport für externe CFD
├── creo/
│   ├── bridge.py         creopyson-Wrapper
│   ├── templates/        Creo-Vorlagenmodelle (Skeleton, Element, Endplate)
│   └── mapkeys.py        Fallback ohne CREOSON
└── ui/                   Dash-App: Profileditor, Kaskadeneditor, Regelampel
```

### 3.3 Das AeroSpec — Single Source of Truth

Eine YAML-Datei beschreibt das gesamte Aeropaket vollständig. Sie liegt im Git, wird gehasht, und der Hash wandert als Creo-Parameter `AERO_SPEC_HASH` ins CAD-Modell. Damit ist zu jedem Zeitpunkt nachvollziehbar, welches CAD-Modell zu welchem CFD-Lauf und welchem Designstand gehört — genau die Rückverfolgbarkeit, die im Engineering-Design-Event gefragt wird.

```yaml
meta:
  name: RSP26_AeroPackage
  rules_version: 2026_v1.1
  vehicle_ref: RSP26_V4          # verweist auf die Fahrzeugreferenzdatei
units: mm
coordinate_system:
  origin: front_axle_ground      # Schnittpunkt VA-Mitte / Bodenebene
  x: rearward
  y: right
  z: up

wings:
  front:
    elements:
      - id: FW_E1
        airfoil: {type: cst, upper: [...], lower: [...]}   # oder {type: dat, file: e423.dat}
        chord_root: 250
        aoa: -4.0
        te_thickness: 2.0
      - id: FW_E2
        airfoil: {type: dat, file: e423.dat}
        chord_root: 125
        aoa_rel: 22.0            # relativ zum Vorgängerelement
        gap: 1.5                 # senkrecht zur TE-Tangente des Vorgängers
        overlap: 2.0             # in Sehnenrichtung, positiv = Überlappung
        gurney: 0
    planform:
      stations:    [0, 150, 300, 450, 570]
      chord_scale: [1.0, 1.0, 0.95, 0.85, 0.70]
      twist:       [0, 0, -1.0, -2.5, -4.0]
      z_offset:    [0, 0, 5, 15, 30]
      x_offset:    [0, 0, 0, 10, 25]
    ground_clearance: 45
  rear:
    ...
undertray:
  sections: [...]                # dieselbe 2D-Pipeline, andere Semantik
export:
  ibl: true
  points_per_curve: 90
  split_at: [le, te]
```

---

## 4. Der 2D-Profildesigner

### 4.1 Drei Wege zum Profil

| Weg | Wann | Vorteil | Nachteil |
|---|---|---|---|
| **Katalog** (`.dat`, UIUC-Format) | Start, Benchmarking | Validierte Profile, Literaturdaten vorhanden | Nicht optimierbar |
| **CST / Kulfan** (8 Parameter pro Seite) | Optimierung | Glatt, wenige Parameter, C∞-stetig, direkt NeuralFoil-kompatibel | Weniger anschaulich |
| **NACA-Generator** (4-/5-stellig) | Lehre, Vergleichsbasis | Analytisch, in Creo direkt als Gleichungskurve abbildbar | Für Abtrieb suboptimal |

**Empfehlung:** Alle drei implementieren, aber intern **immer** nach CST konvertieren. NeuralFoil arbeitet ohnehin intern mit 8 CST-Parametern pro Seite plus Nasenmodifikation und Hinterkantendicke (18 Parameter gesamt) — wer diese Repräsentation als Kern wählt, bekommt Optimierbarkeit und Analyse geschenkt.

### 4.2 Fertigungs- und Regelconstraints direkt in der Parametrisierung

Das ist der Punkt, an dem sich das Tool von einem Profilzeichner unterscheidet. Als **harte Nebenbedingungen**, nicht als nachträgliche Prüfung:

- Hinterkantendicke ≥ 2,0 mm → erfüllt T 2.4.1 (1 mm Radius) und ist in CFK überhaupt laminierbar.
- Nasenradius ≥ 3,0 mm → T 2.4.1 für vorwärtsgerichtete Kanten.
- Minimale lokale Dicke über die gesamte Sehne ≥ 2 × Laminatdicke + Kernminimum (typisch 3–4 mm bei Sandwich).
- Maximale lokale Krümmung begrenzt → sonst lässt sich das Prepreg nicht in die Form drapieren.
- Entformbarkeit: Prüfung auf Hinterschnitte relativ zur gewählten Trennebene.

Genau diese Constraints haben in der KTH-Arbeit das aerodynamisch beste Profil (MSHD) ausscheiden lassen. Wer sie erst am Ende prüft, verliert Wochen.

### 4.3 Repanelisierung — der unterschätzte Schritt

Die Punktverteilung entscheidet über die Qualität der Creo-Splines und über die Regenerationszeit.

- **Cosinus-Clustering**: dicht an Nase und Hinterkante, dünn in der Mitte.
- **60–120 Punkte pro Kurve** sind das Optimum. Weniger → sichtbare Facetten. Mehr → Creo-Splines werden wellig und die Regeneration bricht ein. Für CFD-Netze wird separat mit höherer Auflösung exportiert.
- **Ober- und Unterseite als getrennte Kurvensegmente** exportieren, mit Knick an Nase und Hinterkante. Ein durchgehender Spline über die Nase erzeugt in Creo fast immer eine Beule.
- Glättungsfilter mit Krümmungsanalyse und Krümmungsplot in der UI — ein Profil, dessen Krümmungsverlauf zappelt, produziert im CFD Laminarblasen, die es real nicht gibt.

### 4.4 Mehrelement-Layout: Gap/Overlap statt x/y

**Die wichtigste Modellierungsentscheidung.** Die Position eines Flaps wird nicht als absolute (x, y)-Koordinate gespeichert, sondern relativ zum Vorgängerelement:

- `gap` — kürzester Abstand zwischen der Hinterkante des Vorgängers und der Kontur des Flaps, senkrecht gemessen. Physikalisch die Düsenhöhe.
- `overlap` — Verschiebung in Sehnenrichtung; positiv = der Flap steht vor der Hinterkante des Vorgängers.
- `aoa_rel` — Anstellwinkel relativ zum Vorgänger.

Warum: Diese drei Größen sind die physikalisch wirksamen. Wenn man den Anstellwinkel des Hauptelements ändert, bleiben Gap und Overlap konstant, während x/y automatisch mitwandern. Bei absoluter Speicherung müsste man bei jeder Winkeländerung alle Flaps von Hand nachziehen — das ist die häufigste Fehlerquelle in FS-Aeroteams.

Zusätzlich: **automatischer Konvergenzcheck des Schlitzkanals.** Der Kanal zwischen zwei Elementen wird diskretisiert und die lokale Kanalbreite über die Lauflänge geplottet. Ist sie nicht monoton fallend, warnt das Tool.

Startwerte für die Optimierung: Overlap ≈ 1 % c, Gap ≈ 1,2 % c, Sehnenverhältnis Hauptelement : Flap ≈ 2:1, Gurney 2–5 % c.

---

## 5. 2D-Analyse und Optimierung

### 5.1 Vier Genauigkeitsstufen

| Stufe | Werkzeug | Laufzeit | Einsatz |
|---|---|---|---|
| 0 | Geometrie- und Regelchecks | ms | jede Änderung, live in der UI |
| 1 | **NeuralFoil** | ~1 ms | Vorscreening tausender Varianten, Optimierungsschleife |
| 2 | **XFOIL / MSES** | s | Einzelprofile, Grenzschicht, Transitionsverhalten |
| 3 | externe 2D-CFD (OpenFOAM / Fluent / Star) | min–h | Mehrelement mit Ablösung, bewegter Boden |

NeuralFoil ist ein auf Millionen XFOIL-Läufen trainiertes, physikinformiertes Modell in reinem Python/NumPy. Es konvergiert garantiert — XFOIL tut das bei hoch angestellten Hochauftriebsprofilen notorisch nicht — und ist C∞-stetig, also gradientenbasiert optimierbar. Für ein FS-Team ist das der entscheidende Hebel: 10.000 Konfigurationen in Sekunden statt in Tagen.

**Wichtige Einschränkung, die dokumentiert werden muss:** NeuralFoil und XFOIL sind Einzelprofil-Werkzeuge. Mehrelementkaskaden mit Schlitzströmung sind damit nur näherungsweise über Panelkopplung behandelbar. Für die finale Gap/Overlap-Optimierung braucht es 2D-CFD. Der Workflow lautet deshalb: **NeuralFoil wählt Grundprofil und groben Arbeitsbereich, 2D-CFD optimiert die Kaskade, 3D-CFD validiert.**

### 5.2 Bodeneffekt

Der Frontflügel ist der effizienteste Flügel am Fahrzeug (ca. 235 % gegenüber dem Heckflügel), weil er in Bodennähe arbeitet — und gleichzeitig die größte Risikoquelle, weil die Abtriebsbalance über den Fahrzustand wandert. Das Tool sollte:

- `h/c` als expliziten Parameter führen (Startwert 10 % gemäß Literatur),
- die Abtriebskurve über `h/c` aus einer Surrogat- bzw. Datenbanktabelle plotten,
- und den **Bodenabstand über den Fahrwerks-Envelope** (Hub, Nick, Wank aus den vorhandenen RSP-Kinematikdaten) auswerten, um die Balanceverschiebung zu quantifizieren.

Das ist die direkte Kopplung an das bestehende Fahrwerksprojekt und der Grund, dieses Tool nicht als isolierte Insel zu bauen.

### 5.3 Zielfunktion

Nicht `max CL` und nicht `max CL/CD`, sondern eine rundenzeitgewichtete Größe:

```
J = w_DF · ΔF_z(v_ref) − w_D · ΔF_x(v_ref) − Penalty(Regeln, Fertigung, Balance-Drift)
```

mit `w_DF` und `w_D` aus einer Rundenzeitsimulation (Sensitivitäten `dt_Runde/dAbtrieb` und `dt_Runde/dWiderstand` für das Autocross-/Endurance-Layout). Und: **Die Bewertung läuft über einen Bereich von Anstellwinkeln und Bodenabständen, nicht über einen Punkt** — das war der explizite Lernpunkt aus der KTH-Arbeit.

Optimierung mit Optuna (TPE bzw. NSGA-II) über den CST- und Layout-Parametervektor; multikriteriell Abtrieb gegen Widerstand gegen Arbeitsbereichsbreite.

---

## 6. Vom 2D-Profil zum 3D-Element

### 6.1 Prinzip: Sektionsstapel

Ein 3D-Flügelelement ist ein Stapel identisch strukturierter 2D-Schnitte entlang der Spannweite. „Identisch strukturiert" heißt: gleiche Punktzahl, gleiche Segmentierung, gleiche Startpunkte, gleiche Umlaufrichtung. Das ist die Voraussetzung dafür, dass Creo daraus einen sauberen Boundary Blend baut.

Verteilungsfunktionen über die Spannweite `y`:

| Funktion | Bedeutung | typischer FS-Einsatz |
|---|---|---|
| `chord(y)` | Sehnenverteilung | außen längere Sehne beim Frontflügel (Cologne-Ansatz) |
| `twist(y)` | Verwindung | außen mehr Anstellung, innen entlastet |
| `z(y)` | Höhenverlauf | Anhebung über dem Rad, Bodeneffekt innen |
| `x(y)` | Pfeilung/Versatz | Ausweichen vor der Keep-out-Zone T 2.1.3 |
| `airfoil_blend(y)` | Profilmorphing | selten nötig, aber vorsehen |

Alle als Stützstellen plus monotone kubische Interpolation (PCHIP — kein Overshoot).

### 6.2 Weitere 3D-Elemente in derselben Pipeline

- **Endplates und Footplates:** 2D-Umriss + Dicke + Abkantungen; Regelcheck gegen T 2.1.3 und T 8.2.
- **Gurney-Flaps:** parametrisch an die Hinterkante angehängt, Höhe in % c.
- **Undertray und Diffusor:** Tunnelschnitte sind 2D-Kurven mit den Parametern Einlasshöhe, Kehlenhöhe vorne/hinten (= Neigung), Diffusorhöhe und -winkel — exakt die vier Parameter, die im KTH-Ansatz per DoE optimiert wurden. Läuft durch dieselbe IBL-Exportstrecke.
- **Nasen- und Sidepodflächen:** aus Querschnittsstapeln, gleiche Mechanik.
- **DRS:** Der bewegliche Flap wird als eigenes Element mit zwei `aoa`-Zuständen (`closed`/`open`) modelliert; das Tool exportiert beide Zustände als getrennte Zeilen einer Creo-Familientabelle.

### 6.3 Koordinatensystem-Konvention

Verbindlich festlegen und in der Spec dokumentieren, weil Regelvalidator und Creo-Modell exakt dieselbe Definition brauchen:

- Ursprung: Schnittpunkt der Vorderachsmitte mit der Bodenebene. **z = 0 ist der Boden** — das macht alle T 8.2-Höhenchecks trivial.
- x nach hinten, y nach rechts, z nach oben.
- Alle IBL-Koordinaten werden **bereits im Fahrzeugkoordinatensystem in mm** exportiert. Dann muss in Creo nichts mehr verschoben, gedreht oder skaliert werden.

---

## 7. Die Creo-Anbindung

### 7.1 Formatvergleich

| Weg | Datei | Was in Creo entsteht | Neu einlesbar | Bewertung |
|---|---|---|---|---|
| **Imported Datum Curve** | `.ibl` | Importierte Bezugskurve, an ein KS gebunden | ja, über *Edit Definition* | **Empfehlung.** Sauber, an ein KS gebunden, mehrere Sektionen pro Datei |
| Datum Points | `.pts` | Bezugspunkte (Offset Coordinate System) | ja | Nur wenn man Punkte für Messungen braucht; die Kurve muss man daraus erst bauen |
| Sketcher-Import | `.dxf`, `.dwg`, `.sec`, `.igs` | Echte Skizzenelemente mit Skalieren-/Drehen-/Verschieben-Griffen | nein, nicht assoziativ | Für einmalige Skizzen und für Fertigungsvorlagen |
| Flächen/Volumen | `.igs`, `.step` | Importierte Geometrie | nein | Für die CFD-Rückübergabe, nicht fürs Konstruieren |
| Gleichungskurve | — | `Curve from Equation` | voll parametrisch | Elegant für NACA-/CST-Studien direkt in Creo, aber auf analytische Profile begrenzt |

### 7.2 Das IBL-Format (verifiziert gegen die PTC-Dokumentation)

Creo liest `.ibl`-Dateien über **Model → Get Data → Import**, im Dialog **Import type = Curve**, anschließend im Reiter *Placement* das Zielkoordinatensystem wählen. Aus der PTC-Hilfe:

> Das „.ibl"-Format ähnelt dem Blend-Format; jedem Kurvensegment müssen `begin section` und `begin curve` vorangestellt werden. Zwei Punkte in einer Sektion ergeben eine Gerade, mehr als zwei einen Spline. Zum Verbinden von Segmenten muss der erste Punkt eines Segments mit dem letzten des vorherigen übereinstimmen.

Die Punktnummerierung in der ersten Spalte ist optional. Struktur exakt nach dem PTC-Beispiel:

```
open
arclength

begin section ! 1
        begin curve
    1   20   30   40
    2   40   50   70
    3   30   60   80

begin section ! 2
        begin curve
    1   30   60   80
    2   40   70   40
    3   50   40   60
```

Für ein Flügelelement mit 13 Spannweitenstationen und getrennter Ober-/Unterseite ergibt das **eine** Datei mit 26 Sektionen → **ein einziges Import-Feature in Creo**. Beim Ändern des Designs wird dieselbe Datei überschrieben und das Feature neu definiert; die gesamte nachgelagerte Featurekette (Boundary Blend, Verdicken, Verrundungen) regeneriert automatisch.

Ergänzend: Über **Datum Point → Offset Coordinate System** akzeptiert Creo `.pts` und `.ibl`. Das `.pts`-Format ist schlicht `X Y Z` leerzeichengetrennt; Kommentarzeilen beginnen mit `!`.

### 7.3 Empfohlener Workflow: Skelett + IBL + Projektion

```
  AeroSpec (YAML, im Git)
        │
        ▼   aerostudio export --creo
  ┌─────────────────────────────────────────────┐
  │  FW_E1.ibl   FW_E2.ibl   FW_E3.ibl          │
  │  RW_E1.ibl   ...   UT_TUNNEL.ibl            │
  │  aero_params.txt   (chord, aoa, gap, ...)   │
  └─────────────────────────────────────────────┘
        │
        ▼   Import auf CS_AERO
  AERO_SKELETON.PRT ──── Publish Geometry ────┐
   • Fahrzeug-KS CS_AERO                      │
   • Regelebenen als Bezugsebenen (T 8.2)     │
   • Radpositionen, Bodenebene                │
   • alle importierten Profilkurven           │
                                              ▼
                        ┌──────────────┬──────────────┬──────────────┐
                        │ FW_EL1.PRT   │ FW_EL2.PRT   │ FW_ENDPL.PRT │  ← Copy Geometry
                        └──────────────┴──────────────┴──────────────┘
                                              │
                                              ▼
                                    AERO_FRONT.ASM → AERO.ASM → RSP26.ASM
```

**Schritt für Schritt:**

1. **Skelettmodell anlegen** (`AERO_SKELETON.PRT`). Es enthält das Fahrzeugkoordinatensystem `CS_AERO`, die Bodenebene, die Radpositionen und — das ist der eigentliche Trick — **die T 8.2-Grenzen als echte Bezugsebenen und -flächen**. Damit ist das Reglement im CAD sichtbar und nicht nur im Kopf des Aero-Verantwortlichen.
2. **Tool exportiert die IBL-Dateien** in einen festen Pfad, Koordinaten bereits im Fahrzeug-KS in mm.
3. **Import in Creo** auf `CS_AERO`. Die Kurven sitzen ohne weiteres Zutun exakt richtig.
4. **Geometrie aufbauen:**
   - Konstantes Profil, einfacher Flügel → **Skizze anlegen, `Referenzen projizieren` auf die importierte Kurve, extrudieren.** Damit ist die ursprüngliche Anforderung „als Skizze einfügen und extrudieren" exakt erfüllt — die Skizze enthält aber keine 200 abgetippten Punkte, sondern eine Projektion, die bei jedem Neuimport mitwandert.
   - Verwundener oder verjüngter Flügel → **Boundary Blend** über die Sektionskurven, dann `Verdicken` bzw. `Volumenkörper`.
5. **Publish Geometry** im Skelett, **Copy Geometry** in die Einzelteile. Jedes Flügelelement, jede Endplatte ist ein eigenes Bauteil, das ausschließlich vom Skelett abhängt. Top-Down, eine Quelle.
6. **Änderungslauf:** Tool schreibt IBL neu → in Creo einmal *Edit Definition* am Import-Feature (oder automatisiert, siehe 7.4) → alles Nachgelagerte regeneriert.

### 7.4 Automatisierung mit CREOSON

**CREOSON** ist eine Open-Source-Initiative von Simplified Logic zur Automatisierung von Creo Parametric über JSON-Transaktionen (intern über JLink); **creopyson** ist der Python-Client dazu (auf PyPI, Quelle auf GitHub unter `SimplifiedLogic/creoson`). Über 150 Funktionen in mehr als 15 Befehlsgruppen.

Damit wird aus dem Handimport eine Pipeline:

```python
import creopyson
c = creopyson.Client(); c.connect()
c.file_open("aero_skeleton.prt")
c.parameter_set("AERO_SPEC_HASH", spec_hash)
for name, val in layout_params.items():
    c.parameter_set(name, val)          # chord, aoa, gap, overlap ...
c.file_regenerate()
c.interface_export_file("STEP", filename="aero_for_cfd.stp")
```

Damit ist der Kreis geschlossen: **AeroSpec ändern → Creo regeneriert → STEP für CFD raus → Ergebnis zurück in die Zielfunktion.** Das ist genau der Durchsatzsprung, den Monash über eine automatisierte Workbench-Pipeline erreicht hat.

**Fallback ohne CREOSON** (falls die Creo-Lizenz kein JLink/Object TOOLKIT erlaubt): Das Tool generiert Mapkeys bzw. eine Trail-Datei für den Importschritt. Weniger elegant, reduziert den manuellen Aufwand aber auf zwei Klicks pro Element.

### 7.5 Fallstricke, die vorab geklärt gehören

| Fallstrick | Gegenmaßnahme |
|---|---|
| Zu viele Punkte pro Kurve → wellige Splines, lahme Regeneration | 60–120 Punkte, cosinusverteilt; separater High-Res-Export nur für CFD |
| Durchgehender Spline über die Nase → Beule | Ober- und Unterseite als getrennte Sektionen, Knick an LE und TE |
| Einheiten | Tool rechnet in m, **exportiert immer in mm**; Creo-Template auf mmNs |
| Segmente hängen nicht zusammen | Erster Punkt eines Segments = letzter Punkt des vorherigen (PTC-Vorgabe) |
| DXF-Sketcher-Import ist nicht assoziativ | Nur für Fertigungsvorlagen (Rippen, Schablonen, Wasserstrahl), nie fürs Konstruktionsmodell |
| Boundary Blend verdreht die Fläche | Alle Sektionen mit identischem Startpunkt und gleicher Umlaufrichtung exportieren |
| Hinterkante läuft spitz zu | TE-Dicke ≥ 2 mm erzwingen (T 2.4.1), Hinterkante als eigenes kurzes Segment |
| Kein Nachvollziehen, welches CAD zu welchem CFD gehört | `AERO_SPEC_HASH` als Creo-Parameter plus Git-Tag |

---

## 8. Regelvalidator

Der Validator läuft bei jeder Änderung und liefert eine Ampel in der UI. Er prüft **nicht die statische Lage, sondern den vollen Fahrzustands-Envelope** (T 8.2: „mit jedem Federungssetup, mit oder ohne Fahrer"), gespeist aus den vorhandenen RSP-Kinematikdaten.

| Check | Regel | Datenbedarf |
|---|---|---|
| Höhe < 500 mm vor Kopfstützenebene | T 8.2.1 | Kopfstützenposition, hinterste Einstellung |
| Höhe < 250 mm vor VA und außerhalb innerster Radpunkt | T 8.2.1 | Radgeometrie, Spurweite |
| Höhe < 1100 mm hinter Kopfstützenebene | T 8.2.1 | — |
| Breite unter 500 mm und hinter VA | T 8.2.1 | äußerste Punkte Vorder- und Hinterrad |
| Breite über 500 mm | T 8.2.1 | innerster Punkt Hinterrad |
| Länge ≤ 250 mm hinter HR, ≤ 700 mm vor VR | T 8.2.4 | Radstand, Reifendurchmesser |
| Bodenfreiheit ≥ 30 mm statisch | T 2.2.1 | Fahrzeugmasse, Federraten |
| Keine Bodenberührung in keinem Zustand | T 2.2.2 | Hub-/Nick-/Wank-Envelope |
| Keep-out-Zone offene Räder | T 2.1.3 | Reifenkontur, Lenkwinkel |
| Kantenradien 3 mm / 1 mm | T 2.4.1 | Profilgeometrie |
| Keine externen konkaven Radien außerhalb T 8.2 | T 2.3.2 | Bodyworkkontur |
| Anbindung hinter AIP | T 3.20.2 | AIP-Position |
| Nachweis 120 kN Frontflügelanbindung | T 3.19.4 | Schraubenbild, Strebenknicklast |
| Steifigkeit 200 N / 225 cm² ≤ 10 mm; 50 N ≤ 25 mm | T 8.3 | FEM oder Handrechnung |

Ausgabe: Report in Markdown/PDF mit Regelnummer, Sollwert, Istwert und kritischstem Fahrzustand. Direkt verwendbar für Scrutineering und Design Report.

---

## 9. Roadmap

| Meilenstein | Inhalt | Aufwand | Ergebnis |
|---|---|---|---|
| **M1** | Profilkern (dat/CST/NACA), Repanelisierung, IBL-Export, Handimport in Creo verifiziert | 2–3 Wochen | Ein Profil aus dem Tool sitzt maßhaltig als Kurve in Creo und lässt sich extrudieren |
| **M2** | Mehrelement-Layout (Gap/Overlap), NeuralFoil-Screening, Regelvalidator, Dash-UI | 3–4 Wochen | Kaskaden lassen sich interaktiv auslegen und werden live gegen T 8 geprüft |
| **M3** | Spannweitenverteilungen, Sektionsstapel, Creo-Skelett-Template mit Boundary Blend, Endplates | 3–4 Wochen | Kompletter 3D-Frontflügel aus dem Spec heraus |
| **M4** | CREOSON-Bridge, STEP-Export, CFD-Übergabe, Reportgenerator | 2–3 Wochen | Ein Kommando: Spec → Creo → STEP → CFD-Queue |
| **M5** | Undertray und Diffusor, DoE mit Optuna, Kopplung an Rundenzeit-Sensitivitäten, DRS-Zustände | 4+ Wochen | Optimierungsläufe statt Handiterationen |

Kritischer Pfad ist **M1**: Solange nicht bewiesen ist, dass eine Toolkurve exakt und wiederholbar in Creo landet, ist alles darüber Spekulation. Deshalb M1 zuerst — und gegen ein echtes, gemessenes Bauteil verifizieren.

---

## 10. Offene Punkte

1. **FS Rules 2027** — noch nicht veröffentlicht. Nach Erscheinen: Diff gegen 2026, neue Regel-YAML, Regressionslauf über alle Designs.
2. **Creo-Version und Lizenzumfang** — CREOSON setzt eine Creo-Installation mit JLink/Object TOOLKIT voraus. Muss vor M4 geklärt sein.
3. **CFD-Ressourcen** — die 2D-Kaskadenoptimierung braucht eine Rechenumgebung. Ohne die bleibt das Tool bei NeuralFoil-Genauigkeit stehen, was für die Profilvorauswahl reicht, für Gap/Overlap aber nicht.
4. **Fertigungsverfahren** — Nasspresse, Prepreg im Autoklaven oder gedruckter Kern? Davon hängen die Mindestdicken und Radien in Kapitel 4.2 ab.
5. **Referenzgeometrie-Schnittstelle** — Wer liefert Radpositionen, Kopfstützenposition und Federungs-Envelope in welchem Format? Vorschlag: eine `vehicle_ref.yaml`, gepflegt vom Package-Verantwortlichen, versioniert im selben Repo.

---

## Quellen

**Reglement**
- [FS Rules 2026 v1.1 (PDF)](https://www.formulastudent.de/fileadmin/user_upload/all/2026/rules/FS-Rules_2026_v1.1.pdf) — T 2.1.3, T 2.2, T 2.3.2, T 2.4.1, T 3.19.4, T 3.20.2, T 8, IN 1.5.1
- [FSG Rules & Documents](https://www.formulastudent.de/fsg/rules/) — Stand der veröffentlichten Dokumente
- [FSG News](https://www.formulastudent.de/pr/news) — kein 2027-Dokument gelistet
- [FSG: FS Rules 2026 v1.1 published](https://www.formulastudent.de/pr/news/details/article/fs-rules-2026-v11-published) — FSG Academy am 25.10.2025

**Teams und Verfahren**
- [Optimising FSAE Aerodynamics at Monash Motorsport (LEAP Australia)](https://www.leapaust.com.au/blog/cfd/monash-motorsport-fsae-aerodynamics-guest-post/)
- [Development of the Aerodynamic Design Tools & Processes for Formula-SAE, R. Ockerby, Monash 2015 (PDF)](https://www.monashmotorsport.com/s/MMS-Final-Year-Thesis-DEVELOPMENT-OF-THE-AERODYNAMIC-DESIGN-TOOLS-PROCESSES-FOR-FORMULA-SAE-Ryan-Ock.pdf)
- [Aerodynamics Focus: The Undertray — Monash Motorsport](https://www.monashmotorsport.com/blog/aerodynamics-focus-the-undertray)
- [Aerodynamic Development of Formula Student Race Car, H. Dahlberg (PDF)](https://www.diva-portal.org/smash/get/diva2:737287/fulltext01.pdf)
- [Formula Student Aerodynamics – Growing Wings with CFD (SimScale / eMotorsports Cologne)](https://www.simscale.com/blog/formula-student-aerodynamics/)
- [Team DUT's aerodynamic challenge (Delta, TU Delft)](https://delta.tudelft.nl/en/article/team-duts-aerodynamic-challenge)
- [Rules of thumb in Wing design — FSAE.com Forums](https://www.fsae.com/forums/archive/index.php/t-2541.html)
- [Design Optimization of Multi-Element High-Lift Configurations (Stanford, PDF)](http://aero-comlab.stanford.edu/sanghok/jair2002.pdf)
- [Ground Effect on Wings for Formula Student Race Cars](https://www.researchgate.net/publication/322393663_Ground_Effect_on_Wings_for_Formula_Student_Race_Cars)

**Creo**
- [About Imported Datum Curves (PTC Help, Creo 11)](https://support.ptc.com/help/creo/creo_pma/r11.0/usascii/part_modeling/part_modeling/About_Imported_Datum_Curves.html)
- [Example: Importing a Datum Curve (PTC Help, Creo 11)](https://support.ptc.com/help/creo/creo_pma/r11.0/usascii/part_modeling/part_modeling/Example_Importing_a_Datum_Curve.html)
- [How to import an *.ibl file to create a curve in Creo Parametric (CS107337)](https://www.ptc.com/en/support/article/CS107337)
- [How to insert Section files (*.dxf, *.igs, *.sec, *.dwg, *.ai) into Sketcher (CS72629)](https://www.ptc.com/en/support/article/CS72629)
- [To Import a Data File — Datum Points (PTC Help)](https://support.ptc.com/help/creo/creo_pma/r11.0/usascii/part_modeling/part_modeling/To_Import_a_Data_File.html)
- [CREOSON auf GitHub](https://github.com/SimplifiedLogic/creoson) · [creoson.com](https://creoson.com/) · [creopyson auf PyPI](https://pypi.org/project/creopyson/)

**Werkzeuge**
- [NeuralFoil](https://github.com/peterdsharpe/NeuralFoil) · [NeuralFoil Whitepaper (arXiv)](https://arxiv.org/pdf/2503.16323)
- [AeroSandbox Dokumentation](https://aerosandbox.readthedocs.io/en/master/autoapi/aerosandbox/geometry/airfoil/index.html)
- [UIUC Airfoil Coordinates Database](https://m-selig.ae.illinois.edu/ads/coord_database.html)
