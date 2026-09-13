"""Aerodynamische Abschaetzung - Profilpolare und Traglinienrechnung.

Das Modul heisst profilpolare und nicht polare, weil die Funktion
polare() sonst den Modulnamen ueberdeckt: Nach dem Reexport hier waere
`from aerostudio.aero import polare` die Funktion, nicht das Modul.

Ausdruecklich eine ABSCHAETZUNG fuer den Vergleich von Entwuerfen, kein
Ersatz fuer CFD. Die Grenzen stehen in den Modul-Docstrings und muessen in
jeder Anzeige mit auftauchen.
"""

from .entwurf import Grenzen, Kandidat, Vorschlag, suche, suche_maximum
from .profilpolare import (DICHTE, Polare, polare, polarenschar, reynolds,
                           verfuegbar)
from .traglinie import (Fluegelkraefte, Streifen, bodenkennlinie,
                        einflussmatrix, rechne, streifen_aus_stapel)

__all__ = ["DICHTE", "Fluegelkraefte", "Grenzen", "Kandidat", "Polare",
           "Streifen", "Vorschlag", "bodenkennlinie", "einflussmatrix",
           "polare", "polarenschar", "rechne", "reynolds", "suche",
           "suche_maximum",
           "streifen_aus_stapel", "verfuegbar"]
