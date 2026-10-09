# Aero Studio – Anleitung

Aero Studio ist das Werkzeug der Rennschmiede Pforzheim, um Flügel und Unterboden
für die Formula Student auszulegen: Profil wählen, zur Kaskade anordnen, über die
Spannweite verteilen, Abtrieb abschätzen, gegen das Reglement prüfen und als
Kurven nach Creo exportieren.

Geprüft wird ausschließlich gegen die **FS Rules 2027 v1.0**. Das Original liegt
neben dieser Datei als `FS_Rules_2027_v1.0.pdf`.

---

## 1. Installieren und starten

**Voraussetzungen**

* Windows-Rechner mit **Python 3.10 bis 3.13** von <https://www.python.org/downloads/>.
  Beim Installieren unbedingt **„Add Python to PATH“** ankreuzen.
* Beim ersten Start eine Internetverbindung (es werden einige hundert MB Pakete
  geladen, vor allem NeuralFoil für die Profilpolaren).
* Für den Export nach Creo: Creo 8. Ohne Creo funktioniert alles außer dem
  direkten Öffnen in Creo.

**Starten**

1. Den Ordner `AERO` holen (siehe Abschnitt 9, „Teilen“).
2. **Doppelklick auf `Aero Studio.bat`.**
   Beim ersten Mal legt der Starter eine eigene Python-Umgebung im Ordner `.venv`
   an und installiert alles aus `requirements.txt`. Das dauert einige Minuten und
   passiert nur einmal.
3. Der Browser öffnet sich auf <http://127.0.0.1:8051>. Falls nicht: die Adresse
   selbst eingeben.
4. Das schwarze Fenster offen lassen, dort laufen die Meldungen auf. Zum Beenden
   das Fenster schließen.

Das Programm läuft nur auf dem eigenen Rechner. Es ist keine Webseite im Internet,
und es werden keine Daten verschickt.

**Wenn etwas nicht startet:** Den Ordner `.venv` löschen und `Aero Studio.bat`
erneut starten. Die Umgebung wird dann frisch angelegt. Meldet das Fenster
„Port belegt“, läuft Aero Studio schon in einem anderen Fenster.

---

## 2. Grundidee: der Entwurf ist eine Datei

Alles, was du in der Oberfläche einstellst, ergibt **ein AeroSpec** – eine
YAML-Textdatei mit Profil, Sehne, Winkeln, Kaskade, Spannweite, Endplatte,
Unterboden und Fahrzeuglage. Jede Rechnung, jede Regelprüfung und jeder Export
leitet sich allein aus diesem Spec ab.

* Oben rechts steht der **Spec-Hash**, ein Fingerabdruck des Entwurfs. Er steht
  auch in jeder exportierten Datei. So lässt sich jede IBL-Datei in Creo einem
  Entwurfsstand zuordnen.
* **„Spec speichern“** (oben rechts) schreibt den Entwurf nach
  `specs/aktuell.yaml`. Der vorherige Stand wandert in die Historie (Reiter
  Projekt).
* **Beim Start öffnet Aero Studio `specs/aktuell.yaml` automatisch.** Du
  machst also dort weiter, wo du zuletzt gespeichert hast.
* **„Herunterladen“** (oben rechts) speichert den Entwurf als YAML-Datei auf
  deinem Rechner, zum Weitergeben oder Sichern.
* **Reiter Projekt → „Entwurf öffnen“** lädt jedes andere Spec in die Felder,
  aus der Liste oder per Ziehen einer YAML-Datei vom eigenen Rechner:
  ein Beispiel aus `specs/beispiele/`, eine Paketvariante aus `specs/pakete/`
  oder den Entwurf eines Teamkollegen. Danach „Spec speichern“, um damit
  weiterzuarbeiten.
* Fertige Startpunkte liegen in `specs/beispiele/`: ein zweielementiger
  Frontflügel und ein Heckflügel.

> **Ein Flügel im Editor:** Der Editor bearbeitet immer einen Flügel. Öffnest
> du ein Paket mit Front- und Heckflügel, erscheint der erste, und die Meldung
> sagt es. Die anderen Flügel nimmst du im Reiter Balance unter „Weitere Specs“
> dazu. Front- und Heckflügel deshalb am besten als getrennte Dateien
> speichern, z. B. `specs/frontfluegel.yaml` und `specs/heckfluegel.yaml`
> (Datei kopieren und umbenennen).

---

## 3. Ein Flügel von Anfang bis Ende

So entsteht ein Frontflügel. Die Reiter stehen oben in der Leiste.

1. **Profil** – Katalogprofil (z. B. E423, S1223) oder NACA wählen, Sehne und
   Anstellwinkel setzen. Unten siehst du Kontur und Fertigungsprüfung
   (Wandstärke, Hinterkante, Nasenradius).
2. **Flügel** – Spannweite festlegen: eine Vorgabe laden oder die
   Sektionstabelle selbst füllen (y, Sehnenfaktor, Verwindung, Versatz). Dazu
   kommen die Lage am Fahrzeug (Nase vor der Vorderachse, Höhe des tiefsten
   Punkts über Grund) und die Endplatte. Mit **„Abtrieb rechnen“** bekommst du
   Abtrieb, Widerstand und die Höhenkennlinie. **„Flügel vorschlagen“** sucht
   Sehne, Spannweite und Winkel zu einem Zielabtrieb.
3. **Kaskade** – Flaps hinter dem Hauptelement anlegen (Profil, Sehne, Winkel
   gegen den Vorgänger, Spalt, Überlappung, optional Teilflügel von/bis y).
   Darunter:
   * der Schnitt mit **Druckverteilung** an einer verschiebbaren Stelle,
   * **„Abtrieb räumlich rechnen“** für die ganze Kaskade über die Spannweite,
   * **DRS**: In der Spalte „DRS offen“ den Flapwinkel bei offenem DRS
     eintragen, dann „DRS vergleichen“ bzw. „Familientabelle für Creo
     schreiben“,
   * **Generator**: probiert Profilpaarungen und Elementzahlen durch,
   * **DXF**: Rippen und Schablonen für die Fertigung.
4. **Fahrzeug & Regeln** – Regelampel gegen FS Rules 2027 v1.0 über den
   Federweg (aus- und eingefedert), dazu Seiten- und Draufsicht mit allen
   Grenzen. Rot heißt: so nicht baubar.
5. **Creo** – „IBL schreiben“ erzeugt die Kurvendatei, „Skelett schreiben“ nur
   die Drehachsen. Wie es in Creo weitergeht, steht in
   [ANLEITUNG_Creo.md](ANLEITUNG_Creo.md).
6. **Projekt** – „Entwurf öffnen“, frühere Stände zurückholen und
   **„Report als PDF“**. Gespeichert wird oben rechts mit „Spec speichern“.

---

## 4. Die Reiter im Überblick

| Reiter | Wofür |
|---|---|
| **Profil** | Profilquelle, Sehne, Anstellwinkel, Wirkrichtung (Abtrieb/Auftrieb), Fertigungsverfahren und -prüfung, Polaren über mehrere Reynoldszahlen |
| **Flügel** | Spannweitenverteilung, Lage am Fahrzeug, Endplatte und Footplate, Abtriebsabschätzung, Flügelvorschlag zu einem Zielabtrieb |
| **Kaskade** | Flaps, Druckverteilung am Schnitt, räumlicher Abtrieb, DRS, Generator, DXF-Fertigungsvorlagen |
| **Unterboden** | Kanal mit Einlass, Kehle und Diffusor; Rake und Drehpunkt; Druckverlauf, Höhenkennlinie; DoE mit Pareto-Front |
| **Balance** | Gesamtfahrzeug aus mehreren Specs: Abtrieb, Achslasten, Balance vorn, Nickwanderung, DRS offen; Paket-Optimierung |
| **Fahrzeug & Regeln** | Regelampel FS Rules 2027 v1.0 mit Fahrzustand, Seiten- und Draufsicht |
| **Creo** | Export als IBL, Skelett, Vorschau der Punkte |
| **Projekt** | Entwurf öffnen oder hochladen, Exporte als ZIP, Historie, PDF-Report, das komplette Spec als Text |

### Polaren über die Reynoldszahl (Reiter Profil, unten)

Die fünf Diagramme wie bei Airfoil Tools – CL über CD, CL über α, CL/CD über
α, CD über α und CM über α –, aber für genau das Profil im Editor gerechnet
(NeuralFoil, Ncrit 9 wie XFOIL). Sie rechnen live mit, sobald sich das Profil
ändert.

* **Reynoldszahlen**: mit Komma getrennt, `200000`, `200k` und `2e5` sind
  gleich. Bis zu acht.
* **Dazu aus Geschwindigkeit**: z. B. `10, 20` – die Reynoldszahl kommt dann
  aus Tempo und Sehne. So sieht man, welche Polare im Betrieb gilt.
* **Gestrichelt** ist, wo NeuralFoil sich selbst unter 80 % sicher ist, meist
  hinter dem Abriss. Über den Diagrammen steht es zusätzlich im Klartext: je
  Reynoldszahl die unsicheren Winkelbereiche (orange), **rot**, wenn der
  eingestellte Anstellwinkel in einem unsicheren Bereich liegt oder eine Polare
  fast überall unsicher ist – die dann nicht zum Auslegen verwenden. Die Tabelle darunter nennt CL-Maximum, beste Gleitzahl,
  CD min, CL und CM bei 0° und den sicheren Winkelbereich je Reynoldszahl.
* Bei Wirkrichtung **Abtrieb** ist das Profil gespiegelt, die Kurven stehen
  gegenüber Airfoil Tools auf dem Kopf (negatives CL = Abtrieb). Für den
  direkten Vergleich die Wirkrichtung auf Auftrieb stellen.
* **Polaren als CSV** lädt alle Werte als Tabelle herunter.

### Unterboden

Haken bei **„Unterboden rechnen“** setzen, dann die Maße eintragen. Die
Rechnung läuft sofort mit (Kanalmodell, Millisekunden).

* **Rake** gilt für das ganze Auto: positiv heißt hinten höher. Der
  **Drehpunkt** legt fest, wo sich die Höhe nicht ändert.
* **Abdichtung** ist geschätzt (keine Schürzen erlaubt, T 2.2.2) und der erste
  Wert, der mit CFD abgeglichen werden sollte.
* **DoE rechnen**: Viele Varianten von Einlass, Kehle, Diffusor und Rake. Ein
  Klick auf einen Punkt der Pareto-Front übernimmt dessen Werte in die Felder.

### Balance und Paket-Optimierung

1. Unter **„Weitere Specs“** die übrigen Teile dazunehmen, z. B.
   `beispiele/heckfluegel.yaml`. Das Spec im Editor ist immer dabei.
2. **Zielbalance vorn [%]** eintragen. Üblich ist die statische Achslast vorn.
   Steht sie in `aerostudio/spec/vehicle_ref.yaml` unter
   `fahrdynamik.achslast_vorne_prozent`, ist das Feld vorbelegt.
3. **„Balance rechnen“** zeigt Gesamtabtrieb, Achslasten, Balance und wie weit
   die Balance beim Bremsen und Beschleunigen wandert. Mit **„DRS offen“** siehst
   du die Balance auf der Geraden.
4. **„Paket optimieren“** variiert die Anstellwinkel aller Flügel, Kehle,
   Diffusor und Rake und sucht nach viel Abtrieb, Balance am Ziel und wenig
   Wanderung. Mit **„Flügelgröße mitoptimieren“** kommen Sehne und Spannweite
   dazu (bis an die Breitengrenze des Reglements). Die erste Rechnung dauert
   dann etwa 5 Minuten.
5. Die Varianten auf der Pareto-Front sind gegen das Reglement geprüft. Klick
   auf einen Punkt zeigt die Werte. **„Variante als Paket-Spec speichern“**
   schreibt alle Flügel, Unterboden und Rake in eine Datei unter
   `specs/pakete/`.

### Report

Im Reiter **Projekt** → **„Report als PDF“**. Er nimmt die Specs, die
Geschwindigkeit und die Zielbalance aus dem Reiter Balance. Das PDF landet in
`export/` und enthält Regelkonformität, Geometrie, Druckverteilung, Abtrieb über
die Spannweite, h/c-Kurve, Unterboden, Balance, DRS und die Grenzen der Rechnung.

**Nicht enthalten** sind die Nachweise zur Frontflügelanbindung (T 3.20.2,
T 3.19.4) und zur Steifigkeit (T 8.3). Dafür fehlen dem Werkzeug die
Strukturdaten. Der Report weist das aus.

---

## 5. Kommandozeile

Für große Läufe, aus dem Ordner `AERO` heraus (Python aus `.venv`):

```
.venv\Scripts\python -m aerostudio.aero.doe --spec specs\aktuell.yaml --n 500
.venv\Scripts\python -m aerostudio.aero.paket --spec specs\beispiele\frontfluegel_zweielementig.yaml --dazu specs\beispiele\heckfluegel.yaml --ziel 45 --n 300 --groesse
.venv\Scripts\python -m aerostudio.formate.report --spec specs\aktuell.yaml --dazu specs\beispiele\heckfluegel.yaml --ziel 45
```

Die Ergebnisdateien der DoE-Läufe lassen sich danach in der Oberfläche mit
**„Datei anzeigen“** öffnen.

---

## 6. Wo was landet

| Ordner/Datei | Inhalt |
|---|---|
| `specs/aktuell.yaml` | der gespeicherte Entwurf |
| `specs/beispiele/` | Startpunkte (im Git) |
| `specs/pakete/` | gespeicherte Paketvarianten |
| `specs/.historie/` | frühere Stände von `aktuell.yaml` |
| `export/` | IBL, DXF, Familientabelle, DoE-Ergebnisse, PDF-Reports (**nicht** im Git) |
| `aerostudio/spec/vehicle_ref.yaml` | Fahrzeugmaße: Radstand, Spur, Reifen, Kopfstütze, Massen |
| `aerostudio/regeln/rules_2027.yaml` | Grenzwerte aus FS Rules 2027 v1.0, mit Wortlaut und Seite |

---

## 7. Wie genau sind die Zahlen?

Die Rechnungen sind **Abschätzungen für den Vergleich von Entwürfen**, kein
Ersatz für CFD oder Windkanal.

* **Flügel:** Traglinie mit Profil- bzw. Kaskadenpolaren (NeuralFoil,
  Panelverfahren), Bodeneffekt über Spiegelung und Kanalfaktor. Unter einer
  wirksamen Streckung von etwa 3 (typisch beim Heckflügel) ist das nur eine
  Näherung, und das Werkzeug sagt es dann.
* **Unterboden:** 1D-Kanalmodell. Abdichtung und Ablösegrenze sind geschätzt.
* **Gesamtfahrzeug:** Teile einzeln gerechnet und addiert. Räder, Karosserie
  und Wechselwirkungen (z. B. Nachlauf des Frontflügels auf dem Unterboden)
  fehlen.

Faustregel: **„A ist besser als B“ ist belastbar, „A macht 312 N“ erst nach
dem Abgleich mit CFD.**

---

## 8. Häufige Fragen

**Die Ampel ist rot, aber der Flügel sieht gut aus.**
Geprüft wird über den ganzen Federweg (T 8.2.4). Unter dem Befund steht, in
welchem Fahrzustand und an welcher Stelle die Grenze reißt.

**Die Zielbalance ist „nicht erreichbar“.**
Mit Winkeln allein lässt sich die Balance kaum verschieben. Häkchen
„Flügelgröße mitoptimieren“ setzen, einen Unterboden dazunehmen oder ein
weiteres Element am Heckflügel vorsehen.

**Die Rechnung dauert lange.**
Flügelrechnungen brauchen Sekunden, die Paket-Optimierung mit Größe beim ersten
Mal Minuten. Danach liegen die Zwischenergebnisse im Speicher, solange das
Fenster offen bleibt.

**Wo melde ich Fehler?**
Im GitHub-Repository als Issue, mit Spec-Hash und einem Screenshot.

---

## 9. Web-Version (gehostet)

Aero Studio kann auch auf einem Server laufen, damit es ohne Installation im
Browser erreichbar ist. Der Einstieg dafür ist `wsgi.py`
(z. B. `gunicorn wsgi:server`). Er schaltet den **Web-Modus** ein:

* Gespeichert wird in eine eigene Ablage auf dem Server
  (`AEROSTUDIO_ABLAGE`, sonst ein Temp-Ordner). Dort liegt nichts dauerhaft,
  und alle Nutzer teilen sich die Ablage.
* **Entwürfe deshalb immer mit „Herunterladen“ sichern** und bei Bedarf über
  „Entwurf öffnen“ wieder hochladen.
* IBL-, DXF- und PDF-Dateien holst du über Projekt → **„Exporte als ZIP“**.
  Das direkte Öffnen in Creo gibt es online nicht.
* Ein Hinweisbanner oben erinnert daran.

Lokal ändert sich durch den Web-Modus nichts.

---

## 10. Teilen und gemeinsam arbeiten

Das Programm wird über **GitHub** geteilt. Das Repository ist
`github.com/Jonger1/RSP25-26-Fahrwerk-Vergleich`, das Werkzeug liegt im Ordner
`AERO`.

**Nur benutzen** (am einfachsten):
1. Auf GitHub **Code → Download ZIP**, entpacken.
2. Im Ordner `AERO` **`Aero Studio.bat`** doppelklicken.

**Mitarbeiten und Updates bekommen** (empfohlen fürs Aero-Team):
1. **GitHub Desktop** installieren und das Repository klonen.
2. Für Updates in GitHub Desktop **„Fetch origin“ / „Pull“** klicken, dann neu
   starten. Die `.venv` bleibt erhalten.
3. Eigene Entwürfe als YAML unter `specs/` speichern und mit einer kurzen
   Beschreibung committen. So hat jeder Stand einen Namen und eine Historie.

**Nicht per USB-Stick oder Mail weitergeben.** Kopien veralten unbemerkt, und
niemand weiß mehr, welcher Stand gilt. Der Ordner `.venv` gehört nie in eine
Kopie, er ist rechnerspezifisch und wird beim ersten Start neu angelegt.
