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


class Verfahren(str, Enum):
    """Fertigungsverfahren. Bestimmt die erreichbaren Mindestdicken."""

    nasslaminat = "nasslaminat"
    prepreg = "prepreg"
    autoklav = "autoklav"
    unbestimmt = "unbestimmt"


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
        description="Kerndicke bei Sandwichaufbau in mm. 0 = kein Kern.")

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
    def dicke_min(self) -> float:
        """Kleinste zulaessige lokale Profildicke in mm.

        Zwei Haeute plus Kern - das ist die Dicke, unter der sich das Bauteil
        nicht mehr laminieren laesst, unabhaengig davon, was die Aerodynamik
        gerne haette.
        """
        if self.dicke_min_ueberschreibung is not None:
            return self.dicke_min_ueberschreibung
        return 2.0 * self.wandstaerke + self.kern

    def beschreibung(self) -> str:
        if self.dicke_min_ueberschreibung is not None:
            herkunft = "gesetzt"
        elif self.kern > 0:
            herkunft = f"2 x {self.wandstaerke:g} Haut + {self.kern:g} Kern"
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
    woelbung: float = Field(default=0.04, ge=0.0, le=0.095,
                            description="Groesste Woelbung, Anteil der Sehne.")
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


class Element(BaseModel):
    """Ein Fluegelelement: Profil, Sehne, Anstellwinkel.

    Die Lage relativ zum Vorgaenger (Gap, Overlap) kommt in M2 dazu.
    """

    model_config = ConfigDict(extra="forbid")

    id: str
    profil: Profilquelle = Field(discriminator="art")
    sehne: float = Field(gt=0.0, description="Sehnenlaenge in mm.")
    anstellwinkel: float = Field(
        default=0.0,
        description="Anstellwinkel in Grad. Negativ = Nase nach unten, "
                    "also abtriebserzeugend.")

    fertigung: Optional[Fertigung] = Field(
        default=None,
        description="Ueberschreibt die Fertigungsvorgaben des Pakets. "
                    "None = Vorgabe des Pakets verwenden.")

    def fertigung_wirksam(self, vorgabe: Fertigung) -> Fertigung:
        return self.fertigung if self.fertigung is not None else vorgabe
