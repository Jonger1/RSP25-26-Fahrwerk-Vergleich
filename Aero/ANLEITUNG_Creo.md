# Von der IBL-Datei zum Bauteil in Creo

Was das Werkzeug schreibt, ist immer dasselbe Format: eine `.ibl` mit
Bezugskurven, fertig gedreht ins Koordinatensystem der Creo-Vorlage. Was in
Creo daraus wird, hängt davon ab, welche **Ausgabe** im Reiter *Creo* gewählt
war.

| Ausgabe im Werkzeug | Was in Creo ankommt | Womit es weitergeht |
|---|---|---|
| Eine geschlossene Kurve | ein umlaufender Spline | Skizze → **Profil** (Extrudieren) |
| Profil aus zwei Kurven | Ober- und Unterseite getrennt | Skizze → beide projizieren → **Profil** |
| 3D-Flügel | ein Stapel geschlossener Schnitte | **Berandungsverbund** |

Der wichtigste Unterschied: **Extrudieren geht nur mit einer Skizze.** Eine
importierte Bezugskurve ist keine Skizze. Sie muss erst in eine Skizze
projiziert werden — das sind die zwei Extraklicks in Weg A unten.

---

## Weg A — ebenes Profil extrudieren

Für ein einzelnes Flügelelement mit konstantem Querschnitt.

1. **Datei importieren.** Menüband **Modell** → Gruppe *Daten abrufen* →
   **Importierte Bezugskurve** (`Insert → Model Datum → Curve → From File`).
   Die `.ibl` wählen, als Koordinatensystem das Standard-KS der Vorlage
   nehmen, **OK**.
2. Im Modellbaum steht jetzt ein Eintrag **Kurve Aus Datei ID …**.
3. **Skizze anlegen.** Menüband **Modell** → Gruppe *Bezug* → **Skizze**.
   Als Skizzenebene die Ebene wählen, in der die Kurve liegt — bei der
   Standardausgabe des Werkzeugs ist das die Ebene **Creo-Z = 0**.
4. Im Skizzierer: **Skizze** → **Projizieren** (`Use Edge` / `Project`).
   Die importierte Kurve anklicken. Sie wird als Skizzengeometrie übernommen.
5. Skizze schließen (grüner Haken).
6. Menüband **Modell** → Gruppe *Formen* → **Profil** (das ist in Creo der
   Befehl fürs Extrudieren). Tiefe eintragen, grüner Haken.

**Wenn Creo meckert „Abschnitt ist nicht geschlossen":** Dann war im Werkzeug
die Ausgabe *Profil aus zwei Kurven* gewählt. Zwei Kurven, die sich nur
berühren, sind für Creo keine geschlossene Kontur. Entweder in Schritt 4
**beide** Kurven projizieren, oder im Werkzeug auf *Eine geschlossene Kurve*
umstellen und neu exportieren.

---

## Weg B — 3D-Flügel aus dem Schnittstapel

Für den verwundenen Flügel über die Spannweite. Ergebnis: erst ein
Vollkörper, daraus die Hülle mit Laminatwandstärke.

### B1 — Fläche über die Schnitte legen

1. Menüband **Modell** → Gruppe *Flächen* → **Berandungsverbund**.
2. Der Sammler für die **erste Richtung** ist aktiv. Jetzt im Grafikfenster
   die **innerste** Schnittkurve anklicken (die an der Wurzel).
3. **Strg gedrückt halten** und die übrigen Schnitte **der Reihe nach** nach
   außen anklicken, bis zur Spitze.
   *Die Reihenfolge ist entscheidend.* Wird ein Schnitt übersprungen oder in
   falscher Reihenfolge gewählt, verdreht sich die Fläche sichtbar.
4. Die Vorschau prüfen: Sie muss glatt wie ein Flügel aussehen. Sieht sie
   verdreht oder eingeschnürt aus → Reihenfolge stimmt nicht.
5. Grüner Haken.

Dass alle Schnitte gleich viele Punkte haben, in derselben Richtung laufen
und am selben Punkt beginnen, stellt das Werkzeug sicher — das ist die
häufigste Ursache für einen verdrehten Verbund und deshalb im Export hart
geprüft.

### B2 — Die beiden Enden schließen

Der Berandungsverbund ist ein offenes Rohr. Ein Volumen braucht eine
rundum geschlossene Hülle.

6. Menüband **Modell** → Gruppe *Flächen* → **Füllen**
   (steht ggf. hinter dem kleinen Pfeil **Flächen ▾**).
7. Die **Wurzelkurve** anklicken — die geschlossene Kurve ist eben, Creo
   nimmt sie direkt als Begrenzung. Grüner Haken.
8. Schritt 6 und 7 für die **Spitzenkurve** wiederholen.

Klappt die direkte Auswahl nicht, geht es auch über eine Skizze: im
Füllen-Dialog **Referenz → Definieren**, Skizzenebene = die Ebene des
Schnitts, dort die Kurve **projizieren**.

### B3 — Zusammenführen

9. Im **Modellbaum** den Berandungsverbund anklicken, dann mit **Strg** die
   beiden Füllflächen dazu. (Im Baum trifft man sicherer als im Grafikfenster.)
10. Menüband **Modell** → Gruppe *Editieren* → **Zusammenführen**. Grüner Haken.

Führt Creo nur zwei Flächen auf einmal zusammen, den Schritt einfach
wiederholen, bis nur noch **ein** Flächenverbund im Baum steht.

### B4 — Vollkörper

11. Den zusammengeführten Flächenverbund auswählen.
12. Menüband **Modell** → Gruppe *Konstruktion* → **Verbundvolumen**.
13. Auf die Richtungspfeile achten: Das Material soll **nach innen** gefüllt
    werden, nicht der Außenraum. Grüner Haken.

Jetzt ist der Flügel ein Vollkörper. Bis hierher reicht es, wenn er nur
vernetzt oder als STEP in die CFD soll.

### B5 — Hülle für Fertigung und CAD

14. Menüband **Modell** → Gruppe *Konstruktion* → **Schale**.
15. **Dicke** = die Wandstärke je Haut aus dem Werkzeug (Prepreg-Vorgabe
    0,6 mm). Das ist **eine** Haut — die zweite entsteht auf der Gegenseite
    von selbst, weil die Schale beidseitig aushöhlt.
16. Als **zu entfernende Flächen** die Wurzel- und die Spitzenfläche
    anklicken (mit **Strg**). Der Flügel ist damit an beiden Enden offen —
    so wird er auch laminiert.
17. Grüner Haken.

---

## Wenn die Schale fehlschlägt

Das ist kein Bedienfehler, sondern Geometrie: **An der Hinterkante ist das
Profil dünner als zwei Wandstärken.** Bei 0,6 mm je Haut braucht die Schale
dort mindestens 1,2 mm Bauhöhe — die hat ein Hochauftriebsprofil im letzten
Prozent der Sehne nicht.

Das Werkzeug rechnet genau diese Stelle aus und zeigt sie im Reiter *Profil*
unter **„Vollmaterial ab … % Sehne"**. Beim E423 mit 250 mm Sehne und 0,6 mm
Haut liegt sie bei 98,2 % — die letzten knapp 5 mm sind massiv.

Drei Möglichkeiten, in dieser Reihenfolge sinnvoll:

1. **Hinterkante abschneiden.** Vor dem Schalen die letzten Prozent der Sehne
   mit einem Schnitt entfernen und die Schnittfläche mit als „zu entfernende
   Fläche" wählen. Entspricht der Realität: Dort werden ohnehin zwei Schalen
   verklebt, es gibt keinen Hohlraum.
2. **Dünner schalen** und die dicke Stelle später aufdicken.
3. **Auf die Schale verzichten** und den Vollkörper behalten, wenn das Teil
   nur für CFD oder für die Bauraumprüfung gebraucht wird.

---

## Koordinatensystem — warum in Creo nichts vorzubereiten ist

Das Werkzeug rechnet mit **z nach oben**, weil das Reglement über Höhen über
Grund argumentiert. Die Creo-Vorlage hat **Y nach oben**. Diese Drehung
erledigt der Export beim Schreiben der Datei, nicht du in Creo. Die
Abbildung steht als Daten in `aerostudio/creo/profiles/creo8.yaml` und wird
beim Schreiben geprüft: Wäre sie eine Spiegelung statt einer Drehung, bricht
der Export ab, statt ein seitenverkehrtes Profil auszuliefern.

Deshalb: **Beim Import einfach das Standard-Koordinatensystem der Vorlage
nehmen.** Kein selbstgebautes gedrehtes KS.

## Genauigkeit

Die Punktzahl wird gerechnet, nicht geschätzt — auf Basis einer Nachbildung
des Creo-Splines, die in M0 gegen Creo verifiziert wurde (210,184 mm gemessen
gegenüber 210,1857 mm gerechnet, Abweichung 1,7 µm).

Zwei Dinge, die daraus folgen:

* Eine **geschlossene** Kurve braucht das Zwei- bis Dreifache an Punkten wie
  zwei getrennte Hälften. Der Knick an der Hinterkante liegt nicht mehr auf
  einer Kurvengrenze, er muss durch dichte Stützpunkte erzwungen werden.
* Punkte, die enger beieinander lägen als Creos Modellgenauigkeit von
  0,01 mm, werden vor dem Schreiben entfernt. Creo hielte sie für denselben
  Punkt und lehnte den Spline ab. Das Werkzeug sagt in der Exportinfo, wie
  viele es waren.

---

## Skelett — Flügel parametrisch verstellen

Der Weg oben bringt fertige Flächen nach Creo. Wer den Anstellwinkel später
noch ändern will, hat dann ein Problem: Jede Änderung heißt neu exportieren
und neu importieren.

Das Skelett dreht das um. Es enthält nur **Linien**: je Element eine
Drehachse auf der Viertelsehne, dazu die Querlinie als festen Bezug und die
Bezugslinien des Reglements. Der Flügel hängt in Creo an seiner Achse, und der
Anstellwinkel wird zu einem Maß, das sich ändern lässt.

**Warum die Viertelsehne:** Dort liegt näherungsweise der Neutralpunkt. Das
Moment ändert sich beim Verstellen am wenigsten, und die Hinterkante wandert
nicht davon. Eine Achse an der Nase führt beim Verstellen zu beidem.

### Ablauf

1. Im Werkzeug, Reiter **Creo**: **Skelett schreiben (nur Achsen)**. Die Datei
   heißt wie dein Entwurf, mit dem Zusatz *Skelett*.
2. In Creo ein **neues Bauteil** anlegen — das wird das Skelett, und es bleibt
   dauerhaft bestehen.
3. **Modell** → *Daten abrufen* → **Importierte Bezugskurve**, die
   Skelett-Datei wählen, Standard-Koordinatensystem, **OK**.
4. Du bekommst ein Kurvenfeature mit mehreren Geraden. Welche Linie welche
   ist, steht als Kommentar im **Kopf der Datei** — mit Texteditor öffnen,
   die ersten Zeilen lesen.
5. Für jede Drehachse: **Modell** → *Bezug* → **Achse**, die zugehörige Gerade
   auswählen. Jetzt hast du benannte Achsen statt Kurven.
6. Für jedes Element eine **Bezugsebene** anlegen: **Modell** → *Bezug* →
   **Ebene**, als Referenzen die Achse und die Querlinie wählen, und als Maß
   den **Winkel** eintragen. Genau dieses Maß ist später dein Anstellwinkel.
7. Den Flügel in einem eigenen Bauteil bauen und über **Copy Geometry** oder
   eine Baugruppenbedingung an Achse und Ebene hängen.

Danach änderst du den Anstellwinkel, indem du das Winkelmaß aus Schritt 6
änderst und regenerierst. Kein Export, kein Import.

### Was in der Skelettdatei steht

| Linie | Wozu |
|---|---|
| Drehachse je Element | Die Achse, um die der Flügel verstellt wird |
| Querlinie | Fester Bezug quer zum Fahrzeug, damit die Elemente zueinander nicht verrutschen |
| Bodenebene z = 0 | Bezug für alle Höhenmaße des Reglements |
| Vorderachse x = 0 | Ursprung der Längsmaße |
| Vorderkante Vorderreifen | Die Ebene, auf die sich T 8.2.1 im 2027-Entwurf bezieht |
| T 8.2.1 Höhengrenze 350 mm | Darüber darf vor dem Rad nichts stehen |
| T 8.2.2 Breitengrenze | Äußerster Punkt des Vorderrads |
| T 2.2.1 Bodenfreiheit 30 mm | Die Linie, die im Bremsfall nicht unterschritten werden darf |

Damit steht das Reglement im CAD und nicht nur im Kopf des Aerodynamikers.
