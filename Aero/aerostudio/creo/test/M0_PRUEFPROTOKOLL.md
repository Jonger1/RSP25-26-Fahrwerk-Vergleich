# M0 — Prüfprotokoll

**Ziel:** Beweisen, dass eine Kurve aus dem Tool maßhaltig und wiederholbar in Creo 8 landet. Solange das nicht bewiesen ist, ist alles ab M1 Spekulation.

Stand 21.09.2026: Umgebung geprüft, **nichts zu installieren**. Maßhaltigkeit bewiesen, Splineverhalten identifiziert. Offen sind nur noch die Sichtprüfung mit der vorgedrehten Datei, der Kommentartest und der Mapkey — **zusammen ein Durchlauf von etwa 15 Minuten**, danach ist M0 zu.

**Was noch offen ist, sagt das Skript — nicht diese Liste:**

```
python M0_abnahme.py
```

Es liest `creo8.yaml` und die Prüfkurven, rechnet nach, was ohne Creo nachrechenbar ist, und nennt jeden Eintrag, der noch auf eine Antwort wartet, mit seinem Pfad in der YAML. Eine handgepflegte Häkchenliste weiß immer nur so viel, wie zuletzt jemand hineingeschrieben hat — diese hier stand am 21.09. noch auf „Mapkey entfällt", was auf einer Verwechslung beruhte (siehe Schritt 7).

**Dateien** in diesem Ordner:

| Datei | Wofür |
|---|---|
| `M0_pruefkurve.ibl` | die Prüfkurve, ohne Kommentare |
| `M0_kommentar_vor_kopf.ibl` | dieselbe Geometrie, `!`-Zeilen **über** `open` |
| `M0_kommentar_nach_kopf.ibl` | dieselbe Geometrie, `!`-Zeilen **unter** `arclength` |
| `M0_kommentar_zwischen.ibl` | dieselbe Geometrie, `!`-Zeilen **vor jeder Sektion** |
| `M0_pruefkurve_kommentiert.ibl` | Altbestand, identisch mit `vor_kopf` |

Neu erzeugen mit `python erzeuge_pruefkurve.py`. Dass alle Varianten **punktgleiche** Geometrie haben, prüft `M0_abnahme.py` nach — sonst wäre ein Formunterschied in Creo nicht als Kommentarbefund lesbar.

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

## Schritt 2 — Testteil anlegen

1. **Datei → Neu → Teil → Volumenkörper**, Name `M0_TEST`.
2. **Standardschablone verwenden lassen** — Haken drin lassen.

   > Wir nehmen bewusst die **Teamvorlage** `sut_de_startt.prt`. Die Aeroteile müssen später in derselben Baugruppe leben wie der Rest des Fahrzeugs: gleiche Ebenenbenennung, gleicher Zeichnungsstandard, gleiche Parameter. Die absolute Genauigkeit von 0,01 mm steht in eurer `config.pro` ohnehin schon.

3. Fertig. **Es ist kein Koordinatensystem anzulegen.**

### Warum kein eigenes Koordinatensystem mehr

Die Teamvorlage hat **Y als Hochachse**, das Werkzeug rechnet mit **Z nach oben** — weil das Reglement durchgehend über Höhen über Grund argumentiert (T 8.2: „lower than 500 mm from the ground") und `z = 0` auf der Bodenebene jede Regelprüfung zu einem Vergleich macht.

Ursprünglich sollte dieser Unterschied durch ein von Hand gedrehtes `CS_AERO` aufgelöst werden. **Das war der falsche Ort.** Ein handgebautes Koordinatensystem ist selbst eine Fehlerquelle: Wer versehentlich +90° statt −90° dreht, bekommt eine gespiegelte Geometrie, ohne dass es an der Form auffällt.

Seit 09.09.2026 dreht deshalb **der Exporter**, gesteuert über `export.frame_map` in `creo8.yaml`:

```
Creos X-Achse = unser +x        (nach hinten)
Creos Y-Achse = unser +z        (nach oben)
Creos Z-Achse = unser -y        (Spannweite)
```

Das Minuszeichen ist Pflicht, nicht Geschmack: Mit `+y` wäre die Abbildung eine Spiegelung (Determinante −1). Der Exporter rechnet die Determinante aus und verweigert die Arbeit, wenn sie nicht +1 ist.

Die Konvention sitzt damit weiterhin an genau einer Stelle, ist aber versionierbar und testbar — und **in Creo ist nichts vorzubereiten**.

---

## Schritt 3 — Import

Die `.ibl` ist bereits vorgedreht. Es genügt der schlichte Import:

1. **Modell → Daten abrufen → Importieren**
2. Zur `M0_pruefkurve.ibl` navigieren. Wird sie nicht angezeigt: Dateityp-Filter auf **Alle Dateien**.
3. Unter **Importtyp** → **Kurve** wählen, bestätigen.
4. Bestätigen — **kein Koordinatensystem auszuwählen**, das Standard-KS ist richtig.

Alternativ geht auch **Datei → Öffnen** direkt auf die `.ibl`; Creo legt dann ein neues Teil an. Bequem zum Nachmessen, aber ohne Vorlage und ohne Modellparameter — für den Arbeitsablauf ist der Import in ein vorhandenes Teil der richtige Weg.

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

Beim ersten Versuch am 05.09.2026 — noch mit ungedrehter Datei — lag das Rechteck flach, der Spline hing in die Tiefe, die Marke zeigte nach oben und das kleine Rechteck schwebte 300 mm darüber. Genau das kehrt die Drehung im Exporter jetzt um.

---

## Schritt 5 — Messen *(erledigt am 09.09.2026)*

Alle Sollwerte exakt getroffen, gemessen mit **Analyse → Messen**:

| # | Messung | Soll | Creo | |
|---|---|---|---|---|
| 1 | Unterkante großes Rechteck | 200,000 mm | 200,000 | ✓ |
| 2 | Vorderkante großes Rechteck | 50,000 mm | 50,000 | ✓ |
| 3 | Höhe großes Rechteck | 50,000 mm | 50,000 | ✓ |
| 4 | Länge großes Rechteck | 200,000 mm | 200,000 | ✓ |
| 5 | Kleines Rechteck | 100 × 25 mm | 100,000 × 25,0000 | ✓ |
| 6 | Querabstand der Rechtecke | 300,000 mm | 300,000 | ✓ |
| 7 | Lücke Spline-Ende zu Rechteckecke | 0,000 mm | 0,0000000000 | ✓ |
| 8 | Bogenlänge des Splines | — | 210,184 mm | siehe unten |

Zeile 7 ist wichtiger, als sie aussieht: Sie beweist, dass Creo aufeinanderfolgende Sektionen sauber zusammensetzt, wenn der erste Punkt gleich dem letzten des Vorgängers ist. Darauf baut jede spätere Profilkontur auf.

### Der eigentliche Fund: 210,184 mm

Aus der Bogenlänge des Splines lässt sich ablesen, welchen Kurventyp Creo baut:

| Kurventyp | Bogenlänge |
|---|---|
| kubischer Spline, natural | 210,1791 mm |
| **kubischer Spline, not-a-knot** | **210,1857 mm** |
| Creo, gemessen | **210,184 mm** |

Abweichung **1,7 µm auf 210 mm**, also 8 ppm. Damit ist geklärt: Creo baut aus einer IBL-Sektion einen **interpolierenden kubischen Spline mit not-a-knot-Randbedingung, parametrisiert über die kumulierte Sehnenlänge**. Nachrechnen mit [`spline_verifikation.py`](spline_verifikation.py).

Zwei Folgerungen:

**Der Scheitel ist damit belegt, ohne ihn zu messen.** Ein interpolierender Spline läuft exakt durch seine Stützpunkte; aus der Symmetrie der fünf Punkte folgt der Scheitel bei genau x = 100,000 / z = 80,000.

**Die Punktzahl pro Profilkurve wird ab jetzt gerechnet, nicht geschätzt.** Weil sich in Python dieselbe Kurve bauen lässt, die Creo bauen wird, ist die Abweichung zur echten Profilkontur vorher berechenbar:

```
NACA 4412, Sehne 250 mm, Kosinusverteilung
  20 Punkte  ->  0,1142 mm    zu grob
  30 Punkte  ->  0,0135 mm    grenzwertig
  40 Punkte  ->  0,0037 mm    unter Modellgenauigkeit
  80 Punkte  ->  0,0023 mm    kein Gewinn mehr
```

Die Annahme im Konzept lautete 60–120 Punkte — das war zu konservativ. Es sind eher **40**. Mehr Punkte kosten Regenerationszeit und erhöhen das Risiko welliger Splines, ohne etwas zu verbessern. In M1 wird daraus eine Funktion: Toleranz vorgeben, Punktzahl fällt heraus.

---

## Schritt 6 — Kommentarzeilen testen *(der wichtigste offene Punkt)*

**Warum das kein Nebenschauplatz ist:** Das Werkzeug verlässt sich im Betrieb längst darauf. `ui/app.py` schreibt in **jede** exportierte IBL fünf Kommentarzeilen samt `AERO_SPEC_HASH`, das Skelett ebenso. Fällt der Befund negativ aus, ist nicht ein Nebenweg betroffen, sondern jeder Export.

**Was schon bewiesen ist:** Das Zeichen `!` als Kommentar am Zeilenende funktioniert. Jede geschriebene Sektion trägt `begin section ! 1`, und der Import vom 09.09. lief damit durch. Offen ist allein die **Position ganzer Kommentarzeilen**.

Deshalb drei Dateien statt einer — ein einzelner Fehlschlag mit einer gemischten Datei sagt sonst nicht, welche Stelle Creo stört:

| # | Datei | `!`-Zeilen stehen | Import klappt? |
|---|---|---|---|
| 1 | `M0_kommentar_vor_kopf.ibl` | über `open` | ☐ ja ☐ nein |
| 2 | `M0_kommentar_nach_kopf.ibl` | unter `arclength` | ☐ ja ☐ nein |
| 3 | `M0_kommentar_zwischen.ibl` | vor jeder Sektion | ☐ ja ☐ nein |

Jede Datei in ein frisches Teil importieren, wie in Schritt 3. Fehlermeldungen **wörtlich** notieren.

**Was daraus folgt:**

- **Mindestens eine Variante klappt** → der Spec-Hash darf in die Datei. Jede Kurve in Creo ist bis auf den Git-Stand rückverfolgbar, ohne Umweg über Modellparameter. Die klappende Variante wird zur Vorgabe.
- **Keine klappt** → IBL-Dateien bleiben kommentarfrei. In `creo8.yaml` genügt dann `befunde.ibl_kommentarzeilen_erlaubt: false`; der Exporter lässt sie ab dem nächsten Start von selbst weg. **Am Code ist nichts zu ändern** — genau dafür gibt es die Adapterschicht. Die Herkunft steht dann nur im Creo-Parameter `AERO_SPEC_HASH`, den M5 setzt.

Einzutragen in `creo8.yaml` unter `befunde`: `ibl_kommentar_vor_kopf`, `ibl_kommentar_nach_kopf`, `ibl_kommentar_zwischen_sektionen` und die Zusammenfassung `ibl_kommentarzeilen_erlaubt`.

---

## Schritt 7 — Mapkey aufzeichnen

> **Korrektur vom 21.09.2026.** In `creo8.yaml` stand hierzu `ENTFAELLT`, begründet damit, dass die Student Edition keine Toolkit-Anwendungen lädt. Das war ein Kurzschluss — es sind zwei verschiedene Mechanismen:
>
> - Ein **Mapkey** ist ein Bordmittel von Creo Parametric: eine aufgezeichnete Klickfolge in der `config.pro`. Kein TOOLKIT, kein J-Link, keine Zusatzlizenz. **Er lässt sich hier aufzeichnen und abspielen.**
> - **CREOSON** ist eine Toolkit-Anwendung, die einen Mapkey von *außen* abfeuert. Das ist es, was die Lizenz blockiert.
>
> Nicht erreichbar ist also nur das Abfeuern aus Python, nicht der Mapkey selbst. Er lohnt trotzdem: Er ersetzt die vier Importklicks durch ein Tastenkürzel und ist die fertige Vorarbeit für M5, sobald eine Volllizenz da ist.

Der Baustein, aus dem in M5 die Automatisierung wird.

1. **Werkzeuge → Mapkeys** (falls dort nicht zu finden: Datei → Optionen → Umgebung).
2. **Neu**, Kürzel `aeroimp`, Name „Aero Studio: IBL importieren".
3. **Aufzeichnen** starten, Schritt 3 komplett durchführen, **Stopp**.
4. Speichern, dann auf einem **frischen Teil abspielen** und prüfen, ob die Kurven wieder korrekt sitzen.
5. Mapkey-Text aus der `config.pro` herauskopieren (`C:\Users\janni\config.pro`).

**Erwartete Schwierigkeit:** Der Dateiname steckt in der aufgezeichneten Klickfolge mit drin. Für M5 brauchen wir entweder einen festen Dateinamen, den das Tool immer überschreibt, oder eine Mapkey-Variante, die den Dialog offen lässt. Was in Creo 8 davon geht, findet sich hier heraus. **Klappt es nicht auf Anhieb, ist das kein Rückschlag** — es ist die Information, auf der M5 aufbaut.

---

## Was am Ende zurückkommt

Alles wandert nach `creo8.yaml`, nicht in eine Notiz — nur dort wirkt es.

| # | Frage | Eintrag in `creo8.yaml` |
|---|---|---|
| 1 | Die sechs Sichtprüfungen (Schritt 4) | `befunde.sichtpruefung_ok` |
| 2 | Kommentare über `open`? | `befunde.ibl_kommentar_vor_kopf` |
| 3 | Kommentare unter `arclength`? | `befunde.ibl_kommentar_nach_kopf` |
| 4 | Kommentare vor jeder Sektion? | `befunde.ibl_kommentar_zwischen_sektionen` |
| 5 | Zusammenfassung daraus | `befunde.ibl_kommentarzeilen_erlaubt` |
| 6 | Mapkey-Text | `mapkeys.import_curve` |
| 7 | Mapkey zum Löschen des Import-Features | `mapkeys.delete_import_feature` |
| 8 | Steckt der Dateiname fest im Mapkey? | `mapkeys.dateiname_im_mapkey` |

Alles, was unerwartet war, gehört dazu — Fehlermeldungen bitte **wörtlich**. Was nicht klappt, wird nicht weggelassen, sondern notiert: Davon hängt der Zuschnitt von M5 ab.

---

## Abnahme M0

Der Stand wird **nicht mehr hier** gepflegt, sondern gerechnet:

```
python M0_abnahme.py
```

Das Skript prüft ohne Creo nach, dass die Achsabbildung eine Drehung und keine Spiegelung ist, dass die Sollmaße in der erzeugten Datei stecken und dass alle Kommentarvarianten punktgleiche Geometrie haben. Danach listet es jeden Eintrag aus `creo8.yaml`, der noch auf eine Antwort wartet — getrennt nach „blockiert M0" und „bewusst auf M4/M5 vertagt". Es endet mit Rückgabewert 0, sobald M0 zu ist.

**Bereits bewiesen** (Details in `creo8.yaml` unter `befunde` und `spline`):

- [x] Umgebung geprüft, nichts zu installieren
- [x] IBL-Import funktioniert, Direktimport ohne eigenes Koordinatensystem
- [x] Alle Messungen exakt getroffen, ±0,01 mm eingehalten
- [x] Spline glatt und durch seine Stützpunkte, Kurventyp identifiziert (not-a-knot, 8 ppm)
- [x] Achskonvention festgeschrieben, in den Exporter verlegt und **vom Code aus der Profildatei gelesen** (M0 Aufgabe 6)
- [x] Einheiten der Teamvorlage bestätigt
- [x] `!` als Kommentar am Zeilenende belegt (`begin section ! 1`)
