"""
Tests fuer die Umgebung: Stimmt die Paketliste noch mit dem Code ueberein?

Anlass ist ein echter Fund. In "Aero Studio.bat" stand eine handgepflegte
Paketliste, in der matplotlib fehlte - obwohl geometrie/kaskade.py es fuer
die Kollisionspruefung importiert. Aufgefallen ist es nie, weil neuralfoil
ueber AeroSandbox zufaellig matplotlib mitbringt. Waere neuralfoil je
weggefallen oder optional geworden, haette die Kaskadenpruefung mit einem
nackten ImportError aufgehoert zu arbeiten, und niemand haette den
Zusammenhang gesehen.

Solche Fehler findet kein Fachtest, weil auf dem Entwicklungsrechner immer
alles installiert ist. Deshalb pruefen diese Tests nicht Verhalten, sondern
Buchhaltung: Jedes Fremdpaket, das der Code importiert, steht in
requirements.txt - und der Starter installiert aus genau dieser Datei.
"""

import ast
import re
import sys
from pathlib import Path

import pytest

WURZEL = Path(__file__).resolve().parent.parent
QUELLEN = WURZEL / "aerostudio"
ANFORDERUNGEN = WURZEL / "requirements.txt"
STARTER = WURZEL / "Aero Studio.bat"

# Importname != Paketname. Nur die Faelle, die bei uns vorkommen - eine
# vollstaendige Abbildung gibt es nicht und waere auch nicht pflegbar.
PAKETNAME = {"yaml": "pyyaml"}

# Das eigene Paket und alles aus der Standardbibliothek gehoert nicht in die
# Anforderungen. sys.stdlib_module_names gibt es seit Python 3.10; das ist
# ohnehin die Untergrenze des Projekts.
EIGEN = {"aerostudio", "tests", "conftest"}


def _oberster_name(modul: str) -> str:
    return modul.split(".")[0]


def _importierte_fremdpakete() -> dict[str, set[Path]]:
    """Alle Fremdpakete, die unter aerostudio/ importiert werden, mit Fundort.

    Auch Importe innerhalb von Funktionen werden erfasst - genau so war
    matplotlib versteckt.
    """
    gefunden: dict[str, set[Path]] = {}
    for datei in sorted(QUELLEN.rglob("*.py")):
        baum = ast.parse(datei.read_text(encoding="utf-8"), filename=str(datei))
        for knoten in ast.walk(baum):
            if isinstance(knoten, ast.Import):
                namen = [_oberster_name(a.name) for a in knoten.names]
            elif isinstance(knoten, ast.ImportFrom):
                # level > 0 ist ein relativer Import im eigenen Paket.
                if knoten.level or not knoten.module:
                    continue
                namen = [_oberster_name(knoten.module)]
            else:
                continue
            for name in namen:
                if name in EIGEN or name in sys.stdlib_module_names:
                    continue
                gefunden.setdefault(name, set()).add(datei.relative_to(WURZEL))
    return gefunden


def _angefordert() -> set[str]:
    """Die Paketnamen aus requirements.txt, klein geschrieben, ohne Version."""
    namen = set()
    for zeile in ANFORDERUNGEN.read_text(encoding="utf-8").splitlines():
        zeile = zeile.split("#", 1)[0].strip()
        if not zeile or zeile.startswith("-"):
            continue
        treffer = re.match(r"^([A-Za-z0-9._-]+)", zeile)
        if treffer:
            namen.add(treffer.group(1).lower().replace("_", "-"))
    return namen


def test_jeder_import_steht_in_den_anforderungen():
    angefordert = _angefordert()
    fehlend = {}
    for name, dateien in _importierte_fremdpakete().items():
        paket = PAKETNAME.get(name, name).lower().replace("_", "-")
        if paket not in angefordert:
            fehlend[paket] = sorted(str(d) for d in dateien)
    assert not fehlend, (
        "Diese Pakete werden importiert, stehen aber nicht in "
        f"requirements.txt: {fehlend}"
    )


def test_keine_anforderung_die_niemand_benutzt():
    """Die Gegenrichtung - sonst waechst die Liste um Pakete wie ezdxf zu.

    ezdxf und shapely standen jahrelang in der Installationsliste, ohne dass
    eine Zeile sie importiert haette. Das kostet bei jeder Ersteinrichtung
    Zeit und verschleiert, was das Werkzeug wirklich braucht.
    """
    importiert = {
        PAKETNAME.get(n, n).lower().replace("_", "-")
        for n in _importierte_fremdpakete()
    }
    ueberfluessig = sorted(_angefordert() - importiert)
    assert not ueberfluessig, (
        "Diese Pakete stehen in requirements.txt, werden aber nirgends "
        f"importiert: {ueberfluessig}. Entweder benutzen oder streichen."
    )


def test_starter_installiert_aus_der_anforderungsdatei():
    """Der Doppelklick-Starter darf keine eigene Paketliste fuehren."""
    text = STARTER.read_text(encoding="utf-8", errors="replace")
    assert "-r \"%~dp0requirements.txt\"" in text, (
        "Aero Studio.bat installiert nicht aus requirements.txt"
    )
    # Eine zweite Liste faellt daran auf, dass Paketnamen direkt hinter
    # "pip install" stehen statt hinter -r.
    for zeile in text.splitlines():
        if "pip install" in zeile and "-r " not in zeile:
            assert "--upgrade" in zeile and "pip" in zeile.split("install")[1], (
                f"Der Starter installiert Pakete an requirements.txt vorbei: {zeile.strip()}"
            )


@pytest.mark.parametrize("modul", ["numpy", "scipy", "pydantic", "yaml",
                                   "dash", "plotly", "matplotlib"])
def test_angefordertes_paket_laesst_sich_importieren(modul):
    """Was in der Liste steht, muss in dieser Umgebung auch da sein.

    neuralfoil fehlt hier bewusst: Es ist der einzige Eintrag, ohne den das
    Werkzeug weiterarbeitet - die Profilpolare faengt das ab und sagt
    verstaendlich, was fehlt.
    """
    pytest.importorskip(modul)
