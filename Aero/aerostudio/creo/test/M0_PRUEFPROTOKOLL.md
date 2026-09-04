# M0 — Prüfprotokoll

**Ziel:** Beweisen, dass eine Kurve aus dem Tool maßhaltig und wiederholbar in Creo 8 landet. Solange das nicht bewiesen ist, ist alles ab M1 Spekulation.

Rechner geprüft am 05.09.2026: Creo 8.0.3.0, alles Nötige vorhanden, **nichts zu installieren**. Es fehlen nur noch die Schritte, die in Creo selbst passieren müssen — Dauer etwa 30 Minuten.

**Dateien** in diesem Ordner:
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

**Fehlersignatur Einheiten:** Wäre die Vorlage zollbasiert, erschiene das Rechteck 25,4-fach zu groß.

---

## Schritt 1 — Umgebung *(auf diesem Rechner erledigt)*

```
powershell -ExecutionPolicy Bypass -File ..\..\setup\Pruefe-Umgebung.ps1
```

Ergebnis vom 05.09.2026:

| | |
|---|---|
| Creo | 8.0.3.0, `C:\Program Files\PTC\Creo 8.0.3.0` |
| `otk.jar` | vorhanden → J-Link installiert, M5 und M7 später ohne Nachinstallation |
| Teilevorlage | `sut_de_startt.prt` (gtstarter / stools-se) |
| Genauigkeit | absolut, 0,01 mm — bereits korrekt in der `config.pro` |
| Python | 3.10.11 |
| Java | 25 — Creo 8 erwartet für J-Link Java 11, zu klären in M5 |

Auf einem anderen Rechner das Skript erneut laufen lassen, bevor es weitergeht.

---

## Schritt 2 — Testteil und CS_AERO anlegen

1. **Datei → Neu → Teil → Volumenkörper**, Name `M0_TEST`.
2. **Standardschablone verwenden lassen** — also den Haken **drin** lassen.

   > Wir nehmen bewusst die **Teamvorlage** `sut_de_startt.prt`, nicht PTCs `mmns_part_solid_abs`. Die Aeroteile müssen später in derselben Baugruppe leben wie der Rest des Fahrzeugs: gleiche Ebenenbenennung, gleicher Zeichnungsstandard, gleiche Parameter. Eine zweite Vorlagenfamilie erzeugt genau die Inkonsistenz, die man beim Zusammenbau teuer bezahlt. Die absolute Genauigkeit von 0,01 mm, die wir brauchen, steht in eurer `config.pro` ohnehin schon.

3. **Datei → Vorbereiten → Modelleigenschaften → Einheiten** kontrollieren. Es muss ein **Millimeter**-System sein (`mmNs` oder `mmKs` — für die Geometrie ist beides gleich, entscheidend ist die Längeneinheit).

   Das ist die einzige Annahme, die von außen nicht prüfbar war. Steht dort Zoll: melden, nicht selbst umstellen.

4. **Modell → Koordinatensystem**
5. Als Referenz das vorhandene **Standard-Koordinatensystem** wählen.
6. Reiter **Ausrichtung** → **Um Achsen drehen** → **X: −90**
7. Reiter **Eigenschaften** → Name **`CS_AERO`** → bestätigen.

### Warum die Drehung

Die Teamvorlage hat **Y als Hochachse** (Ebenen `XY_T_VORNE`, `XZ_T_OBEN`, `YZ_T_RECHTS`). Normales Creo-Verhalten, kein Fehler.

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

   **Das ist der entscheidende Klick.** Ohne ihn landet alles auf dem Standard-KS und liegt gekippt.
5. Bestätigen.

Bei Fehlern: Meldung **wörtlich** notieren.

---

## Schritt 4 — Sichtprüfung

| # | Beobachtung | Soll |
|---|---|---|
| 1 | Großes Rechteck | steht **senkrecht**, in der Seitenansicht sichtbar |
| 2 | Spline | wölbt sich **nach oben**, Scheitel 30 mm über der Oberkante |
| 3 | Richtungsmarke | zeigt **waagerecht zur Seite** |
| 4 | Kleines Rechteck | **300 mm seitlich** versetzt, nicht darüber |
| 5 | Spline glatt, ohne Beulen oder Schlingen? | ja |
| 6 | Vier Rechteckkanten sichtbar zusammenhängend? | ja |

Zum Vergleich: Bei einem Import auf das **Standard-KS** liegt das Rechteck flach, der Spline hängt in die Tiefe, die Marke zeigt nach oben und das kleine Rechteck schwebt 300 mm darüber — so sah es beim ersten Versuch am 05.09.2026 aus. Wer beide Zustände einmal gesehen hat, hat die Konvention bewiesen statt behauptet.

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
2. **Neu**, Kürzel `aeroimp`, Name „Aero Studio: IBL importieren".
3. **Aufzeichnen** starten, Schritt 3 komplett durchführen, **Stopp**.
4. Speichern, dann auf einem **frischen Teil abspielen** und prüfen, ob die Kurven wieder korrekt sitzen.
5. Mapkey-Text aus der `config.pro` herauskopieren (`C:\Users\janni\config.pro`).

**Erwartete Schwierigkeit:** Der Dateiname steckt in der aufgezeichneten Klickfolge mit drin. Für M5 brauchen wir entweder einen festen Dateinamen, den das Tool immer überschreibt, oder eine Mapkey-Variante, die den Dialog offen lässt. Was in Creo 8 davon geht, findet sich hier heraus. **Klappt es nicht auf Anhieb, ist das kein Rückschlag** — es ist die Information, auf der M5 aufbaut.

---

## Was am Ende zurückkommt

1. Einheiten der Teamvorlage (Schritt 2, Punkt 3)
2. Die sechs Sichtprüfungen (Schritt 4)
3. Die acht Messwerte (Schritt 5)
4. Kommentierte Datei importierbar? (Schritt 6)
5. Mapkey-Text und ob das Abspielen funktioniert (Schritt 7)
6. Alles, was unerwartet war — Fehlermeldungen bitte wörtlich

---

## Abnahme M0

- [x] Umgebung geprüft, nichts zu installieren
- [x] IBL-Import funktioniert grundsätzlich
- [x] Achskonvention verstanden und in `creo8.yaml` festgeschrieben
- [ ] Alle acht Messungen innerhalb ±0,01 mm
- [ ] Spline glatt und durch seine Stützpunkte
- [ ] Verhalten bei Kommentarzeilen geklärt
- [ ] Mapkey wiederholt den Import ohne Handeingriff
- [ ] `creo8.yaml` ohne offene Einträge außer `OFFEN_BIS_M4` und `OFFEN_BIS_M5`

Was nicht klappt, wird nicht weggelassen, sondern notiert — davon hängt der Zuschnitt von M1 und M5 ab.
