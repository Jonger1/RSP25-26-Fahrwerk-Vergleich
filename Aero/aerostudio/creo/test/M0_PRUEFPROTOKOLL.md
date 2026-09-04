# M0 — Prüfprotokoll

**Ziel:** Beweisen, dass eine Kurve aus dem Tool maßhaltig und wiederholbar in Creo 8 landet. Solange das nicht bewiesen ist, ist alles ab M1 Spekulation.

Dauer etwa 45 Minuten. Ergebnisse wandern nach [`../profiles/creo8.yaml`](../profiles/creo8.yaml).

**Dateien** liegen in diesem Ordner:
`...\0_Fahrwerk_Claude\Aero\aerostudio\creo\test\`
- `M0_pruefkurve.ibl` — die Prüfkurve
- `M0_pruefkurve_kommentiert.ibl` — gleiche Geometrie mit Kommentarzeilen

---

## Was die Prüfkurve enthält

Bewusst so gebaut, dass jeder mögliche Fehler ohne Messen auffällt:

| Element | Geometrie | Prüft |
|---|---|---|
| Großes Rechteck bei y = 0 | 200 mm (x) × 50 mm (z), Ecke im Ursprung | Einheiten, Lage zum Ursprung, Richtung von +x und +z |
| Spline darüber | 5 Punkte, Scheitel bei x = 100 / z = 80 | dass > 2 Punkte einen Spline ergeben und dieser durch die Stützpunkte läuft |
| Kleines Rechteck bei y = 300 | 100 mm × 25 mm | Spannweitenrichtung, mehrere Sektionen in einer Datei |
| Richtungsmarke | 150 mm entlang +y ab Ursprung | in welche Creo-Richtung unser +y zeigt |

Zehn Sektionen in einer Datei — genau die Struktur, die später ein Flügelelement mit mehreren Spannweitenstationen hat.

**Fehlersignaturen:** Zoll- statt Millimetervorlage → alles 25,4-fach zu groß. x und z vertauscht → das Rechteck ist 50 lang und 200 hoch.

---

## Schritt 1 — Umgebung erfassen

1. Creo 8 starten, **Hilfe → Über Creo Parametric**. **Datecode notieren.**
2. **Installationspfad notieren**, typischerweise `C:\Program Files\PTC\Creo 8.0.x.x`.
3. Prüfen, ob diese **Datei** existiert:
   ```
   <Installationspfad>\Common Files\text\java\otk.jar
   ```
   Bei Creo 8 liegt `Common Files` **direkt** im Installationsordner, nicht unter dem Datecode.

   - **Ja** → J-Link nutzbar, M5 und M7 später ohne Nachinstallation möglich.
   - **Nein** → für heute irrelevant. Für M5 die Komponente „API Toolkits" über denselben Installer nachinstallieren, kostenlos.

   > Der Ordnername allein sagt nichts. Ein vorhandener `otk_java_examples`-Ordner bedeutet **nicht**, dass die Bibliotheken da sind — es gibt Installationen, in denen die Ordnerstruktur steht, aber die JAR fehlt. Entscheidend ist `otk.jar`.

---

## Schritt 2 — Testteil und CS_AERO anlegen

1. **Datei → Neu → Teil → Volumenkörper**, Name `M0_TEST`.
2. Haken bei „Standardschablone verwenden" **entfernen**, Vorlage **`mmns_part_solid_abs`** wählen.

   Ab Creo 7 ist `mmns_part_solid` in zwei Varianten aufgeteilt: `_abs` (absolute Genauigkeit) und `_rel` (relative Genauigkeit). **Wir nehmen `_abs`**, und das ist keine Geschmacksfrage: Bei relativer Genauigkeit skaliert die Toleranz mit der Modellgröße. Ein Flügel ist rund 1400 mm breit, hat aber eine 2 mm dicke Hinterkante und 3 mm Nasenradien. Relative Genauigkeit rechnet an genau diesen Stellen zu grob und lässt später Verrundungen und Boundary Blends scheitern — ein Fehlerbild, das erst in M4 auftaucht und dann schwer zuzuordnen ist.

   Steht in der Liste nichts mit `mmns`, ist die Vorlagensammlung angepasst. Dann eine beliebige metrische Vorlage nehmen und mit Punkt 3 die Einheiten von Hand richtigstellen.

3. Prüfen: **Datei → Vorbereiten → Modelleigenschaften → Einheiten** zeigt `millimeter Newton Second (mmNs)`. Falls nicht: **ändern**, und im Dialog **„Maße interpretieren"** wählen (bei einem leeren Teil ohne Geometrie ist die Wahl folgenlos, aber sie wird zur Gewohnheit).

   Im selben Dialog unter **Genauigkeit** prüfen, dass **absolut** eingestellt ist, Wert 0,01 mm. Fehlt die Umschaltmöglichkeit, muss in der `config.pro` die Option `enable_absolute_accuracy` auf `yes` stehen.
4. **Modell → Koordinatensystem**
5. Als Referenz das vorhandene Standard-Koordinatensystem wählen.
6. Reiter **Ausrichtung** → **Um Achsen drehen** → **X: −90**
7. Reiter **Eigenschaften** → Name **`CS_AERO`** → bestätigen.

### Warum die Drehung

Beim ersten Durchlauf am 05.09.2026 zeigte sich: Die deutsche Standardvorlage hat **Y als Hochachse** (Ebenen `XY_T_VORNE`, `XZ_T_OBEN`, `YZ_T_RECHTS`). Normales Creo-Verhalten, kein Fehler.

Das Tool rechnet mit **Z als Hochachse**, weil das Reglement durchgehend über Höhen über Grund argumentiert — T 8.2 sagt „lower than 500 mm from the ground". Mit `z = 0` auf der Bodenebene wird jede Höhenprüfung ein Vergleich statt einer Koordinatentransformation. Diese Konvention bleibt.

Der Unterschied wird **an genau einer Stelle** aufgelöst: bei CS_AERO. Nicht im Exporter — sonst steckt die Konvention an zwei Orten und driftet auseinander, sobald jemand eine davon anfasst.

Nach der Drehung gilt: unser z = Y der Vorlage (senkrecht), unser x = X der Vorlage, unser y = −Z der Vorlage. Rechtshändig.

> **Offen bis M4:** wie CS_AERO im echten Fahrzeugmodell liegt, also welche Richtung im Auto „hinten" ist. Für M0 und M1 genügt, dass z senkrecht steht.

---

## Schritt 3 — Import

1. **Modell → Daten abrufen → Importieren**
2. Zur `M0_pruefkurve.ibl` navigieren. Wird sie nicht angezeigt: Dateityp-Filter auf **Alle Dateien**.
3. Unter **Importtyp** → **Kurve** wählen, bestätigen.
4. Reiter **Platzierung** → Sammler für das Koordinatensystem anklicken → **`CS_AERO`** wählen.

   Das ist der entscheidende Klick. Ohne ihn landet alles auf dem Standard-KS und liegt gekippt.
5. Bestätigen.

Bei Fehlern: Meldung **wörtlich** notieren.

---

## Schritt 4 — Sichtprüfung

| # | Beobachtung | Soll |
|---|---|---|
| 1 | Großes Rechteck | steht senkrecht, in der Seitenansicht sichtbar |
| 2 | Spline | wölbt sich nach oben, Scheitel 30 mm über der Oberkante |
| 3 | Richtungsmarke | zeigt waagerecht zur Seite |
| 4 | Kleines Rechteck | 300 mm seitlich versetzt, nicht darüber |
| 5 | Spline glatt, ohne Beulen oder Schlingen? | ja |
| 6 | Vier Rechteckkanten sichtbar zusammenhängend? | ja |

Zum Vergleich: Bei einem Import auf das **Standard-KS** liegt das Rechteck flach, der Spline hängt in die Tiefe, die Marke zeigt nach oben und das kleine Rechteck schwebt 300 mm darüber. Wer beide Zustände einmal gesehen hat, hat die Konvention bewiesen statt behauptet.

---

## Schritt 5 — Messen

**Analyse → Messen.** Toleranz ±0,01 mm.

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

**Nummer 4 ist die wichtigste Zahl des ganzen Tages.** Läuft der Spline exakt durch seinen Stützpunkt bei 80,000 mm, reichen später wenige Punkte pro Profilkurve. Weicht er ab, brauchen wir dichtere Punktverteilungen — das entscheidet den Zuschnitt von M1.

---

## Schritt 6 — Kommentarzeilen testen

Ein zweites Mal importieren, diesmal `M0_pruefkurve_kommentiert.ibl`. Gleiche Geometrie, aber mit `!`-Kommentarzeilen im Kopf und zwischen den Sektionen.

- **Funktioniert** → wir können den Spec-Hash direkt in jede IBL schreiben. Jede Kurve in Creo wäre bis auf den Git-Stand rückverfolgbar, ohne Umweg über Modellparameter.
- **Scheitert** → auch ein Ergebnis. Dann bleiben IBL-Dateien kommentarfrei und die Herkunft steht nur im Creo-Parameter `AERO_SPEC_HASH`.

---

## Schritt 7 — Mapkey aufzeichnen

Der Baustein, aus dem in M5 die Automatisierung wird.

1. **Werkzeuge → Mapkeys** (falls dort nicht zu finden: Datei → Optionen → Umgebung).
2. **Neu**, Kürzel z. B. `aeroimp`, Name „Aero Studio: IBL importieren".
3. **Aufzeichnen** starten, Schritt 3 komplett durchführen, **Stopp**.
4. Speichern, dann auf einem **frischen Teil abspielen** und prüfen, ob die Kurven wieder korrekt sitzen.
5. Mapkey-Text aus der `config.pro` herauskopieren.

**Erwartete Schwierigkeit:** Der Dateiname steckt in der aufgezeichneten Klickfolge mit drin. Für M5 brauchen wir entweder einen festen Dateinamen, den das Tool immer überschreibt, oder eine Mapkey-Variante, die den Dialog offen lässt. Was in Creo 8 davon geht, findet sich hier heraus. **Klappt es nicht auf Anhieb, ist das kein Rückschlag** — es ist die Information, auf der M5 aufbaut.

---

## Was am Ende zurückkommt

1. Datecode und Installationspfad (Schritt 1)
2. `otk_java_free` vorhanden? (Schritt 1)
3. Die sechs Sichtprüfungen (Schritt 4)
4. Die acht Messwerte (Schritt 5)
5. Kommentierte Datei importierbar? (Schritt 6)
6. Mapkey-Text und ob das Abspielen funktioniert (Schritt 7)
7. Alles, was unerwartet war — Fehlermeldungen bitte wörtlich

---

## Abnahme M0

- [ ] Alle acht Messungen innerhalb ±0,01 mm
- [ ] Spline glatt und durch seine Stützpunkte
- [ ] Achszuordnung durch CS_AERO bestätigt
- [ ] Verhalten bei Kommentarzeilen geklärt
- [ ] Mapkey wiederholt den Import ohne Handeingriff
- [ ] `creo8.yaml` enthält keine `AUSFUELLEN`-Einträge mehr

Was nicht klappt, wird nicht weggelassen, sondern notiert — davon hängt der Zuschnitt von M1 und M5 ab.
