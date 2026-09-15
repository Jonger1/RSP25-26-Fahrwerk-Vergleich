"""
Datenmodell von Aero Studio.

Der gesamte Zustand des Programms steckt in diesen Objekten und wird als YAML
gespeichert. Die Oberflaeche haelt nichts eigenes - sie liest das Spec, stellt
es dar und schreibt Aenderungen hinein. Dadurch sind Oberflaeche und
Kommandozeile automatisch gleichwertig, und jeder Designstand ist eine
diffbare Textdatei im Git.
"""

from __future__ import annotations

from enum import Enum
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator


class Wirkrichtung(str, Enum):
    """Wofuer das Element da ist.

    Praktisch jedes Katalogprofil ist fuer AUFTRIEB gezeichnet - sie stammen
    aus dem Flugzeugbau. Am Rennwagen braucht man fast immer das Gegenteil,
    deshalb ist Abtrieb die Vorgabe und das Profil wird dafuer gespiegelt.

    Auftrieb bleibt waehlbar, weil es Anwendungen gibt, in denen er gewollt
    ist - Bullwings zum Beispiel, die vorne Auftrieb erzeugen, um die
    Aerobalance nach hinten zu verschieben.
    """

    abtrieb = "abtrieb"
    auftrieb = "auftrieb"


class Verfahren(str, Enum):
    """Fertigungsverfahren. Bestimmt die erreichbaren Mindestdicken."""

    nasslaminat = "nasslaminat"
    prepreg = "prepreg"
    autoklav = "autoklav"
    unbestimmt = "unbestimmt"


# Startwerte je Verfahren.
#
# ANNAHMEN, keine gemessenen Werte aus eurer Fertigung. Sie stammen aus dem,
# was im Formula Student ueblich ist: Handlaminat traegt am meisten Harz auf
# und wird am dicksten, Prepreg im Ofen liegt dazwischen, im Autoklaven wird
# es am duennsten, weil der Druck das Laminat verdichtet.
#
# Gedacht als Ausgangspunkt, nicht als Vorschrift - jeder Wert bleibt
# einstellbar, und die Oberflaeche merkt sich, was ihr je Verfahren zuletzt
# benutzt habt. Sobald ihr eigene Werte gemessen habt, gehoeren sie hierher.
VERFAHRENSVORGABEN: dict[str, dict[str, float]] = {
    "nasslaminat": {"wandstaerke": 1.2, "kern": 0.0, "klebespalt": 0.30},
    "prepreg":     {"wandstaerke": 0.6, "kern": 3.0, "klebespalt": 0.20},
    "autoklav":    {"wandstaerke": 0.4, "kern": 3.0, "klebespalt": 0.15},
    "unbestimmt":  {"wandstaerke": 1.0, "kern": 0.0, "klebespalt": 0.20},
}


def vorgaben_fuer(verfahren) -> dict[str, float]:
    """Startwerte eines Verfahrens, immer als frische Kopie."""
    schluessel = getattr(verfahren, "value", verfahren)
    return dict(VERFAHRENSVORGABEN.get(schluessel,
                                       VERFAHRENSVORGABEN["unbestimmt"]))


class Fertigung(BaseModel):
    """Fertigungsgrenzen eines Bauteils.

    Die Fluegel werden unterschiedlich gebaut - Nasslaminat, Prepreg, Autoklav -
    und unterscheiden sich dadurch in der erreichbaren Wandstaerke. Deshalb ist
    die Dicke ein Parameter und keine Konstante, und sie laesst sich pro
    Element ueberschreiben.

    Zwei Werte kommen dagegen aus dem Reglement und stehen fest:
    T 2.4.1 verlangt 3 mm Radius fuer alle nach vorne gerichteten Kanten und
    1 mm fuer alle uebrigen. Daraus folgen Nasenradius >= 3 mm und
    Hinterkantendicke >= 2 mm. Sie lassen sich hier nur bewusst hochsetzen,
    nicht unterschreiten - der Validator prueft das.
    """

    model_config = ConfigDict(extra="forbid")

    verfahren: Verfahren = Verfahren.unbestimmt

    wandstaerke: float = Field(
        default=1.5, gt=0.0,
        description="Dicke EINER Laminathaut in mm.")
    kern: float = Field(
        default=0.0, ge=0.0,
        description="Kerndicke in mm. 0 = kein Kern, reine Schale.")
    kern_zonenweise: bool = Field(
        default=True,
        description="Kern nur dort einlegen, wo das Profil dick genug ist. "
                    "Wo es zusammenlaeuft, bleibt reine Schale, ganz hinten "
                    "Vollmaterial. Das ist der reale Aufbau einer Fluegelschale "
                    "- und es entkoppelt die Kerndicke von der Frage, ob sich "
                    "das Bauteil ueberhaupt bauen laesst.")

    dicke_min_ueberschreibung: Optional[float] = Field(
        default=None, gt=0.0,
        description="Setzt die berechnete Mindestdicke ausser Kraft. "
                    "Nur verwenden, wenn ein Bauteil nachweislich duenner geht.")

    hinterkante_min: float = Field(
        default=2.0, ge=2.0,
        description="Mindestdicke der Hinterkante in mm. 2.0 folgt aus T 2.4.1 "
                    "(1 mm Radius) und ist die untere Grenze.")

    # ---- Verklebung -----------------------------------------------------
    # Team-Entscheidung 09.09.2026: Die Hinterkante wird nicht in das
    # aerodynamische Profil gezeichnet, sondern entsteht beim Verkleben der
    # Ober- und Unterschale. Ein Profil mit spitzer Hinterkante ist damit
    # zulaessig - die gebaute Kante ist es, die zaehlt.
    #
    # Das Werkzeug schaltet die Pruefung deshalb nicht ab, sondern rechnet die
    # gebaute Dicke aus dem Aufbau: zwei Haeute plus Klebespalt. So bleibt
    # sichtbar, was am Ende wirklich am Bauteil steht.
    hinterkante_durch_verklebung: bool = Field(
        default=True,
        description="Hinterkante entsteht durch Verkleben, nicht durch die "
                    "Profilform. Die Pruefung wird dann zum Hinweis.")
    klebespalt: float = Field(
        default=0.2, ge=0.0,
        description="Klebstoffdicke an der Hinterkante in mm.")
    verklebung_beginn_max: float = Field(
        default=0.85, gt=0.0, lt=1.0,
        description="Ab wo darf das Profil in den vollen Klebekeil uebergehen? "
                    "Anteil der Sehne. Frueher hiesse: das Bauteil ist hinten "
                    "auf einer langen Strecke Vollmaterial - schwer und teuer.")
    nasenradius_min: float = Field(
        default=3.0, ge=3.0,
        description="Mindestnasenradius in mm. 3.0 folgt aus T 2.4.1 fuer "
                    "nach vorne gerichtete Kanten und ist die untere Grenze.")

    @property
    def hinterkante_gebaut(self) -> float:
        """Dicke der fertigen Hinterkante in mm: zwei Haeute plus Klebespalt."""
        return 2.0 * self.wandstaerke + self.klebespalt

    @property
    def dicke_schale(self) -> float:
        """Dicke, ab der eine reine Schale ohne Kern moeglich ist: zwei Haeute."""
        return 2.0 * self.wandstaerke

    @property
    def dicke_sandwich(self) -> float:
        """Dicke, ab der ein Sandwich moeglich ist: zwei Haeute plus Kern."""
        return 2.0 * self.wandstaerke + self.kern

    @property
    def dicke_min(self) -> float:
        """Kleinste Dicke, bei der sich das Bauteil ueberhaupt noch bauen laesst.

        Bei zonenweisem Kern sind das zwei Haeute - der Kern entfaellt einfach
        dort, wo das Profil zusammenlaeuft. Wer den Kern durchgehend haben will,
        setzt kern_zonenweise auf false; dann bindet die Sandwichdicke.
        """
        if self.dicke_min_ueberschreibung is not None:
            return self.dicke_min_ueberschreibung
        return self.dicke_schale if self.kern_zonenweise else self.dicke_sandwich

    def beschreibung(self) -> str:
        if self.dicke_min_ueberschreibung is not None:
            herkunft = "gesetzt"
        elif self.kern > 0 and self.kern_zonenweise:
            herkunft = (f"2 x {self.wandstaerke:g} Haut, "
                        f"{self.kern:g} Kern zonenweise")
        elif self.kern > 0:
            herkunft = f"2 x {self.wandstaerke:g} Haut + {self.kern:g} Kern durchgehend"
        else:
            herkunft = f"2 x {self.wandstaerke:g} Haut"
        hk = (f"Hinterkante {self.hinterkante_gebaut:g} mm aus Verklebung"
              if self.hinterkante_durch_verklebung
              else f"Hinterkante >= {self.hinterkante_min:g} mm")
        return (f"{self.verfahren.value}, Mindestdicke {self.dicke_min:g} mm "
                f"({herkunft}), {hk}, "
                f"Nasenradius >= {self.nasenradius_min:g} mm")


class ProfilAusDatei(BaseModel):
    """Profil aus einer Koordinatendatei, etwa aus der UIUC-Datenbank."""

    model_config = ConfigDict(extra="forbid")
    art: Literal["datei"] = "datei"
    datei: str


class ProfilNaca(BaseModel):
    """Analytisch erzeugtes NACA-4-Profil. Vergleichsbasis, kein Abtriebsprofil."""

    model_config = ConfigDict(extra="forbid")
    art: Literal["naca"] = "naca"
    woelbung: float = Field(default=0.04, ge=-0.25, le=0.25,
                            description="Groesste Woelbung, Anteil der Sehne. "
                                        "Negativ erzeugt ein nach unten "
                                        "gewoelbtes Profil. Ueber 9.5 % verlaesst "
                                        "man die Standard-NACA-Familie - die "
                                        "Formel gilt weiter, Literaturdaten "
                                        "gibt es dann aber keine mehr.")
    woelbungslage: float = Field(default=0.4, gt=0.0, lt=1.0,
                                 description="Lage der groessten Woelbung.")
    dicke: float = Field(default=0.12, gt=0.0, le=0.40,
                         description="Groesste Dicke, Anteil der Sehne.")


class ProfilCst(BaseModel):
    """Profil in CST/Kulfan-Darstellung. Das ist die Form fuer die Optimierung.

    Glatt, wenige Parameter, stetig differenzierbar - und dieselbe Darstellung,
    mit der NeuralFoil ab M3 intern arbeitet.
    """

    model_config = ConfigDict(extra="forbid")
    art: Literal["cst"] = "cst"
    oben: list[float]
    unten: list[float]
    hinterkante_dicke: float = Field(
        default=0.0, ge=0.0,
        description="Hinterkantendicke als Anteil der Sehne. 0 = spitz; "
                    "der Fertigungscheck macht daraus spaeter eine echte Dicke.")

    @model_validator(mode="after")
    def _gleich_viele(self) -> "ProfilCst":
        if len(self.oben) != len(self.unten):
            raise ValueError(
                f"CST braucht gleich viele Koeffizienten oben und unten, "
                f"hat aber {len(self.oben)} und {len(self.unten)}.")
        if len(self.oben) < 2:
            raise ValueError("CST braucht mindestens zwei Koeffizienten je Seite.")
        return self


Profilquelle = ProfilAusDatei | ProfilNaca | ProfilCst


class Stuetzstelle(BaseModel):
    """Ein Punkt der Spannweitenverteilung.

    Sehne wirkt multiplikativ auf die Wurzelsehne, Verwindung additiv auf den
    Grundanstellwinkel. So bleibt der Entwurf lesbar: Man sieht sofort, ob ein
    Fluegel nach aussen schmaler oder staerker angestellt wird, ohne
    Absolutwerte vergleichen zu muessen.
    """

    model_config = ConfigDict(extra="forbid")

    y: float = Field(ge=0.0, description="Abstand von der Fahrzeugmitte in mm.")
    sehne: float = Field(default=1.0, gt=0.0,
                         description="Faktor auf die Wurzelsehne.")
    verwindung: float = Field(default=0.0,
                              description="Zusaetzlicher Anstellwinkel in Grad. "
                                          "Negativ innen erzeugt Outwash.")
    z: float = Field(default=0.0, description="Hoehenversatz in mm.")
    x: float = Field(default=0.0, description="Laengsversatz in mm, Pfeilung.")


class Spannweite(BaseModel):
    """Wie sich das Profil ueber die Spannweite veraendert."""

    model_config = ConfigDict(extra="forbid")

    stuetzstellen: list[Stuetzstelle] = Field(min_length=1)
    schnitte: int = Field(default=13, ge=2, le=101,
                          description="Wieviele Profilschnitte exportiert werden. "
                                      "Mehr Schnitte bilden eine Verwindung "
                                      "feiner ab, kosten in Creo aber "
                                      "Regenerationszeit.")

    @model_validator(mode="after")
    def _pruefe(self) -> "Spannweite":
        stellen = [s.y for s in self.stuetzstellen]
        if len(set(stellen)) != len(stellen):
            raise ValueError("Zwei Stuetzstellen liegen auf derselben "
                             "Spannweitenposition.")
        return self

    def skaliert(self, halbspannweite: float) -> "Spannweite":
        """Streckt die Verteilung auf eine andere Halbspannweite.

        Die Stuetzstellen der Vorgaben liegen auf festen y-Werten. Wer eine
        andere Spannweite braucht, will fast immer denselben VERLAUF an
        anderer Stelle - also proportional gestreckt und nicht abgeschnitten.
        """
        weite = max(s.y for s in self.stuetzstellen)
        if weite <= 0.0:
            return self.model_copy(deep=True)
        faktor = float(halbspannweite) / weite
        neu = self.model_copy(deep=True)
        for stelle in neu.stuetzstellen:
            stelle.y *= faktor
        return neu

    @staticmethod
    def frontfluegel_aussen() -> "Spannweite":
        """Aussenabschnitt eines Frontfluegels, massvoll verwunden.

        Innen etwas staerker angestellt als aussen - das leitet Luft nach
        aussen um das Vorderrad herum (Outwash) und entlastet gleichzeitig die
        Fluegelspitze, wo die Stroemung ohnehin um die Kante laeuft.

        WARUM NUR -3 GRAD UND NICHT -10:

        Eine erste Fassung stand innen auf -10 Grad, nach Arbeiten zu
        SEGMENTIERTEN Frontfluegeln. Das war eine falsche Uebertragung: Dort
        sind die inneren Elemente eigene BAUTEILE mit eigenem Anstellwinkel,
        keine Verwindung einer durchgehenden Flaeche. Gerechnet ergab das:

          * Verwindungsrate 24 Grad je Meter. Eine durchgehende Haut wird
            dabei sichtbar eingeschnuert - in Creo faellt das sofort auf.
          * Die Wurzel stand bei -14 Grad und damit ZWEI GRAD JENSEITS des
            Abrisses des E423 (-12 Grad). Sie ueberlebte nur, weil der
            induzierte Winkel sie knapp zurueckholte.
          * Der oertliche Beiwert lief von -2.03 innen (genau CLmax) auf
            -0.32 aussen. Die hoechste Last lag also dort, wo die Sehne am
            KUERZESTEN war - genau die Stelle, die im CAD spitz aussieht.

        Der Handel: 58,8 N mit der alten Fassung gegen 54,6 N mit dieser -
        sieben Prozent weniger Abtrieb fuer fuenf Grad Abrissreserve und eine
        Verwindungsrate von 6,7 statt 24 Grad je Meter. Am Fahrzeug bewegt
        Nicken und Federn den wirksamen Winkel um mehrere Grad; ohne Reserve
        reisst die Wurzel in der ersten Bremszone ab.

        Wer den starken Outwash will, baut ihn als eigenes ELEMENT - dafuer
        ist die Kaskade da, nicht die Verwindung.
        """
        return Spannweite(stuetzstellen=[
            Stuetzstelle(y=0.0, sehne=0.95, verwindung=-3.0, z=0.0),
            Stuetzstelle(y=300.0, sehne=1.00, verwindung=-1.0, z=4.0),
            Stuetzstelle(y=600.0, sehne=1.00, verwindung=1.0, z=14.0),
        ], schnitte=13)

    @staticmethod
    def frontfluegel_stark_verwunden() -> "Spannweite":
        """Die alte, aggressive Fassung - fuer den Vergleich aufgehoben.

        Bringt rund sieben Prozent mehr Abtrieb, stellt die Wurzel dafuer an
        den Abriss und laesst eine durchgehende Flaeche in der Mitte
        einschnueren. Sinnvoll nur, wenn der innere Bereich als eigenes
        Element gebaut wird. Die Zahlen stehen im Docstring von
        frontfluegel_aussen().
        """
        return Spannweite(stuetzstellen=[
            Stuetzstelle(y=0.0, sehne=0.85, verwindung=-10.0, z=0.0),
            Stuetzstelle(y=250.0, sehne=0.95, verwindung=-4.0, z=0.0),
            Stuetzstelle(y=450.0, sehne=1.00, verwindung=0.0, z=8.0),
            Stuetzstelle(y=600.0, sehne=1.00, verwindung=2.0, z=22.0),
        ], schnitte=13)

    @staticmethod
    def gerade(halbspannweite: float = 500.0) -> "Spannweite":
        """Rechteckfluegel ohne Verwindung - der einfachste Fall."""
        return Spannweite(stuetzstellen=[
            Stuetzstelle(y=0.0), Stuetzstelle(y=halbspannweite)], schnitte=5)


class Kaskadenstufe(BaseModel):
    """Ein Flap hinter dem Hauptelement.

    Alles RELATIV zum Vorgaenger, weil das die Groessen sind, die ein
    Aerodynamiker einstellt und die in jeder Veroeffentlichung stehen.
    Absolute Koordinaten muesste man bei jeder Sehnenaenderung neu ausrechnen,
    und ein Zahlendreher faellt dort nicht auf.
    """

    model_config = ConfigDict(extra="forbid")

    profil: str = Field(default="e58.dat",
                        description="Katalogdatei des Flapprofils oder "
                                    "'NACA xxxx' fuer ein NACA-4-Profil.")
    sehne: float = Field(default=0.35, gt=0.0, le=1.0,
                         description="Anteil der Sehne des Hauptelements.")
    winkel: float = Field(default=-20.0,
                          description="Zusaetzlicher Anstellwinkel gegenueber "
                                      "dem Vorgaenger, in Grad.")
    spalt: float = Field(default=0.015, gt=0.0, le=0.2,
                         description="Kuerzester Abstand zum Vorgaenger, "
                                     "als Anteil der Hauptsehne. Ueblich sind "
                                     "0.01 bis 0.02.")
    ueberlappung: float = Field(default=0.02, ge=-0.2, le=0.2,
                                description="Wie weit die Nase VOR der "
                                            "Hinterkante des Vorgaengers "
                                            "steht, als Anteil der Hauptsehne.")

    # --- Teilfluegel ----------------------------------------------------
    # Ein Flap muss nicht ueber die ganze Spannweite laufen. So bauen es die
    # meisten Formula-Student-Teams: innen, vor dem Unterboden, bleibt das
    # Hauptelement flach oder allein, damit Luft in den Unterbodenkanal
    # gelangt; aussen, vor dem Reifen, sitzt der aggressivste Teil.
    y_von: Optional[float] = Field(
        default=None, ge=0.0,
        description="Innerer Beginn in mm ab Fahrzeugmitte. None = dort, wo "
                    "das Hauptelement beginnt.")
    y_bis: Optional[float] = Field(
        default=None, ge=0.0,
        description="Aeusseres Ende in mm ab Fahrzeugmitte. None = dort, wo "
                    "das Hauptelement endet.")
    winkel_aussen: Optional[float] = Field(
        default=None,
        description="Winkel gegen den Vorgaenger am aeusseren Ende, in Grad. "
                    "Dazwischen linear. None = ueberall wie `winkel`.")

    @model_validator(mode="after")
    def _pruefe_bereich(self) -> "Kaskadenstufe":
        if (self.y_von is not None and self.y_bis is not None
                and self.y_bis <= self.y_von):
            raise ValueError("Das aeussere Ende eines Teilflaps muss weiter "
                             "aussen liegen als sein Beginn.")
        return self


class Element(BaseModel):
    """Ein Fluegelelement: Profil, Sehne, Anstellwinkel.

    Die Lage relativ zum Vorgaenger (Gap, Overlap) kommt in M2 dazu.
    """

    model_config = ConfigDict(extra="forbid")

    id: str
    name: str = Field(
        default="",
        max_length=60,
        description="Freier Name des Entwurfs. Steht im Dateinamen des "
                    "Exports und im Kopf der IBL-Datei. Leer = die id.")
    profil: Profilquelle = Field(discriminator="art")
    sehne: float = Field(gt=0.0, description="Sehnenlaenge in mm.")
    anstellwinkel: float = Field(
        default=0.0,
        description="Anstellwinkel in Grad. Negativ = Nase nach unten.")
    wirkrichtung: Wirkrichtung = Field(
        default=Wirkrichtung.abtrieb,
        description="Abtrieb ist die Vorgabe - Katalogprofile sind fuer "
                    "Auftrieb gezeichnet und werden dafuer gespiegelt. "
                    "Auftrieb waehlt man fuer Bullwings.")

    # Lage im Fahrzeug-Koordinatensystem: x nach hinten, y nach rechts,
    # z nach oben, Ursprung Vorderachsmitte auf der Bodenebene. Ohne diese
    # Angabe laesst sich kein Regelcheck rechnen - das Reglement nennt
    # ausschliesslich absolute Lagen am Fahrzeug.
    pos_x: float = Field(default=-600.0,
                         description="Nasenposition der Wurzel in mm. Negativ "
                                     "= vor der Vorderachse.")
    pos_y: float = Field(default=0.0,
                         description="Beginn der Spannweite in mm ab Mitte.")
    pos_z: float = Field(default=60.0,
                         description="Hoehe des TIEFSTEN Punkts des ganzen Fluegels samt Flaps "
                                     "ueber Grund in mm, ueber alle Schnitte - wie T 2.2.1 misst.")

    kaskade: list[Kaskadenstufe] = Field(
        default_factory=list,
        description="Flaps hinter diesem Element. Leer = einzelnes Element.")

    spannweite: Optional[Spannweite] = Field(
        default=None,
        description="Verteilung ueber die Spannweite. None = ebener Schnitt, "
                    "also nur ein Profil ohne Fluegel.")

    fertigung: Optional[Fertigung] = Field(
        default=None,
        description="Ueberschreibt die Fertigungsvorgaben des Pakets. "
                    "None = Vorgabe des Pakets verwenden.")

    def fertigung_wirksam(self, vorgabe: Fertigung) -> Fertigung:
        return self.fertigung if self.fertigung is not None else vorgabe

    @property
    def anzeigename(self) -> str:
        """Was der Anwender sieht. Faellt auf die id zurueck, damit nie eine
        namenlose Datei entsteht."""
        return self.name.strip() or self.id
