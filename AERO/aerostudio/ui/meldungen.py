"""
Ausnahmen in Saetze uebersetzen, die weiterhelfen (M6 Punkt 2).

Die Anwender sind Teammitglieder, die Aerodynamik koennen und nicht Python.
Fuer sie ist

    FileNotFoundError: [Errno 2] No such file or directory: 'e999.dat'

eine Sackgasse. Nicht weil die Meldung falsch waere, sondern weil sie nicht
sagt, was zu tun ist. Genau das verlangt M6: "jede Ausnahme wird in einen
handlungsleitenden Satz uebersetzt, technisches Detail nur auf Ausklappen".

**Drei Regeln, die dieses Modul traegt:**

1. *Was schon gut formuliert ist, bleibt.* Ein grosser Teil der Ausnahmen in
   diesem Werkzeug wird von uns selbst geworfen und traegt bereits einen
   brauchbaren deutschen Satz - "Kein Schnitt vorhanden, ohne Fluegel keine
   Endplatte". Den zu ueberschreiben waere ein Rueckschritt. Uebersetzt wird
   deshalb nur, was sicher erkannt ist.

2. *Nichts verschwindet.* Ein unbekannter Fehler bekommt keinen beruhigenden
   Allgemeinplatz, sondern wird als unerwartet benannt - und die rohe
   Meldung bleibt in jedem Fall sichtbar. Eine Oberflaeche, die Fehler
   glattbuegelt, ist schlimmer als eine, die sie roh zeigt: Beim Glattbuegeln
   sucht der Anwender den Fehler bei sich.

3. *Der Rat nennt einen Ort.* "Bitte pruefen Sie Ihre Eingaben" hilft
   niemandem. "Im Reiter Profil ein anderes Katalogprofil waehlen" schon.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Meldung:
    """Was die Oberflaeche aus einer Ausnahme macht."""

    satz: str                 # was passiert ist, in einem Satz
    rat: str = ""             # was zu tun ist, mit Ortsangabe
    erkannt: bool = True      # False = unbekannte Ausnahme, roh durchgereicht

    @property
    def vollstaendig(self) -> str:
        return f"{self.satz} {self.rat}".strip()


# Ausnahmen, die wir selbst werfen und die bereits einen brauchbaren Satz
# tragen. Ihre Meldung wird unveraendert durchgereicht.
EIGENE = ("SperreBelegt",)


def _pydantic(fehler) -> Meldung | None:
    """Uebersetzt eine pydantic-ValidationError in einen Satz.

    Pydantic meldet mehrzeilig, englisch und mit Typnamen:

        1 validation error for Element
        sehne
          Input should be greater than 0 [type=greater_than, ...]

    Gebraucht wird daraus: welches Feld, und was stimmt damit nicht.
    """
    if type(fehler).__name__ != "ValidationError":
        return None

    try:
        fehlerliste = fehler.errors()
    except Exception:
        return Meldung("Eine Eingabe passt nicht ins Datenmodell.",
                       "Der Reiter Projekt zeigt den vollständigen Spec-Text.")

    if not fehlerliste:
        return Meldung("Eine Eingabe passt nicht ins Datenmodell.")

    erster = fehlerliste[0]
    feld = ".".join(str(t) for t in erster.get("loc", ())) or "ein Feld"
    art = erster.get("type", "")
    # Mit `or` verkettet waere die Grenze 0 verlorengegangen: 0.0 ist falsy,
    # und "sehne muss groesser als 0 sein" ist genau der haeufigste Fall.
    ctx = erster.get("ctx") or {}
    grenze = next((ctx[k] for k in ("gt", "ge", "lt", "le") if k in ctx), None)

    if art == "extra_forbidden":
        satz = f"Das Feld „{feld}“ kennt das Datenmodell nicht."
        rat = ("Meist ein Tippfehler im Spec oder eine Datei aus einer "
               "älteren Version. Der Reiter Projekt zeigt den ganzen Text.")
    elif art == "missing":
        satz = f"Im Spec fehlt das Feld „{feld}“."
        rat = "Ohne dieses Feld lässt sich der Entwurf nicht aufbauen."
    elif art.startswith("greater_than") or art.startswith("less_than"):
        richtung = "größer" if art.startswith("greater") else "kleiner"
        satz = (f"Der Wert für „{feld}“ liegt außerhalb des Zulässigen — "
                f"er muss {richtung} als {grenze} sein.")
        rat = "Der Regler daneben hält sich von selbst an die Grenzen."
    elif art in ("model_type", "dict_type"):
        satz = "Die Datei ist kein gültiges AeroSpec."
        rat = ("Vermutlich wurde eine andere YAML-Datei geladen. Ein "
               "Startpunkt liegt unter specs/beispiele/.")
    else:
        satz = f"Der Wert für „{feld}“ passt nicht."
        rat = str(erster.get("msg", "")).strip()

    return Meldung(satz, rat)


def _datei(fehler) -> Meldung | None:
    """FileNotFoundError und Verwandte - der haeufigste Fall im Betrieb."""
    if not isinstance(fehler, (FileNotFoundError, IsADirectoryError,
                               NotADirectoryError)):
        return None

    name = getattr(fehler, "filename", "") or ""
    kurz = name.rsplit("/", 1)[-1].rsplit("\\", 1)[-1] or "die Datei"

    if kurz.endswith(".dat"):
        return Meldung(
            f"Das Profil „{kurz}“ liegt nicht im Katalog.",
            "Im Reiter Profil ein Katalogprofil wählen, oder die .dat-Datei "
            "nach profile/katalog/ legen.")
    if kurz.endswith((".yaml", ".yml")):
        return Meldung(
            f"Die Spec-Datei „{kurz}“ gibt es nicht.",
            "Ein Startpunkt liegt unter specs/beispiele/.")
    if kurz.endswith((".ibl", ".dxf")):
        return Meldung(
            f"Der Zielordner für „{kurz}“ existiert nicht.",
            "Im Reiter Creo unter „Zielordner“ einen vorhandenen Ordner "
            "eintragen — er wird relativ zum Projektordner gesucht.")
    return Meldung(
        f"„{kurz}“ wurde nicht gefunden.",
        "Der Pfad wird relativ zum Projektordner gesucht.")


def _rechte(fehler) -> Meldung | None:
    if not isinstance(fehler, PermissionError):
        return None
    name = getattr(fehler, "filename", "") or "die Datei"
    kurz = name.rsplit("/", 1)[-1].rsplit("\\", 1)[-1] or "die Datei"
    return Meldung(
        f"Keine Schreibrechte für „{kurz}“.",
        "Häufigste Ursache: Die Datei ist noch in Creo oder Excel geöffnet. "
        "Schließen und noch einmal versuchen.")


def _pakete(fehler) -> Meldung | None:
    """Ein fehlendes Paket - betrifft in der Praxis nur neuralfoil."""
    if not isinstance(fehler, ImportError):
        return None
    name = getattr(fehler, "name", "") or ""
    if "neuralfoil" in str(fehler) or name == "neuralfoil":
        return Meldung(
            "Für diese Rechnung fehlt das Paket neuralfoil.",
            "Geometrie und Export gehen ohne es weiter, Abtriebszahlen "
            "nicht. Nachinstallieren mit: pip install -r requirements.txt")
    return Meldung(
        f"Das Paket „{name or 'unbekannt'}“ fehlt.",
        "Nachinstallieren mit: pip install -r requirements.txt")


def _speicher(fehler) -> Meldung | None:
    if not isinstance(fehler, MemoryError):
        return None
    return Meldung(
        "Der Arbeitsspeicher reicht für diese Rechnung nicht.",
        "Meist hilft eine kleinere Schnittzahl im Reiter Flügel oder eine "
        "gröbere Toleranz im Reiter Creo.")


def _schon_gut(fehler) -> Meldung | None:
    """Eigene Ausnahmen tragen schon einen brauchbaren Satz.

    Erkannt an der Klasse, nicht am Text: Eine Heuristik auf deutsche Woerter
    wuerde frueher oder spaeter eine englische Systemmeldung durchwinken.
    """
    if type(fehler).__name__ in EIGENE:
        return Meldung(str(fehler), "")
    return None


# Reihenfolge zaehlt: Die eigenen Ausnahmen zuerst, damit ihr Satz nicht von
# einer allgemeineren Regel ueberschrieben wird.
_REGELN = (_schon_gut, _pydantic, _datei, _rechte, _pakete, _speicher)


def uebersetze(fehler: BaseException) -> Meldung:
    """Macht aus einer Ausnahme einen Satz, der weiterhilft.

    Was nicht sicher erkannt wird, kommt als `erkannt=False` zurueck - dann
    zeigt die Oberflaeche die rohe Meldung und nennt sie unerwartet, statt
    einen Allgemeinplatz hinzustellen.
    """
    for regel in _REGELN:
        meldung = regel(fehler)
        if meldung is not None:
            return meldung

    # Unsere eigenen ValueError tragen fast immer schon einen deutschen Satz.
    # Sie durchzureichen ist besser, als sie durch "Unerwarteter Fehler" zu
    # ersetzen - aber als erkannt gelten sie nur, wenn sie ueberhaupt einen
    # Text haben.
    text = str(fehler).strip()
    if isinstance(fehler, ValueError) and text:
        return Meldung(text, "")

    return Meldung(
        f"Unerwarteter Fehler: {type(fehler).__name__}",
        "Das ist keine Fehleingabe, sondern vermutlich ein Programmfehler. "
        "Die Einzelheiten unten gehören in die Fehlermeldung an das Team.",
        erkannt=False)


def technisch(fehler: BaseException) -> str:
    """Die rohe Meldung - fuer das Ausklappfeld."""
    return f"{type(fehler).__name__}: {fehler}"
