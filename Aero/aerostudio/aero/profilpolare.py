"""
Profilpolare — CL, CD und CM über den Anstellwinkel.

Gerechnet mit NeuralFoil. Das ist ein neuronales Netz, das auf einer sehr
großen Zahl von XFOIL-Rechnungen trainiert wurde; eine Auswertung dauert
Millisekunden statt Sekunden. Für ein Werkzeug, das bei jedem Reglerzug neu
rechnen soll, ist das der Unterschied zwischen benutzbar und unbenutzbar.

**Was das Verfahren kann und was nicht — bitte lesen, bevor damit ausgelegt
wird:**

* Es ist eine Nachbildung von XFOIL, und XFOIL ist ein Panelverfahren mit
  Grenzschichtkopplung für das EINZELNE Profil. Es sieht keine Kaskade, keinen
  Boden, keine Endplatte und keine Räder.
* Im Ablösebereich wird es unsicher. NeuralFoil liefert dazu selbst ein
  Vertrauensmaß mit; das wird hier durchgereicht und gehört in die Anzeige.
  Fällt es unter etwa 0,8, ist die Zahl eine Hausnummer.
* Bei kleiner Reynoldszahl bricht der Auftrieb ein, weil die Laminarblase
  aufplatzt. Gemessen für das gespiegelte E423 bei −4 Grad: CL 1,54 bei
  Re 250 000, aber nur 0,89 bei Re 100 000 — bei gleichzeitig vierfachem
  Widerstand. Wer nur bei einer Geschwindigkeit rechnet, übersieht das.

Das alles heißt: Das Werkzeug wählt damit das Grundprofil und den groben
Arbeitsbereich. Die Feinabstimmung einer Kaskade braucht 2D-CFD.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

import numpy as np

# Luft bei 15 Grad Celsius auf Meereshöhe.
DICHTE = 1.225          # kg/m3
KINEMATISCHE_ZAEHIGKEIT = 1.48e-5   # m2/s

# Unterhalb dieses Wertes meldet NeuralFoil selbst Zweifel an seiner Aussage.
VERTRAUENSSCHWELLE = 0.80


def verfuegbar() -> bool:
    """Laesst sich die Polare ueberhaupt rechnen?

    Die Oberflaeche fragt das, bevor sie einen Knopf anbietet, der ohnehin
    nur in einer Fehlermeldung enden wuerde.
    """
    try:
        import neuralfoil  # noqa: F401
        return True
    except ImportError:
        return False


def reynolds(geschwindigkeit_ms: float, sehne_mm: float) -> float:
    """Reynoldszahl aus Fahrgeschwindigkeit und Sehnenlänge.

    Der Formula-Student-Bereich liegt niedrig: Bei 15 m/s und 250 mm Sehne
    sind es rund 250 000. Genau dort, wo Profile aus dem Flugzeugbau ihre
    Kennwerte verlieren - deshalb die Hochauftriebsprofile aus dem
    Modellflug- und Segelflugbereich im Katalog.
    """
    return float(geschwindigkeit_ms) * float(sehne_mm) / 1000.0 / KINEMATISCHE_ZAEHIGKEIT


@dataclass
class Polare:
    """Eine gerechnete Polare. Winkel in Grad."""

    alpha: np.ndarray
    cl: np.ndarray
    cd: np.ndarray
    cm: np.ndarray
    vertrauen: np.ndarray
    reynolds: float
    name: str = ""

    def _auf(self, werte: np.ndarray, alpha) -> np.ndarray:
        """Interpoliert einen Kennwert auf beliebige Winkel.

        Außerhalb des gerechneten Bereichs wird NICHT extrapoliert, sondern
        auf den Randwert geklemmt. Eine extrapolierte Polare läuft im
        Abrissbereich beliebig weit ins Falsche, und das fällt niemandem auf,
        weil die Kurve glatt bleibt.
        """
        a = np.asarray(alpha, dtype=float)
        return np.interp(a, self.alpha, werte, left=werte[0], right=werte[-1])

    def cl_bei(self, alpha):
        return self._auf(self.cl, alpha)

    def cd_bei(self, alpha):
        return self._auf(self.cd, alpha)

    def cm_bei(self, alpha):
        return self._auf(self.cm, alpha)

    def vertrauen_bei(self, alpha):
        return self._auf(self.vertrauen, alpha)

    @property
    def cl_max_betrag(self) -> float:
        """Größter erreichbarer Auftriebsbetrag - gleich für Auftrieb und Abtrieb."""
        return float(np.abs(self.cl).max())

    @property
    def abriss_winkel(self) -> float:
        """Der Winkel, bei dem der Auftriebsbetrag sein Maximum hat.

        Alles darüber hinaus ist Abriss. Für ein Abtriebsprofil ist der Wert
        negativ, weil dort die Nase nach unten steht.
        """
        return float(self.alpha[int(np.argmax(np.abs(self.cl)))])

    @property
    def beste_gleitzahl(self) -> tuple[float, float]:
        """Bester Wirkungsgrad (|CL|/CD) und der Winkel dazu.

        Am Rennwagen ist das nicht das Ziel - Abtrieb zählt mehr als
        Widerstand -, aber es ist der Bezugspunkt, gegen den sich beurteilen
        lässt, wieviel Widerstand ein Anstellwinkel zusätzlich kostet.
        """
        güte = np.abs(self.cl) / np.maximum(self.cd, 1e-9)
        i = int(np.argmax(güte))
        return float(güte[i]), float(self.alpha[i])

    def unsicher_ab(self) -> float | None:
        """Ab welchem Winkelbetrag NeuralFoil selbst unsicher wird, oder None."""
        schlecht = np.abs(self.alpha)[self.vertrauen < VERTRAUENSSCHWELLE]
        return float(schlecht.min()) if len(schlecht) else None


def polare(profil, reynolds_zahl: float,
           alpha: np.ndarray | None = None,
           modell: str = "medium") -> Polare:
    """Rechnet die Polare eines Profils.

    `profil` ist ein Profil-Objekt; gerechnet wird mit seiner Einheitssehne,
    also unabhängig von der späteren Größe. Die Größe steckt allein in der
    Reynoldszahl.
    """
    if alpha is None:
        # Von +10 bis -20 Grad: Der Abtriebsbereich braucht mehr Platz, weil
        # ein gespiegeltes Hochauftriebsprofil erst bei etwa -12 Grad abreisst.
        alpha = np.arange(10.0, -20.5, -0.5)

    punkte = profil.repanelisiert(80).punkte
    daten = _rechne(punkte.tobytes(), punkte.shape, np.asarray(alpha).tobytes(),
                    len(np.atleast_1d(alpha)), float(reynolds_zahl), modell)

    ordnung = np.argsort(np.asarray(alpha, dtype=float))
    a = np.asarray(alpha, dtype=float)[ordnung]
    return Polare(alpha=a,
                  cl=daten["CL"][ordnung], cd=daten["CD"][ordnung],
                  cm=daten["CM"][ordnung],
                  vertrauen=daten["analysis_confidence"][ordnung],
                  reynolds=float(reynolds_zahl),
                  name=getattr(profil, "name", ""))


@lru_cache(maxsize=256)
def _rechne(punkte_bytes, form, alpha_bytes, n_alpha, re, modell):
    """Der eigentliche Aufruf, gepuffert.

    Gepuffert über die Rohbytes, weil numpy-Felder nicht hashbar sind. Der
    Puffer lohnt sich nicht wegen der Rechenzeit - eine Auswertung dauert
    Millisekunden -, sondern weil die Traglinienrechnung dieselbe Polare
    dutzendfach je Iteration anfordert.
    """
    try:
        import neuralfoil as nf
    except ImportError as fehlt:
        # Klartext statt Stacktrace. Genau das ist passiert: NeuralFoil lag im
        # System-Python, das Werkzeug laeuft aber aus der projekteigenen .venv -
        # und in der Oberflaeche stand nur eine Fehlermeldung ohne Ausweg.
        raise RuntimeError(
            "NeuralFoil ist nicht installiert - ohne das Paket laesst sich "
            "keine Profilpolare und damit kein Abtrieb rechnen. "
            "So wird es nachgeholt: Aero Studio schliessen und ueber "
            "'Aero Studio.bat' neu starten; der Starter installiert "
            "fehlende Pakete von selbst. Hilft das nicht, den Ordner "
            ".venv loeschen und die .bat erneut starten - die Umgebung "
            "wird dann neu angelegt. Alles ausser dem Abtrieb "
            "funktioniert ohne NeuralFoil weiter: Profilentwurf, "
            "Fertigungspruefung, Regelpruefung und der Export nach Creo."
        ) from fehlt

    punkte = np.frombuffer(punkte_bytes, dtype=float).reshape(form)
    alpha = np.frombuffer(alpha_bytes, dtype=float).reshape(n_alpha)
    ergebnis = nf.get_aero_from_coordinates(coordinates=punkte, alpha=alpha,
                                            Re=re, model_size=modell)
    return {k: np.atleast_1d(np.asarray(v, dtype=float))
            for k, v in ergebnis.items()}


def polarenschar(profil, geschwindigkeiten, sehne_mm: float,
                 modell: str = "medium") -> dict[float, Polare]:
    """Je eine Polare für mehrere Fahrgeschwindigkeiten.

    Der Sinn ist die Gegenprobe: Ein Profil, das bei 20 m/s glänzt, kann bei
    8 m/s - Slalom, enge Schikane - deutlich schlechter dastehen, weil die
    Reynoldszahl unter die Schwelle fällt, ab der die Laminarblase aufplatzt.
    """
    return {float(v): polare(profil, reynolds(v, sehne_mm), modell=modell)
            for v in geschwindigkeiten}
