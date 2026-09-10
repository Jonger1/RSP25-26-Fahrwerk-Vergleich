"""Aerodynamische Abschaetzung - Profilpolare und Traglinienrechnung.

Das Modul heisst profilpolare und nicht polare, weil die Funktion
polare() sonst den Modulnamen ueberdeckt: Nach dem Reexport hier waere
`from aerostudio.aero import polare` die Funktion, nicht das Modul.

Ausdruecklich eine ABSCHAETZUNG fuer den Vergleich von Entwuerfen, kein
Ersatz fuer CFD. Die Grenzen stehen in den Modul-Docstrings und muessen in
jeder Anzeige mit auftauchen.
"""

from .profilpolare import DICHTE, Polare, polare, polarenschar, reynolds
from .traglinie import (Fluegelkraefte, Streifen, bodenkennlinie,
                        einflussmatrix, rechne, streifen_aus_stapel)

__all__ = ["DICHTE", "Fluegelkraefte", "Polare", "Streifen", "bodenkennlinie",
           "einflussmatrix", "polare", "polarenschar", "rechne", "reynolds",
           "streifen_aus_stapel"]
