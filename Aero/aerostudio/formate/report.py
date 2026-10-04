"""
Report fuer Design-Jury und Technical Inspection (M9).

    python -m aerostudio.formate.report --spec specs/beispiele/frontfluegel_zweielementig.yaml \\
        --dazu specs/beispiele/heckfluegel.yaml --ziel 45

Ein Kommando, ein PDF. Es enthaelt genau das, was sich aus dem Spec
belegen laesst:

1. **Deckblatt und Zusammenfassung** - Entwurf, Spec-Hash, Regelstaende,
   Urteil, Kennzahlen.
2. **Regelkonformitaet** - je Teil und Regelstand: Regel, Soll, Ist,
   Reserve, der Fahrzustand, in dem die Pruefung kritisch ist.
3. **Geometrie** je Fluegel - Kaskade im Wurzelschnitt, Profilvergleich,
   Grundriss.
4. **Aerodynamik** je Fluegel - Druckverteilung, Abtrieb ueber die
   Spannweite, Bodenabstand (h/c).
5. **Unterboden** und **Gesamtfahrzeug** mit Balance, wenn vorhanden.
6. **Annahmen, Grenzen, offene Nachweise.**

**Warum matplotlib und nicht die Plotly-Bilder der Oberflaeche.** Plotly
braucht fuer PDF das Zusatzpaket kaleido, das auf Teamrechnern regelmaessig
an Chrome-Abhaengigkeiten scheitert. matplotlib steht ohnehin in der
Paketliste und schreibt PDF ohne Umweg. Die Grafiken sind deshalb eigene,
schlichte Fassungen - gedacht zum Einfuegen in den Design Report, nicht
zum Anklicken.

**Was NICHT drin ist** und im Report auch so dasteht: der Nachweis der
Frontfluegelanbindung (T 3.20.2, T 3.19.4) und die Steifigkeit nach T 8.3.
Beides braucht Schraubenbild, Streben und Laminat - Daten, die das Spec
nicht kennt. Ein Report, der dazu eine Zahl erfaende, waere schlimmer als
einer, der die Luecke benennt.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Callable

import numpy as np

A4 = (8.27, 11.69)
FARBEN = ["#3b3f46", "#cf2027", "#ea7317", "#f4c20d", "#3d6fa5"]
GRAU = "#6b7280"
# Bodenabstand relativ zur Sehne des Hauptelements fuer die h/c-Kurve.
HC_STUFEN = (0.12, 0.18, 0.25, 0.35, 0.5, 0.8)


# ================================================================ Daten

@dataclass
class Fluegelteil:
    name: str
    element: object
    befunde: dict[str, list] = field(default_factory=dict)   # Regelstand -> Befunde
    kraefte: object = None
    kaskade_wurzel: list = field(default_factory=list)       # Elementlagen
    druck: list = field(default_factory=list)                # Druckverlaeufe
    grundriss: np.ndarray | None = None                      # Punkte x, y
    profile: list = field(default_factory=list)              # (name, punkte)
    hc: list[tuple[float, float]] = field(default_factory=list)
    drs: object = None                                       # drs.Vergleich
    hinweise: list[str] = field(default_factory=list)


@dataclass
class Reportdaten:
    spec: object
    quellen: list[str]
    geschwindigkeit: float
    ziel: float | None
    zustand: object
    staende: list
    fluegel: list[Fluegelteil]
    unterboden: object = None           # Unterbodenergebnis
    unterboden_kennlinie: object = None
    unterboden_befunde: list = field(default_factory=list)
    bilanz: object = None
    bilanz_drs: object = None           # dieselbe Bilanz mit offenem DRS
    familientabelle: tuple = ((), ())
    wanderung: list = field(default_factory=list)
    mit_aero: bool = True
    hinweise: list[str] = field(default_factory=list)
    erstellt: str = field(
        default_factory=lambda: datetime.now().strftime("%d.%m.%Y %H:%M"))


def sammeln(spec, weitere=(), quellen=(), geschwindigkeit: float = 20.0,
            ziel: float | None = None, mit_aero: bool = True,
            melden: Callable[[str], None] | None = None) -> Reportdaten:
    """Rechnet alles, was in den Report kommt.

    Die Geometrie- und Rechenwege sind dieselben wie in der Oberflaeche -
    der Report darf keine Zahl zeigen, die man im Werkzeug anders sieht.
    """
    from .. import regeln
    from ..aero import drs, gesamt, kaskade as aero_kaskade, paket, unterboden
    from . import familientabelle
    from ..aero.profilpolare import verfuegbar
    from ..geometrie import endplatte as geo_endplatte
    from ..ui import app as ui

    melden = melden or (lambda text: None)
    mit_aero = bool(mit_aero and verfuegbar())
    p = paket.bauen(spec, list(weitere))
    bezug = regeln.Bezugsgeometrie.aus_datei()
    zustand = regeln.Fahrzustand()
    staende = regeln.alle_staende()

    teile = []
    for name, element in paket.fluegel_des_pakets(p):
        teil = Fluegelteil(name, element)
        teile.append(teil)
        if element.spannweite is None:
            teil.hinweise.append("Ohne Sektionstabelle: keine Spannweite, "
                                 "keine Regelprüfung, kein Abtrieb.")
            continue
        melden(f"Geometrie und Regeln: {name}")
        stapel_je = ui._elementstapel(element)
        stapel = [s for t in stapel_je for s in t]
        if element.endplatte is not None:
            stapel = stapel + geo_endplatte.schnitte(stapel_je, element.endplatte)
        for satz in staende:
            teil.befunde[satz.version] = regeln.pruefe_fluegel(
                stapel, satz, bezug, zustand)
        if drs.hat_drs(element):
            # Offen steht der Flap steiler oder flacher - Hoehe und Laenge
            # aendern sich, also muss auch dieser Zustand die Regeln halten.
            melden(f"Regeln mit offenem DRS: {name}")
            offen = drs.element_offen(element)
            je_offen = ui._elementstapel(offen)
            stapel_offen = [s for t in je_offen for s in t]
            if offen.endplatte is not None:
                stapel_offen += geo_endplatte.schnitte(je_offen, offen.endplatte)
            for satz in staende:
                teil.befunde[f"{satz.version} DRS offen"] = regeln.pruefe_fluegel(
                    stapel_offen, satz, bezug, zustand)
        teil.grundriss = _grundriss(stapel_je)
        teil.kaskade_wurzel = ui._schnittelemente(
            element, min(s.y for s in element.spannweite.stuetzstellen))
        teil.profile = [(ui.profil_fuer(element).name, ui.profil_fuer(element).punkte)]
        teil.profile += [(k.profil, ui.profil_aus_datei(k.profil).punkte)
                         for k in element.kaskade]

        if mit_aero:
            melden(f"Aerodynamik: {name}")
            teil.druck = aero_kaskade.druckverteilung(teil.kaskade_wurzel,
                                                      element.anstellwinkel)
            teil.kraefte = ui._fluegelkraefte(element, geschwindigkeit)
            if drs.hat_drs(element):
                teil.drs = drs.vergleich(element, ui._fluegelkraefte,
                                         geschwindigkeit, name)
            if element.pos_x < 0:
                # Nur vor der Vorderachse: Dort arbeitet der Fluegel im
                # Bodeneffekt. Ein Heckfluegel auf 900 mm hat keine
                # h/c-Abhaengigkeit, die sich zu zeigen lohnt.
                for hc in HC_STUFEN:
                    e = element.model_copy(update={"pos_z": hc * element.sehne})
                    teil.hc.append((hc, ui._fluegelkraefte(e, geschwindigkeit).abtrieb))

    daten = Reportdaten(spec=spec, quellen=list(quellen),
                        geschwindigkeit=float(geschwindigkeit), ziel=ziel,
                        zustand=zustand, staende=staende, fluegel=teile,
                        mit_aero=mit_aero)

    if p.unterboden is not None:
        melden("Unterboden")
        # Die Pruefung zuerst und immer: Gerade ein aufsetzender Boden muss
        # als Verstoss im Report stehen, statt ihn ganz zu verhindern.
        daten.unterboden_befunde = unterboden.pruefe(
            p.unterboden, p.lage, regeln.lade("2026"), zustand.tief)
        try:
            daten.unterboden = unterboden.rechne(p.unterboden, p.lage,
                                                 geschwindigkeit)
            daten.unterboden_kennlinie = unterboden.kennlinie(
                p.unterboden, p.lage, geschwindigkeit)
        except ValueError as fehler:
            daten.hinweise.append(f"Unterboden nicht gerechnet: {fehler}")

    if mit_aero and (teile or p.unterboden is not None):
        melden("Gesamtfahrzeug und Nickwanderung")
        daten.wanderung = gesamt.wanderung(
            paket.fluegel_des_pakets(p), p.unterboden, p.lage,
            ui._fluegelkraefte, geschwindigkeit, bezug.radstand)
        daten.bilanz = next(b for b in daten.wanderung
                            if b.zustand.nick_grad == 0.0)
        if any(t.drs is not None for t in teile):
            daten.bilanz_drs = gesamt.bilanz(
                [(n, drs.element_offen(e)) for n, e in paket.fluegel_des_pakets(p)],
                p.unterboden, p.lage, ui._fluegelkraefte, geschwindigkeit,
                bezug.radstand)
    daten.familientabelle = familientabelle.tabelle(p)
    return daten


def _grundriss(stapel_je) -> np.ndarray:
    """Vorder- und Hinterkante ueber y, je Schnitt: Spalten y, x_vorn, x_hinten.

    Ueber alle Elemente samt Flaps - der Grundriss ist, was von oben zu
    sehen ist. Endplatten bleiben draussen, sie haetten keine Flaeche.
    """
    je_y: dict[float, list[float]] = {}
    for teil in stapel_je:
        for schnitt in teil:
            y = round(float(schnitt.y), 1)
            x = schnitt.punkte[:, 0]
            alt = je_y.get(y, [math.inf, -math.inf])
            je_y[y] = [min(alt[0], float(x.min())), max(alt[1], float(x.max()))]
    return np.array([[y, v, h] for y, (v, h) in sorted(je_y.items())])


# ============================================================ Zeichnen

def _seite(pdf, titel: str, untertitel: str = ""):
    import matplotlib.pyplot as plt

    fig = plt.figure(figsize=A4)
    fig.text(0.07, 0.955, titel, fontsize=15, fontweight="bold")
    if untertitel:
        fig.text(0.07, 0.935, untertitel, fontsize=9, color=GRAU)
    fig.add_artist(plt.Line2D([0.07, 0.93], [0.928, 0.928], color="#cf2027",
                              linewidth=1.5))
    return fig


def _fuss(fig, daten: Reportdaten, nr: int):
    fig.text(0.07, 0.025, f"Aero Studio — {daten.spec.meta.name} — Spec "
             f"{daten.spec.hash()[:12]} — {daten.erstellt}", fontsize=7, color=GRAU)
    fig.text(0.93, 0.025, f"Seite {nr}", fontsize=7, color=GRAU, ha="right")


def _tabelle(ax, kopf, zeilen, breiten=None, schrift=7.5, farben=None):
    ax.axis("off")
    if not zeilen:
        ax.text(0.0, 1.0, "—", va="top", fontsize=schrift)
        return
    t = ax.table(cellText=zeilen, colLabels=kopf or None, loc="upper left",
                 cellLoc="left", colLoc="left", colWidths=breiten)
    t.auto_set_font_size(False)
    t.set_fontsize(schrift)
    t.scale(1.0, 1.25)
    zellen = t.get_celld()
    # Mehrzeiliger Text braucht hoehere Zeilen - sonst schreiben sich die
    # Zeilen gegenseitig ueber.
    versatz = 1 if kopf else 0
    for r, zeile in enumerate(zeilen, start=versatz):
        linien = max(str(z).count("\n") + 1 for z in zeile)
        if linien > 1:
            for c in range(len(zeile)):
                zellen[r, c].set_height(zellen[r, c].get_height() * linien)
    for (r, c), zelle in zellen.items():
        zelle.set_edgecolor("#d9dce1")
        zelle.set_text_props(verticalalignment="center")
        if r == 0 and kopf:
            zelle.set_facecolor("#eef0f3")
            zelle.set_text_props(fontweight="bold")
        elif farben and farben[r - (1 if kopf else 0)]:
            zelle.set_facecolor(farben[r - (1 if kopf else 0)])


def _urteil(befunde) -> str:
    harte = [b for b in befunde if b.blockiert]
    weich = [b for b in befunde if not b.ok and not b.blockiert]
    if harte:
        return f"{len(harte)} Verstoß" + ("e" if len(harte) > 1 else "")
    if weich:
        return f"regelkonform, {len(weich)} Hinweis" + ("e" if len(weich) > 1 else "")
    return "regelkonform"


def _deckblatt(pdf, daten: Reportdaten, nr: int):
    import matplotlib.pyplot as plt

    s = daten.spec
    fig = plt.figure(figsize=A4)
    fig.patch.set_facecolor("white")
    fig.text(0.07, 0.86, "Aerodynamik — Auslegungsnachweis", fontsize=22,
             fontweight="bold")
    fig.text(0.07, 0.83, s.meta.name, fontsize=14, color="#cf2027")
    fig.add_artist(plt.Line2D([0.07, 0.93], [0.815, 0.815], color="#cf2027",
                              linewidth=2))
    meta = [["Fahrzeug", s.meta.fahrzeug],
            ["Entwurf (Spec-Hash)", s.hash()],
            ["Quellen", ", ".join(daten.quellen) or "—"],
            ["Bearbeiter", s.meta.bearbeiter or "—"],
            ["Erstellt", daten.erstellt],
            ["Fahrzustand der Regelprüfung",
             f"+{daten.zustand.hoch:.1f} / −{daten.zustand.tief:.1f} mm "
             f"({daten.zustand.quelle})"],
            ["Geschwindigkeit der Rechnung", f"{daten.geschwindigkeit:.0f} m/s"]]
    _tabelle(fig.add_axes([0.07, 0.62, 0.86, 0.17]), None, meta,
             [0.34, 0.66], schrift=8.5)

    fig.text(0.07, 0.585, "Regelkonformität", fontsize=12, fontweight="bold")
    zeilen, farben = [], []
    for teil in daten.fluegel:
        for stand, befunde in teil.befunde.items():
            u = _urteil(befunde)
            # Keep-out-Pruefungen sind ja/nein (Grenze 0) - ihre "Reserve"
            # von 0 mm waere immer die kleinste und saegte nichts.
            mass = [b.reserve for b in befunde if abs(b.grenze) > 1e-9]
            zeilen.append([teil.name, stand, u,
                           f"{min(mass):+.1f} mm" if mass else "—"])
            farben.append("#fde8e8" if "Verstoß" in u else None)
    for b in daten.unterboden_befunde:
        zeilen.append(["Unterboden", "2026",
                       ("ok: " if b.ok else "VERSTOSS: ") + b.text,
                       f"{b.ist - b.grenze:+.1f} mm"])
        farben.append(None if b.ok else "#fde8e8")
    _tabelle(fig.add_axes([0.07, 0.40, 0.86, 0.17]),
             ["Teil", "Regelstand", "Urteil", "Maßreserve"], zeilen,
             [0.27, 0.12, 0.43, 0.18], schrift=8, farben=farben)

    fig.text(0.07, 0.365, "Kennzahlen", fontsize=12, fontweight="bold")
    if daten.bilanz is not None:
        b = daten.bilanz
        zeilen = [[t.name, f"{t.abtrieb:.0f}",
                   f"{t.widerstand:.1f}" if math.isfinite(t.widerstand) else "—",
                   f"{t.abtrieb / t.widerstand:.1f}"
                   if t.widerstand and math.isfinite(t.widerstand) else "—",
                   f"{t.x:.0f}"] for t in b.beitraege]
        zeilen.append(["Gesamt", f"{b.abtrieb:.0f}", f"{b.widerstand:.1f}",
                       f"{b.wirkungsgrad:.1f}", f"{b.druckpunkt_x:.0f}"])
        _tabelle(fig.add_axes([0.07, 0.25, 0.86, 0.1]),
                 ["Teil", "Abtrieb [N]", "Widerstand [N]", "L/D", "x Angriff [mm]"],
                 zeilen, [0.36, 0.16, 0.18, 0.12, 0.18], schrift=8.5)
        text = (f"Balance {100 * b.balance_vorne:.1f} % auf der Vorderachse")
        if daten.ziel is not None:
            text += f" (Ziel {daten.ziel:.0f} %)"
        if daten.wanderung:
            from ..aero import gesamt
            text += (f", Wanderung {gesamt.empfindlichkeit(daten.wanderung):+.1f} "
                     f"Prozentpunkte je Grad Nicken")
        fig.text(0.07, 0.235, text + ".", fontsize=9)
    else:
        fig.text(0.07, 0.34, "Ohne NeuralFoil gerechnet — keine Kraefte.",
                 fontsize=9, color=GRAU)
    fig.text(0.07, 0.09, "Alle Kräfte aus Aero Studio (Traglinie mit Kaskaden-"
             "polaren, Kanalmodell für den Unterboden), nicht mit CFD oder "
             "Messung abgeglichen.\nVergleiche zwischen Entwürfen sind "
             "belastbar, absolute Werte erst nach dem Abgleich. Details auf "
             "der letzten Seite.", fontsize=7.5, color=GRAU)
    _fuss(fig, daten, nr)
    pdf.savefig(fig)
    plt.close(fig)


def _regelseiten(pdf, daten: Reportdaten, nr: int) -> int:
    import matplotlib.pyplot as plt

    zeilen, farben = [], []
    for teil in daten.fluegel:
        for stand, befunde in teil.befunde.items():
            zeilen.append(["", f"{teil.name} — Regelstand {stand}: "
                               f"{_urteil(befunde)}", "", "", "", "", ""])
            farben.append("#e3e6ea")
            for b in befunde:
                pfeil = "≤" if b.richtung == "max" else "≥"
                zeilen.append([b.regel, b.pruefung[:58], f"{pfeil} {b.grenze:.1f}",
                               f"{b.ist:.1f}", f"{b.reserve:+.1f}",
                               b.fahrzustand.replace(" mm", ""),
                               "ok" if b.ok else ("VERSTOSS" if b.blockiert
                                                  else "Hinweis")])
                farben.append(None if b.ok else
                              ("#fde8e8" if b.blockiert else "#fff4e0"))
    je_seite = 38
    for start in range(0, max(len(zeilen), 1), je_seite):
        fig = _seite(pdf, "Regelkonformität",
                     "Jede Prüfung in der Lage, in der sie kritisch wird. "
                     "Einheiten mm, außer wo die Regel anderes nennt.")
        _tabelle(fig.add_axes([0.04, 0.06, 0.92, 0.85]),
                 ["Regel", "Prüfung", "Soll", "Ist", "Reserve",
                  "Fahrzustand [mm]", "Urteil"],
                 zeilen[start:start + je_seite],
                 [0.08, 0.44, 0.09, 0.08, 0.08, 0.15, 0.08],
                 schrift=6.5, farben=farben[start:start + je_seite])
        _fuss(fig, daten, nr)
        pdf.savefig(fig)
        plt.close(fig)
        nr += 1
    return nr


def _geometrieseite(pdf, daten: Reportdaten, teil: Fluegelteil, nr: int):
    import matplotlib.pyplot as plt

    fig = _seite(pdf, f"Geometrie — {teil.name}",
                 f"Sehne {teil.element.sehne:.0f} mm, Anstellwinkel "
                 f"{teil.element.anstellwinkel:+.1f}°, tiefster Punkt "
                 f"{teil.element.pos_z:.0f} mm über Grund")

    ax = fig.add_axes([0.1, 0.63, 0.83, 0.26])
    for i, e in enumerate(teil.kaskade_wurzel):
        ax.fill(e.punkte[:, 0], e.punkte[:, 1], color=FARBEN[i % len(FARBEN)],
                alpha=0.85, label=f"{e.name or 'Hauptelement'} "
                                  f"({e.winkel:+.1f}°)")
    unten = min(float(e.punkte[:, 1].min()) for e in teil.kaskade_wurzel) \
        if teil.kaskade_wurzel else 0.0
    if unten < 1.5 * teil.element.sehne:
        # Nur in Bodennaehe: Bei einem Heckfluegel auf 900 mm staucht die
        # Strasse das Bild auf Briefmarkengroesse.
        ax.axhline(0.0, color="#8a8f98", linewidth=1)
    ax.set_aspect("equal")
    ax.set_title("Kaskade im Wurzelschnitt (x nach hinten, z über Grund)",
                 fontsize=9, loc="left")
    ax.legend(fontsize=7, loc="lower left", bbox_to_anchor=(0.0, 1.06),
              ncol=3, frameon=False)
    ax.tick_params(labelsize=7)
    ax.set_xlabel("x [mm]", fontsize=8)
    ax.set_ylabel("z [mm]", fontsize=8)

    ax = fig.add_axes([0.1, 0.38, 0.83, 0.18])
    for i, (name, punkte) in enumerate(teil.profile):
        ax.plot(punkte[:, 0], punkte[:, 1], color=FARBEN[i % len(FARBEN)],
                linewidth=1.3, label=str(name))
    ax.set_aspect("equal")
    ax.set_title("Profilvergleich, auf die Sehne bezogen (für Abtrieb gespiegelt)",
                 fontsize=9, loc="left")
    ax.legend(fontsize=7)
    ax.tick_params(labelsize=7)

    ax = fig.add_axes([0.1, 0.07, 0.83, 0.24])
    if teil.grundriss is not None and len(teil.grundriss):
        y, vorn, hinten = teil.grundriss.T
        for vz, alpha in ((1.0, 0.85), (-1.0, 0.3)):
            ax.fill(np.concatenate([y, y[::-1]]) * vz,
                    np.concatenate([vorn, hinten[::-1]]),
                    color=FARBEN[0], alpha=alpha, linewidth=0)
        ax.axvline(0.0, color="#8a8f98", linewidth=0.8, linestyle="--")
        ax.invert_yaxis()
        ax.set_aspect("equal")
    ax.set_title("Grundriss (Draufsicht, Fahrtrichtung nach oben; gespiegelte "
                 "Seite hell)", fontsize=9, loc="left")
    ax.set_xlabel("y [mm]", fontsize=8)
    ax.set_ylabel("x [mm]", fontsize=8)
    ax.tick_params(labelsize=7)
    _fuss(fig, daten, nr)
    pdf.savefig(fig)
    plt.close(fig)


def _aeroseite(pdf, daten: Reportdaten, teil: Fluegelteil, nr: int):
    import matplotlib.pyplot as plt

    k = teil.kraefte
    unter = (f"{k.abtrieb:.0f} N Abtrieb, {k.widerstand:.1f} N Widerstand bei "
             f"{daten.geschwindigkeit:.0f} m/s, beide Seiten" if k is not None else "")
    fig = _seite(pdf, f"Aerodynamik — {teil.name}", unter)

    ax = fig.add_axes([0.1, 0.64, 0.83, 0.25])
    for i, d in enumerate(teil.druck):
        oben = d.saugseite
        ax.plot(d.x_rel[oben], d.cp[oben], color=FARBEN[i % len(FARBEN)],
                linewidth=1.4, label=f"{d.name or 'Hauptelement'} Saugseite")
        ax.plot(d.x_rel[~oben], d.cp[~oben], color=FARBEN[i % len(FARBEN)],
                linewidth=1.0, linestyle="--")
    if teil.druck:
        # Die Nasensingularitaet (siehe aero/kaskade.py) wuerde die Achse
        # auf das Zehnfache strecken - geschnitten wird bei der Saugspitze
        # ohne Nase, die Kurve selbst bleibt ungeglaettet.
        tief = min(d.saugspitze for d in teil.druck)
        hoch = max(float(d.cp.max()) for d in teil.druck)
        ax.set_ylim(tief - 0.25 * abs(tief) - 0.2, hoch + 0.3)
    ax.invert_yaxis()
    ax.set_title("Druckverteilung im Wurzelschnitt, reibungsfrei (Panelverfahren; "
                 "Nasenspitze abgeschnitten)",
                 fontsize=9, loc="left")
    ax.set_xlabel("x/c des Elements", fontsize=8)
    ax.set_ylabel("cp (Sog oben)", fontsize=8)
    ax.legend(fontsize=7)
    ax.tick_params(labelsize=7)

    ax = fig.add_axes([0.1, 0.36, 0.83, 0.2])
    if k is not None and len(getattr(k, "auftrieb_lokal", [])):
        y = np.array([s.y for s in k.streifen])
        b = np.array([s.breite for s in k.streifen]) / 1000.0
        last = -np.asarray(k.auftrieb_lokal) / b
        ordnung = np.argsort(y)
        ax.plot(y[ordnung], last[ordnung], color=FARBEN[1], linewidth=1.5)
        ax.fill_between(y[ordnung], 0, last[ordnung], color=FARBEN[1], alpha=0.15)
    ax.set_title("Abtrieb über die Spannweite (Traglinie)", fontsize=9, loc="left")
    ax.set_xlabel("y [mm]", fontsize=8)
    ax.set_ylabel("Abtrieb [N/m]", fontsize=8)
    ax.tick_params(labelsize=7)

    ax = fig.add_axes([0.1, 0.07, 0.83, 0.2])
    if teil.hc:
        hc, f = zip(*teil.hc)
        ax.plot(hc, f, "o-", color=FARBEN[0], linewidth=1.5, markersize=4)
        aktuell = teil.element.pos_z / teil.element.sehne
        ax.axvline(aktuell, color="#cf2027", linestyle="--", linewidth=1)
        ax.text(aktuell, max(f), f"  Entwurf h/c = {aktuell:.2f}", fontsize=7,
                color="#cf2027", va="top")
        ax.set_title("Bodenabstand: Abtrieb über h/c (h = tiefster Punkt, "
                     "c = Sehne Hauptelement)", fontsize=9, loc="left")
        ax.set_xlabel("h/c", fontsize=8)
        ax.set_ylabel("Abtrieb [N]", fontsize=8)
    else:
        ax.axis("off")
        ax.text(0, 0.5, "Kein h/c-Verlauf: Der Flügel liegt hinter der "
                "Vorderachse und arbeitet nicht im Bodeneffekt.",
                fontsize=8, color=GRAU)
    ax.tick_params(labelsize=7)
    _fuss(fig, daten, nr)
    pdf.savefig(fig)
    plt.close(fig)


def _unterbodenseite(pdf, daten: Reportdaten, nr: int):
    import matplotlib.pyplot as plt

    e, k = daten.unterboden, daten.unterboden_kennlinie
    fig = _seite(pdf, "Unterboden",
                 f"{e.abtrieb:.0f} N Abtrieb, {e.widerstand:.1f} N Widerstand, "
                 f"Druckpunkt {e.druckpunkt_x:.0f} mm, Diffusor wirksam "
                 f"{e.diffusor_winkel_wirksam:.1f}°, Stabilität {k.stabilitaet:.2f}")
    ax = fig.add_axes([0.1, 0.66, 0.83, 0.22])
    ax.fill_between(e.x, e.hoehe, e.hoehe.max() * 1.3, color=FARBEN[0], alpha=0.8)
    ax.axhline(0, color="#8a8f98")
    ax.set_title("Längsschnitt (Höhe überhöht)", fontsize=9, loc="left")
    ax.set_xlabel("x ab Vorderachse [mm]", fontsize=8)
    ax.set_ylabel("Höhe [mm]", fontsize=8)
    ax.tick_params(labelsize=7)

    ax = fig.add_axes([0.1, 0.37, 0.83, 0.2])
    ax.plot(e.x, e.cp, color=FARBEN[4], linewidth=1.5)
    ax.axvline(e.druckpunkt_x, color="#cf2027", linestyle="--", linewidth=1)
    ax.invert_yaxis()
    ax.set_title("Druck entlang des Bodens (Kanalmodell)", fontsize=9, loc="left")
    ax.set_xlabel("x [mm]", fontsize=8)
    ax.set_ylabel("cp (Sog oben)", fontsize=8)
    ax.tick_params(labelsize=7)

    ax = fig.add_axes([0.1, 0.08, 0.83, 0.2])
    ax.plot(k.hub, k.abtrieb, "o-", color=FARBEN[0], markersize=4)
    ax.set_title("Abtrieb über den Hub", fontsize=9, loc="left")
    ax.set_xlabel("Hub [mm], negativ = eingefedert", fontsize=8)
    ax.set_ylabel("Abtrieb [N]", fontsize=8)
    ax.tick_params(labelsize=7)
    _fuss(fig, daten, nr)
    pdf.savefig(fig)
    plt.close(fig)


def _gesamtseite(pdf, daten: Reportdaten, nr: int):
    import matplotlib.pyplot as plt

    from ..aero import gesamt

    b = daten.bilanz
    fig = _seite(pdf, "Gesamtfahrzeug und Balance",
                 f"{b.abtrieb:.0f} N, Balance {100 * b.balance_vorne:.1f} % vorn, "
                 f"Achslast {b.last_vorne:.0f} / {b.last_hinten:.0f} N")
    ax = fig.add_axes([0.1, 0.55, 0.83, 0.32])
    for i, t in enumerate(b.beitraege):
        ax.bar(t.x, t.abtrieb, width=max(60.0, 0.05 * b.radstand),
               color=FARBEN[i % len(FARBEN)], label=f"{t.name}: {t.abtrieb:.0f} N")
    for x, text in ((0.0, "VA"), (b.radstand, "HA")):
        ax.axvline(x, color="#8a8f98", linewidth=1.5)
        ax.text(x, ax.get_ylim()[1], text, ha="center", va="bottom", fontsize=8)
    if math.isfinite(b.druckpunkt_x):
        ax.axvline(b.druckpunkt_x, color="#cf2027", linestyle="--",
                   label=f"Druckpunkt {b.druckpunkt_x:.0f} mm")
    if daten.ziel is not None:
        ax.axvline(b.druckpunkt_fuer(daten.ziel), color="#2e7d32",
                   linestyle=":", label=f"Ziel {daten.ziel:.0f} % vorn")
    ax.set_title("Abtrieb je Teil an seinem Angriffspunkt", fontsize=9, loc="left")
    ax.set_xlabel("x ab Vorderachse [mm]", fontsize=8)
    ax.set_ylabel("Abtrieb [N]", fontsize=8)
    ax.legend(fontsize=7)
    ax.tick_params(labelsize=7)

    ax = fig.add_axes([0.1, 0.12, 0.83, 0.3])
    if daten.wanderung:
        n = [w.zustand.nick_grad for w in daten.wanderung]
        v = [100 * w.balance_vorne for w in daten.wanderung]
        ax.plot(n, v, "o-", color=FARBEN[0])
        if daten.ziel is not None:
            ax.axhline(daten.ziel, color="#2e7d32", linestyle=":")
        ax.set_title(f"Nickwanderung: {gesamt.empfindlichkeit(daten.wanderung):+.1f} "
                     f"Prozentpunkte je Grad", fontsize=9, loc="left")
    ax.set_xlabel("Nicken [°], positiv = Nase tiefer (Bremsen)", fontsize=8)
    ax.set_ylabel("Balance vorn [%]", fontsize=8)
    ax.tick_params(labelsize=7)
    fig.text(0.1, 0.05, "Teile einzeln gerechnet und addiert — ohne Räder, "
             "Karosserie und Wechselwirkungen (Nachlauf des Frontflügels auf dem "
             "Unterboden).", fontsize=7.5, color=GRAU)
    _fuss(fig, daten, nr)
    pdf.savefig(fig)
    plt.close(fig)


def _drsseite(pdf, daten: Reportdaten, nr: int):
    import matplotlib.pyplot as plt

    fig = _seite(pdf, "DRS — verstellbarer Flap",
                 "Zwei Zustände desselben Entwurfs: zu (Kurve) und offen (Gerade)")
    fig.text(0.07, 0.9, "Kräfte je Flügel", fontsize=11, fontweight="bold")
    zeilen = [[t.drs.name, f"{t.drs.zu_abtrieb:.0f}", f"{t.drs.auf_abtrieb:.0f}",
               f"−{100 * t.drs.abtrieb_verlust:.0f} %",
               f"{t.drs.zu_widerstand:.1f}", f"{t.drs.auf_widerstand:.1f}",
               f"−{100 * t.drs.widerstand_gewinn:.0f} %"]
              for t in daten.fluegel if t.drs is not None]
    _tabelle(fig.add_axes([0.07, 0.78, 0.86, 0.1]),
             ["Flügel", "Abtrieb zu", "Abtrieb offen", "Δ", "Widerst. zu",
              "Widerst. offen", "Δ"], zeilen,
             [0.28, 0.12, 0.13, 0.09, 0.13, 0.15, 0.1], schrift=8)
    if daten.bilanz is not None and daten.bilanz_drs is not None:
        zu, auf = daten.bilanz, daten.bilanz_drs
        fig.text(0.07, 0.72, "Gesamtfahrzeug", fontsize=11, fontweight="bold")
        _tabelle(fig.add_axes([0.07, 0.62, 0.86, 0.08]),
                 ["", "Abtrieb [N]", "Widerstand [N]", "Balance vorn"],
                 [["DRS zu", f"{zu.abtrieb:.0f}", f"{zu.widerstand:.1f}",
                   f"{100 * zu.balance_vorne:.1f} %"],
                  ["DRS offen", f"{auf.abtrieb:.0f}", f"{auf.widerstand:.1f}",
                   f"{100 * auf.balance_vorne:.1f} %"]],
                 [0.25, 0.25, 0.25, 0.25], schrift=8.5)
        sprung = 100 * (zu.balance_vorne - auf.balance_vorne)
        fig.text(0.07, 0.585, f"Beim Schließen am Kurveneingang wandert die "
                 f"Balance um {abs(sprung):.1f} Prozentpunkte nach "
                 f"{'vorn' if sprung > 0 else 'hinten'}.", fontsize=9)
    kopf, zeilen = daten.familientabelle
    if zeilen:
        fig.text(0.07, 0.52, "Familientabelle für Creo", fontsize=11,
                 fontweight="bold")
        _tabelle(fig.add_axes([0.07, 0.42, 0.86, 0.08]), list(kopf),
                 [[z[0], *(f"{w:+.1f}" for w in z[1:])] for z in zeilen],
                 schrift=8.5)
    fig.text(0.07, 0.36, _umbruch(
        "Der offene Flap ist wie jeder Flap über Spalt und Überlappung "
        "angeordnet. Ein echtes DRS dreht um ein Scharnier; dessen Kinematik "
        "und die Kollisionsprüfung gehören nach Creo. Die Regelprüfung des "
        "offenen Zustands steht auf den Regelseiten (\u201eDRS offen\u201c).",
        120), fontsize=8, color=GRAU, va="top")
    _fuss(fig, daten, nr)
    pdf.savefig(fig)
    plt.close(fig)


GRENZEN = [
    ("Kräfte", "Traglinie mit Profil- bzw. Kaskadenpolaren (NeuralFoil, "
               "Panelverfahren), Bodeneffekt über Spiegelung und Kanalfaktor. "
               "Nicht mit CFD oder Messung abgeglichen: Vergleiche tragen, "
               "absolute Newton erst nach dem Abgleich."),
    ("Kaskadenabriss", "Druckrückgewinn-Kriterium mit unkalibrierter "
                       "Grenzschichtreserve."),
    ("Widerstand", "Induziert aus der Traglinie, Profilwiderstand aus den "
                   "Polaren. Räder und Karosserie fehlen - der Gesamtwiderstand "
                   "des Autos liegt deutlich höher."),
    ("Unterboden", "1D-Kanalmodell. Abdichtung (keine Schürzen nach T 2.2.2) "
                   "und Ablösegrenze 15–25° geschätzt."),
    ("Gesamtfahrzeug", "Teile addiert, keine Wechselwirkung; Räder, Karosserie, "
                       "Fahrer fehlen."),
    ("Regelprüfung", "Gegen die Punktwolke der Schnitte samt Endplatten, im "
                     "Fahrzustand-Envelope. Bezugsmaße aus vehicle_ref.yaml."),
]

OFFEN = [
    ("T 3.20.2 / T 3.19.4", "Frontflügelanbindung hinter der AIP und 120-kN-"
                            "Rechnung: braucht Schraubenbild und Strebenknicklast "
                            "— nicht im Spec. Getrennt nachzuweisen."),
    ("T 8.3", "Steifigkeit (200 N auf 225 cm² ≤ 10 mm; 50 N ≤ 25 mm): braucht "
              "Laminat und Anbindung — FEM oder Versuch."),
    ("Fertigung", "Rippen- und Schablonen-DXF entstehen im Reiter Creo "
                  "(formate/dxf.py); Formtrennebenen sind noch nicht abgeleitet."),
]


def _grenzenseite(pdf, daten: Reportdaten, nr: int):
    import matplotlib.pyplot as plt

    fig = _seite(pdf, "Annahmen, Grenzen, offene Nachweise")
    fig.text(0.07, 0.9, "Modellgrenzen", fontsize=11, fontweight="bold")
    _tabelle(fig.add_axes([0.07, 0.56, 0.86, 0.32]), ["Thema", "Grenze"],
             [[a, _umbruch(b, 95)] for a, b in GRENZEN], [0.2, 0.8], schrift=7.5)
    fig.text(0.07, 0.5, "Nicht in diesem Report nachgewiesen", fontsize=11,
             fontweight="bold")
    _tabelle(fig.add_axes([0.07, 0.3, 0.86, 0.18]), ["Regel", "Stand"],
             [[a, _umbruch(b, 95)] for a, b in OFFEN], [0.2, 0.8], schrift=7.5,
             farben=["#fff4e0"] * len(OFFEN))
    zeilen = [f"{t.name}: {h}" for t in daten.fluegel for h in t.hinweise]
    zeilen += daten.hinweise
    if zeilen:
        fig.text(0.07, 0.25, "Hinweise zu diesem Entwurf", fontsize=11,
                 fontweight="bold")
        fig.text(0.07, 0.23, "\n".join(_umbruch(z, 120) for z in zeilen),
                 fontsize=8, color=GRAU, va="top", linespacing=1.5)
    _fuss(fig, daten, nr)
    pdf.savefig(fig)
    plt.close(fig)


def _umbruch(text: str, breite: int) -> str:
    import textwrap
    return "\n".join(textwrap.wrap(text, breite))


def schreiben(daten: Reportdaten, pfad: str | Path) -> Path:
    """Schreibt den Report als PDF."""
    import matplotlib
    matplotlib.use("Agg")
    from matplotlib.backends.backend_pdf import PdfPages

    pfad = Path(pfad)
    pfad.parent.mkdir(parents=True, exist_ok=True)
    with PdfPages(pfad) as pdf:
        nr = 1
        _deckblatt(pdf, daten, nr)
        nr = _regelseiten(pdf, daten, nr + 1)
        for teil in daten.fluegel:
            if teil.grundriss is None:
                continue
            _geometrieseite(pdf, daten, teil, nr)
            nr += 1
            if daten.mit_aero:
                _aeroseite(pdf, daten, teil, nr)
                nr += 1
        if daten.unterboden is not None:
            _unterbodenseite(pdf, daten, nr)
            nr += 1
        if daten.bilanz is not None:
            _gesamtseite(pdf, daten, nr)
            nr += 1
        if any(t.drs is not None for t in daten.fluegel):
            _drsseite(pdf, daten, nr)
            nr += 1
        _grenzenseite(pdf, daten, nr)
        info = pdf.infodict()
        info["Title"] = f"Aerodynamik — {daten.spec.meta.name}"
        info["Subject"] = f"Spec {daten.spec.hash()}"
        info["Creator"] = "Aero Studio"
    return pfad


# ======================================================= Kommandozeile

def main(argv: list[str] | None = None) -> int:
    import argparse

    from ..spec.projekt import AeroSpec

    teil = argparse.ArgumentParser(
        prog="python -m aerostudio.formate.report",
        description="Schreibt den Auslegungsnachweis als PDF: Regelkonformität, "
                    "Geometrie, Aerodynamik, Unterboden, Balance.")
    teil.add_argument("--spec", required=True)
    teil.add_argument("--dazu", nargs="*", default=[],
                      help="weitere Specs, etwa der Heckflügel")
    teil.add_argument("--tempo", type=float, default=20.0)
    teil.add_argument("--ziel", type=float, default=None,
                      help="Zielbalance vorn in Prozent")
    teil.add_argument("--aus", default=None, help="PDF-Datei")
    teil.add_argument("--ohne-aero", action="store_true",
                      help="nur Geometrie und Regeln, ohne Kräfte (schnell)")
    arg = teil.parse_args(argv)

    from ..aero.gesamt import zielbalance_aus_datei

    spec = AeroSpec.laden(arg.spec)
    weitere = [AeroSpec.laden(p) for p in arg.dazu]
    ziel = arg.ziel if arg.ziel is not None else zielbalance_aus_datei()
    daten = sammeln(spec, weitere, [arg.spec, *arg.dazu], arg.tempo, ziel,
                    not arg.ohne_aero, melden=lambda t: print(f"  {t}", flush=True))
    pfad = schreiben(daten, arg.aus or f"export/report_{Path(arg.spec).stem}.pdf")
    print(f"  Geschrieben: {pfad}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
