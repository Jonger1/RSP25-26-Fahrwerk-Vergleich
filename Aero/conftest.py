"""Macht das Paket `aerostudio` fuer pytest auffindbar.

Ohne diese Datei laufen die Tests nur, wenn man pytest aus dem Ordner Aero
heraus startet. Mit ihr gehen sie aus dem Projektwurzelverzeichnis genauso -
und damit auch in jeder spaeteren automatischen Pruefung.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
