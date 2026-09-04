# M0 — Prüfprotokoll

**Ziel:** Beweisen, dass eine Kurve aus dem Tool maßhaltig und wiederholbar in Creo 8 landet. Solange das nicht bewiesen ist, ist alles ab M1 Spekulation.

Dauer: etwa 45 Minuten. Ergebnisse in [`../profiles/creo8.yaml`](../profiles/creo8.yaml) eintragen.

---

## Was die Prüfkurve enthält

`M0_pruefkurve.ibl` — bewusst so gebaut, dass jeder mögliche Fehler sofort sichtbar wird:

| Element | Geometrie | Prüft |
|---|---|---|
| Großes Rechteck bei y = 0 | 200 mm (x) × 50 mm (z), Ecke im Ursprung | Einheiten, Lage zum Ursprung, Richtung von +x und +z |
| Spline darüber | 5 Punkte, Scheitel bei x = 100 / z = 80 | dass > 2 Punkte einen Spline ergeben und dieser durch die Punkte läuft |
| Kleines Rechteck bei y = 300 | 100 mm × 25 mm | Spannweitenrichtung, mehrere Sektionen in einer Datei |
| Richtungsmarke | 150 mm entlang +y ab Ursprung | in welche Creo-Richtung unser +y zeigt |

Zehn Sektionen in einer Datei — genau die Struktur, die später ein Flügelelement mit mehreren Spannweitenstationen hat.

**Fehlersignaturen:** Ist die Vorlage auf Zoll statt Millimeter, erscheint das Rechteck 25,4-fach zu groß. Sind x und z vertauscht, ist es 50 lang und 200 hoch. Beides sieht man ohne Messen.

---

## Schritt 1 — Umgebung erfassen

1. Creo 8 starten, **Hilfe → Über Creo Parametric**. Datecode notieren.
2. Installationspfad notieren (Loadpoint), typischerweise `C:\Program Files\PTC\Creo 8.0.x.x`.
3. Im Loadpoint nachsehen, ob es den Ordner `<datecode>\Common Files\otk\otk_java_free` gibt.
   - **Ja** → die Komponente „API Toolkits" ist installiert, M5 und M7 sind später ohne Nachinstallation möglich.
   - **Nein** → kein Problem für heute. Für M5 später über denselben Installer nachinstallieren, kostenlos.

→ Eintragen unter `creo:` und `api_toolkits:` in `creo8.yaml`.

---

## Schritt 2 — Testteil anlegen

1. **Datei → Neu → Teil → Volumenkörper**, Name `M0_TEST`.
2. Haken bei „Standardschablone verwenden" **entfernen**, Vorlage **`mmns_part_solid`** wählen (Millimeter/Newton/Sekunde). Falls mehrere mmns-Varianten angeboten werden, ist die Wahl für M0 egal — Hauptsache Millimeter.
3. Prüfen: **Datei → Vorbereiten → Modelleigenschaften → Einheiten** muss `millimeter Newton Second` zeigen.
4. Koordinatensystem `CS_AERO` anlegen — **mit Drehung**, siehe unten.

### Warum CS_AERO gedreht wird

Beim ersten Durchlauf am 05.09.2026 kam heraus: Die deutsche Standardvorlage hat **Y als Hochachse** (Ebenen `XY_T_VORNE`, `XZ_T_OBEN`, `YZ_T_RECHTS`; Standard-KS mit X seitlich, Y nach oben, Z in die Tiefe). Das ist normales Creo-Verhalten, kein Fehler.

Das Tool rechnet dagegen mit **Z als Hochachse**, weil das Reglement durchgehend über Höhen über Grund argumentiert — T 8.2 sagt „lower than 500 mm from the ground". Mit `z = 0` auf der Bodenebene wird jede Höhenprüfung zu einem Vergleich statt zu einer Koordinatentransformation. Diese Konvention bleibt.

Aufgelöst wird der Unterschied **an genau einer Stelle**: bei CS_AERO. Nicht im Exporter — sonst steckt die Konvention an zwei Orten und driftet irgendwann auseinander.

### CS_AERO anlegen

1. **Modell → Koordinatensystem**.
2. Als Referenz das vorhandene Standard-Koordinatensystem wählen.
3. Reiter **Ausrichtung** → **Um Achsen drehen** → **X: −90**.
4. Reiter **Eigenschaften** → Name **`CS_AERO`**.

Danach gilt: unser z = Y der Vorlage (senkrecht), unser x = X der Vorlage, unser y = −Z der Vorlage. Rechtshändig, wie es sein muss.

> **Noch offen bis M4:** wie CS_AERO im echten Fahrzeugmodell liegt, also welche Richtung im Auto „hinten" ist. Für M0 und M1 genügt, dass z senkrecht steht. Die Bindung ans Fahrzeug gehört dorthin, wo das Skelett eingehängt wird — heute würden wir sie raten.

---

## Schritt 3 — Import

1. **Modell → Daten abrufen → Importieren**.
2. Im Dateidialog zur `M0_pruefkurve.ibl` navigieren. Wird sie nicht angezeigt, den Dateityp-Filter auf **Alle Dateien** stellen.
3. Im folgenden Dialog unter **Importtyp** → **Kurve** wählen, bestätigen.
4. Im Reiter **Platzierung** den Sammler für das Koordinatensystem anklicken und **`CS_AERO`** wählen.
5. Bestätigen. Die Kurven erscheinen.

**Wenn hier etwas schiefgeht:** Fehlermeldung wörtlich notieren und mir schicken. Das Format ist gegen die PTC-Dokumentation verifiziert, aber genau dafür machen wir M0.

---

## Schritt 4 — Nachmessen

Mit **Analyse → Messen**. Sollwerte auf drei Nachkommastellen, Toleranz ±0,01 mm.

| # | Messung | Soll | Ist | ok? |
|---|---|---|---|---|
| 1 | Unterkante großes Rechteck, Länge | 200,000 mm | | |
| 2 | Vorderkante großes Rechteck, Länge | 50,000 mm | | |
| 3 | Abstand Rechteckecke zum Ursprung von `CS_AERO` | 0,000 mm | | |
| 4 | Höchster Punkt des Splines über der Rechteckunterkante | 80,000 mm | | |
| 5 | Position dieses Scheitelpunkts in Längsrichtung | 100,000 mm | | |
| 6 | Richtungsmarke, Länge | 150,000 mm | | |
| 7 | Abstand der beiden Rechtecke quer | 300,000 mm | | |
| 8 | Kleines Rechteck, Länge × Höhe | 100,000 × 25,000 mm | | |

Zusätzlich per Augenschein:

| # | Beobachtung | Soll nach der CS_AERO-Drehung | Ist |
|---|---|---|---|
| 9 | Liegt das große Rechteck senkrecht (in der Seitenansicht)? | ja | |
| 10 | Wölbt sich der Spline nach oben über das Rechteck? | ja, Scheitel 30 mm darüber | |
| 11 | Zeigt die Richtungsmarke waagerecht zur Seite? | ja | |
| 12 | Steht das kleine Rechteck seitlich versetzt, nicht darüber? | ja, 300 mm seitlich | |
| 13 | Ist der Spline glatt, ohne Beulen oder Schlingen? | ja | |
| 14 | Hängen die vier Rechteckkanten sichtbar zusammen? | ja | |

Die Punkte 9 bis 12 sind der eigentliche Test der Achszuordnung: **Vor** der Drehung liegt das Rechteck flach, der Spline hängt in die Tiefe, die Marke zeigt nach oben und das kleine Rechteck schwebt 300 mm darüber. **Nach** der Drehung ist es genau umgekehrt. Wenn du beide Zustände einmal gesehen hast, ist die Konvention bewiesen.

---

## Schritt 5 — Kommentarzeilen testen

Ein zweites Mal importieren, diesmal `M0_pruefkurve_kommentiert.ibl`. Gleiche Geometrie, aber mit `!`-Kommentarzeilen im Kopf und zwischen den Sektionen.

- **Import funktioniert** → wir können künftig den Spec-Hash und das Erstellungsdatum direkt in jede IBL schreiben. Jede Kurve in Creo wäre dann bis auf den Git-Stand rückverfolgbar. Das wäre ein echter Gewinn.
- **Import scheitert** → auch gut zu wissen. Dann bleiben IBL-Dateien kommentarfrei und die Herkunft steht nur im Creo-Parameter `AERO_SPEC_HASH`.

→ Ergebnis unter `befunde: ibl_kommentarzeilen_erlaubt` eintragen.

---

## Schritt 6 — Mapkey aufzeichnen

Das ist der Baustein, aus dem in M5 die Automatisierung wird.

1. **Werkzeuge → Mapkeys** (falls dort nicht zu finden: Datei → Optionen → Umgebung).
2. **Neu**, Kürzel z. B. `aeroimp`, Name „Aero Studio: IBL importieren".
3. **Aufzeichnen** starten, die Schritte aus Schritt 3 komplett durchführen, **Stopp**.
4. Speichern, dann den Mapkey **auf einem frischen Teil abspielen** und prüfen, ob die Kurven wieder korrekt sitzen.
5. Den Mapkey-Text aus der `config.pro` herauskopieren.

→ Unter `mapkeys: import_curve` in `creo8.yaml` eintragen.

**Erwartete Schwierigkeit:** Mapkeys zeichnen Klickfolgen auf, und der Dateiname steckt mit drin. Für M5 brauchen wir entweder einen festen Dateinamen, den das Tool immer überschreibt, oder eine Mapkey-Variante, die den Dialog offen lässt. Was davon in Creo 8 funktioniert, finden wir hier heraus — wenn es heute nicht auf Anhieb klappt, ist das kein Rückschlag, sondern genau die Information, die M5 braucht.

---

## Abnahme M0

M0 ist erledigt, wenn:

- [ ] Alle acht Messungen liegen innerhalb ±0,01 mm.
- [ ] Der Spline ist glatt und läuft durch seine Stützpunkte.
- [ ] Die Achszuordnung ist notiert.
- [ ] Das Verhalten bei Kommentarzeilen ist geklärt.
- [ ] Der Mapkey wiederholt den Import ohne Handeingriff.
- [ ] `creo8.yaml` enthält keine `AUSFUELLEN`-Einträge mehr.

Was nicht klappt, wird nicht weggelassen, sondern notiert — davon hängt der Zuschnitt von M1 und M5 ab.
