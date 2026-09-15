"""
Aero Studio - Oberflaeche.

Aufruf:
    python -m aerostudio.ui.app
oder per Doppelklick auf "Aero Studio.bat" im Projektordner.

Zwei Entwurfsentscheidungen, die den Aufbau erklaeren:

1. Alle drei Ansichten stehen dauerhaft im Layout und werden nur ein- und
   ausgeblendet. Wuerden sie beim Reiterwechsel neu aufgebaut, verloeren die
   Bedienelemente ihre Werte, und Callbacks, die auf sie zeigen, liefen ins
   Leere - beides ist beim ersten Versuch genau so passiert.

2. Der Bearbeitungsstand steckt in einem einzigen dcc.Store, nicht verteilt
   ueber die Bedienelemente. Die Wahrheit auf der Platte ist die YAML-Datei;
   Speichern ist ein bewusster Schritt.

Die Callbacks bleiben duenn - sie nehmen Eingaben entgegen, rufen eine Funktion
aus aerostudio.* auf und geben das Ergebnis zurueck. Fachlogik steht hier keine.
"""

from __future__ import annotations

import math
import traceback
import webbrowser
from pathlib import Path
from threading import Timer

from dash import (ALL, MATCH, Dash, Input, Output, State, callback_context,
                  dash_table,
                  dcc, html,
                  no_update)

from ..creo import starten as creo_starten
from ..formate import export, skelett
from .. import regeln
from ..aero import entwurf as aero_entwurf
from ..aero import kaskade as aero_kaskade
from ..aero import generator as aero_generator
from ..geometrie import kaskade as geo_kaskade
from ..aero.profilpolare import verfuegbar as aero_verfuegbar
from ..aero import traglinie
from ..geometrie import spannweite, verwindung
from ..geometrie.profil import (KATALOG, katalognotiz, katalogoptionen,
                                katalogprofile, profil_fuer)
from ..spec.modell import (Fertigung, Kaskadenstufe, ProfilAusDatei,
                           ProfilNaca, Spannweite, Stuetzstelle,
                           Wirkrichtung, vorgaben_fuer)
from ..spec.projekt import AeroSpec
from . import darstellung

PROJEKT = Path(__file__).resolve().parents[2]
SPEC_VORGABE = PROJEKT / "specs" / "aktuell.yaml"

FARBE_OK = "#2e7d32"
FARBE_HINWEIS = "#ef6c00"
FARBE_FEHLER = "#c62828"
FARBE_AKZENT = "#253494"


# ------------------------------------------------------------- Zahlenfeld

def wert(feld: str) -> dict:
    """Kennung eines Zahleneingabefelds.

    Als Wortverzeichnis, damit Minus, Plus und Eingabefeld desselben Feldes
    ueber MATCH zusammenfinden - sonst braeuchte jedes Feld eigene Callbacks.
    """
    return {"typ": "wert", "feld": feld}


# Schrittweite der Knoepfe je Feld. Bewusst NICHT im step-Attribut des
# Eingabefelds: Ein HTML-Zahlenfeld mit step="5" und min="10" erklaert alles
# ausser 10, 15, 20 ... fuer ungueltig - Kommazahlen erst recht. Mit
# step="any" laesst sich frei tippen, und die Knoepfe holen ihre Schrittweite
# von hier.
_SCHRITTE: dict[str, float] = {}

def _zahlenfeld(feld: str, vorgabe: float, schritt: float,
                minimum: float | None = None,
                maximum: float | None = None) -> html.Div:
    """Zahleneingabe mit eigenen Minus- und Plus-Schaltflaechen.

    Die Pfeilchen, die ein Browser bei einem Zahlenfeld von sich aus einblendet,
    sind winzig und verhalten sich je nach Browser anders. Eigene Schaltflaechen
    sind verlaesslich, gross genug und rechnen mit derselben Schrittweite, die
    auch die Tastatur benutzt.
    """
    _SCHRITTE[feld] = float(schritt)
    return html.Div([
        html.Button("−", id={"typ": "minus", "feld": feld}, n_clicks=0,
                    className="as-schritt", **{"aria-label": "verringern"}),
        dcc.Input(id=wert(feld), type="number", value=vorgabe, step="any",
                  min=minimum, max=maximum, debounce=False),
        html.Button("+", id={"typ": "plus", "feld": feld}, n_clicks=0,
                    className="as-schritt", **{"aria-label": "erhöhen"}),
    ], className="as-zahlenfeld")


# ------------------------------------------------------------------ Bausteine

def _feld(beschriftung: str, komponente, hinweis: str = "") -> html.Div:
    kinder = []
    if beschriftung:
        kinder.append(html.Label(beschriftung, className="as-beschriftung"))
    kinder.append(komponente)
    if hinweis:
        kinder.append(html.Div(hinweis, className="as-hinweis"))
    return html.Div(kinder, className="as-feld")


def _karte(kinder) -> html.Div:
    return html.Div(kinder, className="as-karte")


def _ueberschrift(text: str) -> html.H4:
    return html.H4(text)


def _logo():
    """Zeigt das Teamlogo, wenn eines im Assets-Ordner liegt.

    Erwartet logo.svg oder logo.png neben dieser Datei unter assets/. Fehlt es,
    bleibt nur die Wortmarke - ein Logo wird nicht erfunden.
    """
    ordner = Path(__file__).resolve().parent / "assets"
    for name in ("logo.svg", "logo.png", "logo.jpg"):
        if (ordner / name).is_file():
            return html.Img(src=f"/assets/{name}", className="as-logo",
                            alt="Rennschmiede Pforzheim")
    return None


_GRAPH = dict(config={"displaylogo": False, "displayModeBar": False})


# ------------------------------------------------------------------- Ansichten

def _leiste(titel: str, felder: list, spalten: str = "220px") -> html.Div:
    """Eine Karte, deren Felder NEBENEINANDER stehen statt untereinander.

    Der Grund ist praktisch: Standen die Regler in einer hohen Spalte links,
    lag die Haelfte davon unterhalb des sichtbaren Bereichs. Wer den
    Anstellwinkel aendern wollte, musste scrollen und sah dabei das Diagramm
    nicht mehr, das sich gerade aenderte. Nebeneinander passen dieselben
    Felder in zwei Zeilen und stehen gemeinsam mit der Zeichnung im Blick.

    auto-fit statt einer festen Spaltenzahl: Auf einem schmalen Bildschirm
    rutschen die Felder von selbst untereinander, statt zusammengequetscht
    zu werden.
    """
    return _karte([
        _ueberschrift(titel),
        html.Div(felder, className="as-leiste",
                 style={"gridTemplateColumns":
                        f"repeat(auto-fit, minmax({spalten}, 1fr))"}),
    ])


def _profilleiste() -> html.Div:
    return _leiste("Profil und Geometrie", [
        _feld("Name des Entwurfs", dcc.Input(
            id="entwurfsname", type="text", value="Frontfluegel Hauptelement",
            debounce=True, maxLength=60, className="as-textfeld"),
            "Steht im Dateinamen des Exports und im Kopf der IBL-Datei."),

        _feld("Quelle", dcc.RadioItems(
            id="quelle", value="datei",
            options=[{"label": " Katalog", "value": "datei"},
                     {"label": " NACA", "value": "naca"}],
            inline=True, style={"fontSize": "13px"}),
            "Fertiges Profil aus dem Katalog oder eines nach NACA-Formel."),

        html.Div(id="quelle-katalog", children=[
            _feld("Katalogprofil", dcc.Dropdown(
                id="katalogdatei", options=katalogoptionen(),
                value="e423.dat", clearable=False,
                style={"fontSize": "13px"}))]),

        html.Div(id="quelle-naca", children=[
            _feld("Wölbung [%]",
                  _zahlenfeld("naca-woelbung", 4.0, 0.5, -25.0, 25.0),
                  "Negativ wölbt nach unten. Über 9,5 % verlässt man die "
                  "Standard-NACA-Familie."),
            _feld("Wölbungslage [%]",
                  _zahlenfeld("naca-lage", 40.0, 5.0, 5.0, 95.0)),
            _feld("Dicke [%]", _zahlenfeld("naca-dicke", 12.0, 0.5, 1.0, 40.0)),
        ]),

        _feld("Wirkrichtung", dcc.RadioItems(
            id="wirkrichtung", value="abtrieb",
            options=[{"label": " Abtrieb", "value": "abtrieb"},
                     {"label": " Auftrieb (Bullwing)", "value": "auftrieb"}],
            style={"fontSize": "13px"}),
            "Katalogprofile sind für Auftrieb gezeichnet und werden für "
            "Abtrieb gespiegelt. Auftrieb wählt man für Bullwings."),

        _feld("Sehnenlänge [mm]", _zahlenfeld("sehne", 250.0, 5.0, 1.0, 5000.0),
              "Beliebige Zahl, auch mit Komma. Die Knöpfe springen in "
              "5-mm-Schritten."),

        _feld("Anstellwinkel [°]", _zahlenfeld("aoa", -4.0, 0.5, -60.0, 60.0),
              "Negativ = Nase nach unten."),
    ])


def _fertigungsleiste() -> html.Div:
    return _leiste("Fertigung", [
        _feld("Verfahren", dcc.Dropdown(
            id="verfahren", clearable=False, value="prepreg",
            options=["nasslaminat", "prepreg", "autoklav", "unbestimmt"],
            style={"fontSize": "13px"}),
            "Setzt die drei Werte daneben auf Startwerte. Änderst du sie, "
            "merkt sich das Werkzeug sie je Verfahren."),
        _feld("Wandstärke je Haut [mm]",
              _zahlenfeld("wandstaerke", 0.6, 0.1, 0.05, 20.0)),
        _feld("Kerndicke [mm]", _zahlenfeld("kern", 3.0, 0.5, 0.0, 100.0),
              "0 = keine. Der Kern kommt nur dorthin, wo er hineinpasst."),
        _feld("Klebespalt [mm]", _zahlenfeld("klebespalt", 0.2, 0.05, 0.0, 5.0),
              "Bestimmt zusammen mit der Wandstärke die gebaute Hinterkante."),
    ])


def _ansicht_profil() -> html.Div:
    return html.Div([
        _profilleiste(),
        html.Div([
            html.Div(_karte([dcc.Graph(id="fig-kontur", **_GRAPH)]),
                     style={"flex": "2 1 0", "minWidth": 0,
                            "marginRight": "14px"}),
            html.Div([_karte([html.Div(id="ampel")]),
                      html.Div(id="katalog-notiz")],
                     style={"flex": "1 1 0", "minWidth": "300px"}),
        ], className="as-zeile"),
        _fertigungsleiste(),
        html.Div([
            html.Div(_karte([dcc.Graph(id="fig-dicke", **_GRAPH)]),
                     style={"flex": 1, "marginRight": "14px", "minWidth": 0}),
            html.Div(_karte([dcc.Graph(id="fig-kruemmung", **_GRAPH)]),
                     style={"flex": 1, "minWidth": 0}),
        ], className="as-zeile"),
        _karte([dcc.Graph(id="fig-zonen", **_GRAPH)]),
    ])


SPALTEN = [
    {"id": "y", "name": "y [mm] ab Mitte", "type": "numeric"},
    {"id": "sehne", "name": "Sehne × Wurzel", "type": "numeric"},
    {"id": "verwindung", "name": "Eindrehen [°]", "type": "numeric"},
    {"id": "z", "name": "Höhenversatz [mm]", "type": "numeric"},
    {"id": "x", "name": "Längsversatz [mm]", "type": "numeric"},
]


def _tabellendaten(spannweite) -> list[dict]:
    return [{"y": round(st.y, 1), "sehne": round(st.sehne, 3),
             "verwindung": round(st.verwindung, 2), "z": round(st.z, 1),
             "x": round(st.x, 1)} for st in spannweite.stuetzstellen]


def _ansicht_fluegel() -> html.Div:
    return html.Div([
        _leiste("Flügel über die Spannweite", [
            _feld("Vorgabe", html.Div([
                dcc.Dropdown(
                    id="verteilung", clearable=False, value="frontfluegel",
                    options=[{"label": "Frontflügel außen (Outwash innen)",
                              "value": "frontfluegel"},
                             {"label": "Gerader Flügel ohne Verwindung",
                              "value": "gerade"}],
                    style={"fontSize": "13px"}),
                html.Button("Vorgabe in die Tabelle laden", id="btn-vorgabe",
                            n_clicks=0, className="as-knopf as-knopf-leer"),
            ]),
                "Setzt die Tabelle unten auf einen Startpunkt. Danach ist die "
                "Tabelle maßgeblich — die Vorgabe überschreibt sie erst beim "
                "nächsten Klick."),
            _feld("Halbspannweite der Vorgabe [mm]",
                  _zahlenfeld("halbspannweite", 600.0, 25.0, 50.0, 900.0),
                  "Nur beim Laden der Vorgabe wirksam. Der äußerste Punkt des "
                  "Vorderrads liegt bei 695 mm."),
            _feld("Schnitte für den Export",
                  _zahlenfeld("schnittzahl", 13.0, 2.0, 2.0, 101.0),
                  "Wieviele Profilschnitte zwischen den Sektionen berechnet "
                  "werden. Mehr bilden die Verwindung feiner ab, kosten in "
                  "Creo aber Regenerationszeit."),
            _feld("Nase vor der Vorderachse [mm]",
                  _zahlenfeld("pos-x", 600.0, 25.0, -2000.0, 2000.0),
                  "Positiv = vor der Achse."),
            _feld("Höhe über Boden [mm]",
                  _zahlenfeld("pos-z", 90.0, 5.0, 0.0, 1500.0),
                  "Höhe der Wurzelsehne."),
        ], spalten="240px"),

        _karte([
            _ueberschrift("Sektionen"),
            html.Div([
                "Jede Zeile ist eine Stützstelle über die Spannweite. Zwischen "
                "den Zeilen wird formerhaltend interpoliert, es entsteht also "
                "keine Sehne und kein Winkel, der größer wäre als beide "
                "Nachbarn. ",
                html.B("Eindrehen"), " wirkt additiv auf den Anstellwinkel aus "
                "dem Reiter Profil: −10° dort bedeutet zehn Grad weiter Nase "
                "nach unten als die Wurzel. ",
                html.B("Sehne"), " ist ein Faktor auf die Wurzelsehne.",
            ], className="as-hinweis", style={"marginBottom": "10px"}),
            dash_table.DataTable(
                id="stuetzstellen",
                columns=SPALTEN,
                data=_tabellendaten(Spannweite.frontfluegel_aussen()),
                editable=True, row_deletable=True,
                style_cell={"fontFamily": "Consolas, monospace",
                            "fontSize": "13px", "padding": "6px 10px",
                            "textAlign": "right"},
                style_header={"fontFamily": "Segoe UI, sans-serif",
                              "fontWeight": 600, "fontSize": "12px",
                              "textAlign": "right",
                              "backgroundColor": "#f4f5f7"},
                style_data_conditional=[
                    {"if": {"column_id": "verwindung"},
                     "backgroundColor": "#fffdf5"}],
            ),
            html.Div([
                html.Button("Sektion hinzufügen", id="btn-sektion", n_clicks=0,
                            className="as-knopf as-knopf-leer",
                            style={"width": "auto", "marginRight": "10px"}),
                html.Span("Zeilen lassen sich über das Kreuz rechts löschen.",
                          className="as-hinweis"),
            ], style={"marginTop": "10px", "display": "flex",
                      "alignItems": "center", "gap": "8px"}),
            html.Div(id="sektionen-meldung", style={"marginTop": "9px"}),
        ]),

        html.Div([
            html.Div(_karte([_ueberschrift("Verlauf über die Spannweite"),
                             dcc.Graph(id="fig-verteilung", **_GRAPH)]),
                     style={"flex": "1 1 0", "minWidth": 0,
                            "marginRight": "14px"}),
            html.Div(_karte([
                _ueberschrift("Flügel räumlich"),
                dcc.RadioItems(
                    id="ansicht3d", value="flaeche",
                    options=[{"label": " Ganzer Flügel", "value": "flaeche"},
                             {"label": " Nur Schnitte", "value": "schnitte"},
                             {"label": " Beides", "value": "beides"}],
                    inline=True,
                    style={"fontSize": "12.5px", "marginBottom": "8px"}),
                html.Div("Bei „Nur Schnitte“ und „Beides“ lässt sich "
                         "jeder Schnitt über die Legende einzeln ein- und "
                         "ausblenden. Die Farbe läuft von dunkelrot innen "
                         "nach gelb außen.", className="as-hinweis",
                         style={"marginBottom": "8px"}),
                dcc.Graph(id="fig-fluegel3d", **_GRAPH)]),
                     style={"flex": "1 1 0", "minWidth": 0}),
        ], className="as-zeile"),

        _karte([
            _ueberschrift("Abtrieb — Abschätzung"),
            html.Div([
                _feld("Geschwindigkeit [m/s]",
                      _zahlenfeld("tempo", 15.0, 1.0, 3.0, 45.0),
                      "15 m/s sind 54 km/h — etwa das Mittel einer "
                      "Autocross-Runde."),
                html.Div([
                    html.Button("Abtrieb rechnen", id="btn-aero", n_clicks=0,
                                className="as-knopf as-knopf-voll"),
                    html.Div("Dauert ein paar Sekunden.", className="as-hinweis",
                             style={"marginTop": "6px"}),
                ]),
            ], className="as-leiste",
                style={"gridTemplateColumns": "240px 240px",
                       "marginBottom": "14px"}),
            dcc.Loading(html.Div(id="aero-ergebnis"), type="dot"),
        ]),

        _karte([
            _ueberschrift("Flügel zu einem Zielabtrieb vorschlagen"),
            html.Div("Die Verwindung aus der Tabelle oben bleibt erhalten — "
                     "gesucht werden Wurzelsehne, Halbspannweite, "
                     "Anstellwinkel und Einbauhöhe. Unter allem, was das Ziel "
                     "trifft und das Reglement einhält, gewinnt der beste "
                     "Wirkungsgrad.", className="as-hinweis",
                     style={"marginBottom": "12px"}),
            html.Div([
                _feld("Zielabtrieb [N]",
                      _zahlenfeld("zielabtrieb", 60.0, 5.0, 1.0, 2000.0),
                      "Für den Flügel allein, bei der Geschwindigkeit darüber."),
                _feld("Sehne von … bis [mm]", html.Div([
                    _zahlenfeld("sehne-min", 120.0, 10.0, 30.0, 1000.0),
                    html.Div(style={"height": "6px"}),
                    _zahlenfeld("sehne-max", 400.0, 10.0, 30.0, 1000.0),
                ])),
                _feld("Halbspannweite von … bis [mm]", html.Div([
                    _zahlenfeld("weite-min", 300.0, 25.0, 50.0, 900.0),
                    html.Div(style={"height": "6px"}),
                    _zahlenfeld("weite-max", 695.0, 25.0, 50.0, 900.0),
                ]), "695 mm ist die Außenkante des Vorderrads."),
                _feld("Steilster Anstellwinkel [°]",
                      _zahlenfeld("winkel-min", -16.0, 1.0, -40.0, 0.0),
                      "Grenze für die Suche. Der Abriss begrenzt zusätzlich."),
                html.Div([
                    html.Button("Flügel vorschlagen", id="btn-vorschlag",
                                n_clicks=0, className="as-knopf as-knopf-voll"),
                    html.Div("Rechnet einige hundert Varianten durch, "
                             "etwa zehn Sekunden.", className="as-hinweis",
                             style={"marginTop": "6px"}),
                ]),
            ], className="as-leiste",
                style={"gridTemplateColumns": "repeat(auto-fit, minmax(210px, 1fr))",
                       "marginBottom": "14px"}),
            dcc.Loading(html.Div(id="vorschlag-ergebnis"), type="dot"),
        ]),
    ])


KASKADENSPALTEN = [
    {"id": "profil", "name": "Profil", "presentation": "dropdown"},
    {"id": "sehne", "name": "Sehne × Hauptsehne", "type": "numeric"},
    {"id": "winkel", "name": "Winkel gegen Vorgänger [°]", "type": "numeric"},
    {"id": "spalt", "name": "Spalt × Hauptsehne", "type": "numeric"},
    {"id": "ueberlappung", "name": "Überlappung × Hauptsehne", "type": "numeric"},
]


def _ansicht_kaskade() -> html.Div:
    return html.Div([
        _karte([
            _ueberschrift("Elemente hinter dem Hauptelement"),
            html.Div([
                "Ein Formula-Student-Frontflügel ist fast nie ein einzelnes "
                "Profil. Der Gewinn kommt nicht aus mehr Fläche, sondern aus "
                "dem ", html.B("Spalt"), ": Die Luft beschleunigt zwischen den "
                "Elementen hindurch und hält die Strömung anliegend, wo ein "
                "einzelnes Profil längst abgerissen wäre. ",
                html.B("Überlappung"), " ist, wie weit die Nase des Flaps VOR "
                "der Hinterkante des Vorgängers steht. Übliche Werte: Spalt "
                "0,01 bis 0,02, Überlappung 0,01 bis 0,04.",
            ], className="as-hinweis", style={"marginBottom": "10px"}),
            dash_table.DataTable(
                id="kaskadentabelle", columns=KASKADENSPALTEN, data=[],
                editable=True, row_deletable=True,
                dropdown={"profil": {"options": [
                    {"label": o["label"], "value": o["value"]}
                    for o in katalogoptionen()]}},
                style_cell={"fontFamily": "Consolas, monospace",
                            "fontSize": "13px", "padding": "6px 10px",
                            "textAlign": "right"},
                style_cell_conditional=[
                    {"if": {"column_id": "profil"}, "textAlign": "left",
                     "minWidth": "240px"}],
                style_header={"fontFamily": "Segoe UI, sans-serif",
                              "fontWeight": 600, "fontSize": "12px",
                              "textAlign": "right",
                              "backgroundColor": "#f4f5f7"},
                style_data_conditional=[
                    {"if": {"column_id": "spalt"},
                     "backgroundColor": "#fffdf5"}],
            ),
            html.Div([
                html.Button("Element hinzufügen", id="btn-stufe", n_clicks=0,
                            className="as-knopf as-knopf-leer",
                            style={"width": "auto", "marginRight": "10px"}),
                html.Span("Zeilen über das Kreuz rechts löschen. Ohne Zeile "
                          "bleibt es beim einzelnen Profil.",
                          className="as-hinweis"),
            ], style={"marginTop": "10px", "display": "flex",
                      "alignItems": "center", "gap": "8px"}),
        ]),

        html.Div([
            html.Div(_karte([_ueberschrift("Die Kaskade im Schnitt"),
                             dcc.Graph(id="fig-kaskade", **_GRAPH)]),
                     style={"flex": "3 1 0", "minWidth": 0,
                            "marginRight": "14px"}),
            html.Div(_karte([_ueberschrift("Beiwerte"),
                             dcc.Loading(html.Div(id="kaskaden-beiwerte"),
                                         type="dot")]),
                     style={"flex": "2 1 0", "minWidth": "320px"}),
        ], className="as-zeile"),

        _karte([
            _ueberschrift("Generator — Kombination mit dem größten Abtrieb"),
            html.Div("Probiert Profilpaarungen und Elementzahlen durch. "
                     "Spalt und Überlappung bleiben bei den Werten aus der "
                     "Tabelle oben.", className="as-hinweis",
                     style={"marginBottom": "12px"}),
            html.Div([
                _feld("Höchste Elementzahl",
                      _zahlenfeld("maxelemente", 3.0, 1.0, 1.0, 4.0)),
                html.Div([
                    html.Button("Kombinationen durchrechnen", id="btn-generator",
                                n_clicks=0, className="as-knopf as-knopf-voll"),
                    html.Div("Dauert etwa eine halbe Minute.",
                             className="as-hinweis", style={"marginTop": "6px"}),
                ]),
            ], className="as-leiste",
                style={"gridTemplateColumns": "240px 260px",
                       "marginBottom": "14px"}),
            dcc.Loading(html.Div(id="generator-ergebnis"), type="dot"),
        ]),
    ])


def _ansicht_creo() -> html.Div:
    return html.Div([
        _leiste("Export nach Creo", [
            _feld("Ausgabe", dcc.RadioItems(
                id="ausgabe", value="kurve",
                options=[{"label": " Eine geschlossene Kurve", "value": "kurve"},
                         {"label": " Profil aus zwei Kurven", "value": "profil"},
                         {"label": " 3D-Flügel über die Spannweite",
                          "value": "fluegel"},
                         {"label": " Kaskade (alle Elemente aus dem Reiter "
                                   "Kaskade)", "value": "kaskade"}],
                style={"fontSize": "13px"}),
                "Eine geschlossene Kurve ist der Normalfall: EIN umlaufender "
                "Spline, aus dem sich sofort eine Skizze und daraus ein "
                "Extrudieren machen lässt. Profil liefert Ober- und Unterseite "
                "getrennt — die berühren sich nur, für Creo ist das keine "
                "geschlossene Kontur, dafür braucht diese Form etwa ein "
                "Drittel der Punkte. 3D-Flügel schreibt einen Schnittstapel "
                "über die Spannweite, aus dem in Creo ein Verbund wird."),
            _feld("Toleranz [mm]",
                  _zahlenfeld("toleranz", 0.005, 0.001, 0.0005, 0.5),
                  "Creos Modellgenauigkeit liegt bei 0,010 mm."),
            _feld("Zielordner", dcc.Input(
                id="exportordner", type="text", value="export",
                className="as-textfeld"), "Relativ zum Projektordner."),
            _feld("Dateiname", dcc.Input(
                id="dateiname", type="text", value="", debounce=True,
                maxLength=80, placeholder="wie der Entwurf",
                className="as-textfeld"),
                "Leer lassen, dann heißt die Datei wie der Entwurf aus dem "
                "Reiter Profil. Die Endung .ibl kommt von selbst dazu; "
                "Umlaute und Sonderzeichen werden umgeschrieben."),
            _feld("Name des Skeletts", dcc.Input(
                id="skelettname", type="text", value="", debounce=True,
                maxLength=80, placeholder="Dateiname + „ Skelett\u201c",
                className="as-textfeld"),
                "Das Skelett bekommt eine eigene Datei — sie wird einmal "
                "importiert und bleibt dann stehen."),
            html.Div([
                html.Button("IBL schreiben", id="btn-export", n_clicks=0,
                            className="as-knopf as-knopf-voll"),
                html.Button("Schreiben und in Creo öffnen", id="btn-creo",
                            n_clicks=0, className="as-knopf as-knopf-leer"),
                html.Button("Skelett schreiben (nur Achsen)", id="btn-skelett",
                            n_clicks=0, className="as-knopf as-knopf-leer"),
                html.Div(id="creo-status", className="as-hinweis",
                         style={"marginTop": "9px"}),
                html.Div(id="skelett-status", className="as-hinweis",
                         style={"marginTop": "6px"}),
            ]),
        ], spalten="250px"),

        html.Div([
            html.Div(_karte([_ueberschrift("Diese Punkte gehen nach Creo"),
                             dcc.Graph(id="fig-export", **_GRAPH)]),
                     style={"flex": "2 1 0", "minWidth": 0,
                            "marginRight": "14px"}),
            html.Div(_karte([html.Div(id="export-info")]),
                     style={"flex": "1 1 0", "minWidth": "300px"}),
        ], className="as-zeile"),

        html.Div(id="regelkarte"),
        _karte([_ueberschrift("Vorschau der IBL-Datei"),
                html.Pre(id="ibl-vorschau", className="as-code",
                         style={"maxHeight": "300px"})]),
    ])


def _ansicht_projekt() -> html.Div:
    return html.Div([
        _karte([_ueberschrift("Aktueller Stand"),
                html.Div(id="projekt-info", style={"fontSize": "13px"})]),
        _karte([
            _ueberschrift("AeroSpec"),
            html.Div("Das hier ist der gesamte Zustand des Programms. Genau diese "
                     "Datei wird gespeichert und liegt im Git.",
                     className="as-hinweis", style={"marginBottom": "9px"}),
            html.Pre(id="spec-yaml", className="as-code",
                     style={"maxHeight": "500px"}),
        ]),
    ])


def layout() -> html.Div:
    marke = [k for k in (_logo(), html.Div([
        html.Div("Aero Studio", className="as-wortmarke"),
        html.Div("Rennschmiede Pforzheim", className="as-untertitel"),
    ])) if k is not None]

    return html.Div([
        dcc.Store(id="spec"),
        # Merkt sich je Verfahren die zuletzt benutzten Werte. Bewusst nur
        # Bedienkomfort und nicht Teil des Spec: Es beschreibt nicht den
        # Entwurf, sondern die Gewohnheit des Bearbeiters.
        dcc.Store(id="verfahrensspeicher", data={}),
        # Der zuletzt gerechnete Vorschlag, damit der Uebernehmen-Knopf
        # ihn anwenden kann, ohne noch einmal zu rechnen.
        dcc.Store(id="vorschlag"),
        # Die Kombinationen aus dem Generator, damit sich eine davon
        # uebernehmen laesst, ohne noch einmal zu rechnen.
        dcc.Store(id="kombinationen"),

        html.Div([
            html.Div(marke, className="as-marke"),
            html.Div([
                html.Span(id="kopf-status"),
                html.Span(id="kopf-hash", className="as-hash"),
                html.Button("Spec speichern", id="btn-speichern", n_clicks=0,
                            className="as-knopf as-knopf-klein"),
            ], className="as-kopf-rechts"),
        ], className="as-kopf"),
        html.Div(className="as-streifen"),

        dcc.Tabs(id="reiter", value="profil", className="as-reiter", children=[
            dcc.Tab(label="Profil", value="profil"),
            dcc.Tab(label="Flügel", value="fluegel"),
            dcc.Tab(label="Kaskade", value="kaskade"),
            dcc.Tab(label="Creo", value="creo"),
            dcc.Tab(label="Projekt", value="projekt"),
        ]),

        # Alle Ansichten stehen dauerhaft hier, der Reiter blendet nur um.
        html.Div([
            html.Div(_ansicht_profil(), id="view-profil"),
            html.Div(_ansicht_fluegel(), id="view-fluegel"),
            html.Div(_ansicht_kaskade(), id="view-kaskade"),
            html.Div(_ansicht_creo(), id="view-creo"),
            html.Div(_ansicht_projekt(), id="view-projekt"),
        ], className="as-inhalt"),
    ])


# ------------------------------------------------------------------ Callbacks

app = Dash(__name__, title="Aero Studio")
app.layout = layout


ANSICHTEN = ("profil", "fluegel", "kaskade", "creo", "projekt")


@app.callback(*[Output(f"view-{r}", "style") for r in ANSICHTEN],
              Input("reiter", "value"))
def _reiter_umblenden(reiter):
    an, aus = {"display": "block"}, {"display": "none"}
    return tuple(an if reiter == r else aus for r in ANSICHTEN)


@app.callback(Output("quelle-katalog", "style"), Output("quelle-naca", "style"),
              Input("quelle", "value"))
def _quelle_umschalten(quelle):
    an, aus = {"display": "block"}, {"display": "none"}
    return (an, aus) if quelle == "datei" else (aus, an)


@app.callback(
    Output(wert(MATCH), "value"),
    Input({"typ": "minus", "feld": MATCH}, "n_clicks"),
    Input({"typ": "plus", "feld": MATCH}, "n_clicks"),
    State(wert(MATCH), "value"),
    State(wert(MATCH), "min"), State(wert(MATCH), "max"),
    prevent_initial_call=True)
def _schrittweise(_minus, _plus, aktuell, minimum, maximum):
    """Eine Schaltflaeche weiter oder zurueck - fuer alle Zahlenfelder zugleich."""
    ausloeser = callback_context.triggered_id
    if not isinstance(ausloeser, dict):
        return no_update
    schritt = _SCHRITTE.get(ausloeser.get("feld"), 1.0)
    return schritt_rechnen(aktuell, schritt, ausloeser["typ"], minimum, maximum)


def schritt_rechnen(aktuell, schritt, richtung: str,
                    minimum=None, maximum=None) -> float:
    """Einen Schritt weiter oder zurueck, begrenzt und ohne Gleitkommareste.

    Ohne das Runden entstehen beim wiederholten Klicken Werte wie
    0.30000000000000004, die dann so im Spec und in der IBL landen.
    """
    schritt = float(schritt or 1.0)
    neu = float(aktuell or 0.0) + (schritt if richtung == "plus" else -schritt)
    if minimum is not None:
        neu = max(neu, float(minimum))
    if maximum is not None:
        neu = min(neu, float(maximum))
    stellen = max(0, -int(math.floor(math.log10(abs(schritt))))) + 1
    return round(neu, stellen)


def kaskade_aus_tabelle(zeilen) -> list[Kaskadenstufe]:
    """Macht aus den Tabellenzeilen die Flapliste.

    Unvollstaendige Zeilen werden uebersprungen statt abgelehnt - wer eine
    Zeile hinzufuegt und noch tippt, soll keine Fehlermeldung sehen. Werte
    ausserhalb des Gueltigen werden geklemmt, damit ein Tippfehler nicht die
    ganze Oberflaeche in eine Fehlermeldung schickt.
    """
    stufen = []
    for zeile in (zeilen or []):
        profil = (zeile.get("profil") or "").strip()
        if not profil:
            continue

        def zahl(schluessel, vorgabe, unten, oben):
            try:
                return min(max(float(zeile.get(schluessel)), unten), oben)
            except (TypeError, ValueError):
                return vorgabe

        stufen.append(Kaskadenstufe(
            profil=profil,
            sehne=zahl("sehne", 0.35, 0.05, 1.0),
            winkel=zahl("winkel", -20.0, -60.0, 60.0),
            spalt=zahl("spalt", 0.015, 0.002, 0.2),
            ueberlappung=zahl("ueberlappung", 0.02, -0.2, 0.2)))
    return stufen


def _kaskadendaten(stufen) -> list[dict]:
    return [{"profil": k.profil, "sehne": round(k.sehne, 3),
             "winkel": round(k.winkel, 1), "spalt": round(k.spalt, 4),
             "ueberlappung": round(k.ueberlappung, 4)} for k in stufen]


def _vorgaben(stufen) -> list:
    """Aus den Spec-Stufen die Vorgaben fuer die Geometrie."""
    return [geo_kaskade.Kaskadenvorgabe(
        profil=profil_aus_datei(k.profil), sehne_faktor=k.sehne,
        winkel_relativ=k.winkel, spalt=k.spalt, ueberlappung=k.ueberlappung,
        name=f"Flap {i}") for i, k in enumerate(stufen, start=1)]


def profil_aus_datei(datei: str):
    """Laedt ein Katalogprofil und spiegelt es fuer Abtrieb.

    Gespiegelt, weil Katalogprofile aus dem Flugzeugbau stammen und fuer
    Auftrieb gezeichnet sind - am Rennwagen ist Abtrieb der Normalfall.
    """
    from ..geometrie.profil import Profil
    return Profil.aus_dat(KATALOG / datei).gespiegelt()


def spannweite_aus_tabelle(zeilen, schnitte: int = 13) -> Spannweite:
    """Macht aus den Tabellenzeilen eine gueltige Spannweitenverteilung.

    Leere und unvollstaendige Zeilen werden uebersprungen statt abgelehnt: Wer
    eine Zeile hinzufuegt und noch nicht ausgefuellt hat, soll nicht sofort
    eine Fehlermeldung sehen. Bleibt gar nichts uebrig, greift die Vorgabe.
    """
    stellen = []
    for zeile in (zeilen or []):
        try:
            y = float(zeile.get("y"))
        except (TypeError, ValueError):
            continue

        def zahl(schluessel, vorgabe):
            try:
                return float(zeile.get(schluessel))
            except (TypeError, ValueError):
                return vorgabe

        stellen.append(Stuetzstelle(
            y=abs(y), sehne=max(zahl("sehne", 1.0), 1e-3),
            verwindung=zahl("verwindung", 0.0),
            z=zahl("z", 0.0), x=zahl("x", 0.0)))

    # Doppelte Spannweitenpositionen faengt das Datenmodell ab. Hier wird die
    # spaetere Zeile bevorzugt - beim Tippen entsteht ein Duplikat sonst
    # sofort und macht die Tabelle unbenutzbar.
    einmalig = {}
    for st in stellen:
        einmalig[round(st.y, 6)] = st
    stellen = [einmalig[k] for k in sorted(einmalig)]

    if not stellen:
        return Spannweite.frontfluegel_aussen()
    if len(stellen) == 1:
        stellen.append(Stuetzstelle(y=stellen[0].y + 1.0, sehne=stellen[0].sehne,
                                    verwindung=stellen[0].verwindung,
                                    z=stellen[0].z, x=stellen[0].x))
    return Spannweite(stuetzstellen=stellen, schnitte=int(schnitte))


def _baue_spec(quelle, katalogdatei, w, lage, dicke, wirkrichtung, sehne, aoa,
               verfahren, wandstaerke, kern, klebespalt, entwurfsname,
               stuetzstellen, schnittzahl, pos_x, pos_z,
               kaskadenzeilen) -> AeroSpec:
    """Sammelt die Bedienelemente zu einem gueltigen Spec.

    Einzige Stelle, an der aus Bedienelementen Fachdaten werden - alles Weitere
    arbeitet nur noch mit dem Spec.
    """
    spec = AeroSpec.beispiel()
    element = spec.elemente[0]
    if quelle == "naca":
        element.profil = ProfilNaca(
            woelbung=(0.0 if w is None else w) / 100.0,
            woelbungslage=(lage or 40) / 100.0,
            dicke=(dicke or 12) / 100.0)
    else:
        element.profil = ProfilAusDatei(datei=katalogdatei or "e423.dat")
    element.name = (entwurfsname or "").strip()
    element.wirkrichtung = Wirkrichtung(wirkrichtung or "abtrieb")
    element.sehne = float(sehne or 250.0)
    element.anstellwinkel = float(0.0 if aoa is None else aoa)
    # Die Spannweite steht immer im Spec, auch wenn gerade nur eine Kurve
    # ausgegeben wird. So geht die Einstellung beim Umschalten nicht verloren
    # - und der Regelcheck kann rechnen, ohne dass man erst exportieren muss.
    element.spannweite = spannweite_aus_tabelle(stuetzstellen,
                                               int(schnittzahl or 13))
    element.kaskade = kaskade_aus_tabelle(kaskadenzeilen)
    # Im Werkzeug zeigt x nach hinten, im Bedienfeld wird nach VORNE gefragt -
    # "600 mm vor der Vorderachse" ist die Sprache, in der ein Aeroteam denkt.
    element.pos_x = -float(pos_x if pos_x is not None else 600.0)
    element.pos_z = float(pos_z if pos_z is not None else 90.0)

    spec.fertigung = Fertigung(
        verfahren=verfahren or "unbestimmt",
        wandstaerke=float(wandstaerke or 0.6),
        kern=float(0.0 if kern is None else kern),
        klebespalt=float(0.0 if klebespalt is None else klebespalt))
    return spec


_EINGABEN = [
    Input("quelle", "value"), Input("katalogdatei", "value"),
    Input(wert("naca-woelbung"), "value"), Input(wert("naca-lage"), "value"),
    Input(wert("naca-dicke"), "value"), Input("wirkrichtung", "value"),
    Input(wert("sehne"), "value"), Input(wert("aoa"), "value"),
    Input("verfahren", "value"), Input(wert("wandstaerke"), "value"),
    Input(wert("kern"), "value"), Input(wert("klebespalt"), "value"),
    Input("entwurfsname", "value"),
    Input("stuetzstellen", "data"), Input(wert("schnittzahl"), "value"),
    Input(wert("pos-x"), "value"), Input(wert("pos-z"), "value"),
    Input("kaskadentabelle", "data"),
]


@app.callback(
    Output("spec", "data"), Output("ampel", "children"),
    Output("fig-kontur", "figure"), Output("fig-dicke", "figure"),
    Output("fig-kruemmung", "figure"), Output("fig-zonen", "figure"),
    *_EINGABEN)
def _profil_aktualisieren(*werte):
    try:
        spec = _baue_spec(*werte)
        element = spec.elemente[0]
        profil = profil_fuer(element)
        sehne = element.sehne
        fert = element.fertigung_wirksam(spec.fertigung)

        return (spec.model_dump(mode="json"),
                _ampel(profil, sehne, fert, profil.pruefe_fertigung(fert, sehne)),
                darstellung.kontur(profil, sehne, element.anstellwinkel, fert),
                darstellung.dickenverlauf(profil, sehne, fert),
                darstellung.kruemmung(profil),
                darstellung.zonenbalken(profil, sehne, fert))
    except Exception as fehler:
        leer = {"data": [], "layout": {"height": 200}}
        return no_update, _fehlerkarte(fehler), leer, leer, leer, leer


@app.callback(Output("katalog-notiz", "children"),
              Input("katalogdatei", "value"))
def _katalognotiz(datei):
    """Zeigt, wofuer das gewaehlte Profil taugt.

    Eigener Callback und nicht Teil der Ampel: Die Notiz haengt allein an der
    Profilauswahl. Waere sie im grossen Callback, wuerde sie bei jeder
    Sehnenaenderung mitgerechnet, ohne sich zu aendern.
    """
    notiz = katalognotiz(datei or "")
    if not notiz:
        return html.Div("Keine Notiz hinterlegt. Wer eine ergänzen möchte: "
                        "profile/katalog.yaml.", className="as-hinweis")

    teile = []
    if notiz.get("notiz"):
        teile.append(html.Div(notiz["notiz"].strip(), className="as-notiz-text"))
    if notiz.get("achtung"):
        teile.append(html.Div([html.B("Achtung: "), notiz["achtung"].strip()],
                              className="as-notiz-achtung"))
    return html.Div(teile, className="as-notiz")


def _ampel(profil, sehne, fertigung, befunde) -> html.Div:
    """Kennwerte und Pruefergebnisse als Ampel.

    Der Kopf sagt in einem Satz, ob sich das so bauen laesst. Darunter die
    Kennwerte, dann jede Pruefung mit Ist, Soll und - wo vorhanden - der
    Regelnummer. Ein Hinweis erscheint nur, wenn die Pruefung nicht besteht;
    sonst wuerde die Liste zulaufen und niemand liest sie mehr.
    """
    kennwerte = html.Div([
        html.Span([html.B(f"{profil.max_dicke*100:.1f} %"), " Dicke bei ",
                   html.B(f"{profil.max_dicke_bei*100:.0f} %")],
                  className="as-kennwert"),
        html.Span([html.B(f"{profil.max_woelbung*100:.1f} %"), " Wölbung"],
                  className="as-kennwert"),
        html.Span([html.B(f"{profil.nasenradius()*sehne:.1f} mm"), " Nasenradius"],
                  className="as-kennwert"),
        html.Span(f"{len(profil.punkte)} Punkte in der Quelle",
                  className="as-kennwert"),
    ], className="as-kennwerte")

    zeilen = []
    for bef in befunde:
        stufe = "ok" if bef.ok else bef.stufe
        zeichen = "✓" if bef.ok else ("✗" if bef.stufe == "fehler" else "!")
        kopf = [html.Span(zeichen, className=f"as-zeichen {stufe}"),
                html.Span(bef.pruefung, className="as-pruefung"),
                html.Span(f"  {bef.ist:.2f} {bef.einheit}  ·  gefordert ≥ "
                          f"{bef.soll:.2f}", className="as-messwert")]
        if bef.regel:
            kopf.append(html.Span(f"  {bef.regel}", className="as-regel"))
        eintrag = [html.Div(kopf)]
        if bef.hinweis and not bef.ok:
            eintrag.append(html.Div(bef.hinweis, className="as-befund-hinweis"))
        zeilen.append(html.Div(eintrag, className="as-befund"))

    blockiert = any(bef.blockiert for bef in befunde)
    return html.Div([
        html.Div("Nicht baubar in dieser Form" if blockiert
                 else "Regel- und fertigungskonform",
                 className=f"as-ampel-kopf {'fehl' if blockiert else 'ok'}"),
        kennwerte, html.Div(zeilen)])


def _fehlerkarte(fehler: Exception) -> html.Div:
    return html.Div([
        html.Div("Das lässt sich so nicht berechnen.", className="as-status-fehler"),
        html.Div(str(fehler), style={"marginTop": "7px"}),
        html.Details([html.Summary("Einzelheiten"),
                      html.Pre(traceback.format_exc(), className="as-code",
                               style={"marginTop": "7px"})],
                     style={"marginTop": "9px"}),
    ], className="as-fehlerkarte")


@app.callback(Output("kopf-hash", "children"), Input("spec", "data"))
def _kopfzeile(daten):
    return f"Spec {AeroSpec.model_validate(daten).hash()}" if daten else ""


@app.callback(Output("spec-yaml", "children"), Output("projekt-info", "children"),
              Input("spec", "data"))
def _projektreiter(daten):
    if not daten:
        return "", ""
    spec = AeroSpec.model_validate(daten)
    info = html.Div([
        html.Div(f"Name: {spec.meta.name}"),
        html.Div(f"Fahrzeug: {spec.meta.fahrzeug}"),
        html.Div(f"Regelstand: {spec.meta.regelstand}"),
        html.Div(f"Hash: {spec.hash()}", style={"color": "#777"}),
        html.Div(f"Datei: {SPEC_VORGABE}",
                 style={"color": "#777", "fontSize": "12px"}),
    ])
    return spec.als_yaml(), info


@app.callback(Output("kopf-status", "children"),
              Input("btn-speichern", "n_clicks"), State("spec", "data"))
def _speichern(n, daten):
    if not n or not daten:
        return ""
    try:
        AeroSpec.model_validate(daten).speichern(SPEC_VORGABE)
        return html.Span(f"gespeichert: {SPEC_VORGABE.name}",
                         className="as-status-ok")
    except Exception as fehler:
        return html.Span(f"Speichern fehlgeschlagen: {fehler}",
                         className="as-status-fehler")


@app.callback(Output("export-info", "children"), Output("ibl-vorschau", "children"),
              Output("fig-export", "figure"),
              Output("creo-status", "children"), Output("regelkarte", "children"),
              Input("spec", "data"), Input(wert("toleranz"), "value"),
              Input("exportordner", "value"), Input("ausgabe", "value"),
              Input("dateiname", "value"),
              Input("btn-export", "n_clicks"), Input("btn-creo", "n_clicks"))
def _export(daten, toleranz, ordner, ausgabe, dateiname, n_export, n_creo):
    leer = {"data": [], "layout": {"height": 200}}
    if not daten:
        return "", "", leer, "", ""
    try:
        spec = AeroSpec.model_validate(daten)
        element = spec.elemente[0]
        profil = profil_fuer(element)

        if ausgabe == "kaskade":
            plan = export.plane_kaskade(
                profil, element.sehne, element.anstellwinkel,
                _vorgaben(element.kaskade), float(toleranz or 0.005))
        elif ausgabe == "fluegel" and element.spannweite is not None:
            plan = export.plane_fluegel(
                profil, element.spannweite, element.sehne, element.anstellwinkel,
                lage=(element.pos_x, element.pos_y, element.pos_z),
                toleranz_mm=float(toleranz or 0.005))
        else:
            plan = export.plane_element(profil, element.sehne,
                                        element.anstellwinkel,
                                        float(toleranz or 0.005),
                                        geschlossen=(ausgabe != "profil"))
        ziel = (PROJEKT / (ordner or "export")
                / export.dateiname(_exportname(dateiname, element)))

        # Beide Schaltflaechen schreiben - die zweite oeffnet zusaetzlich Creo.
        nach_creo = _ausgeloest_von("btn-creo")
        geschrieben = None
        if _ausgeloest_von("btn-export") or nach_creo:
            export.schreibe(plan, ziel, kommentare=[
                f"Aero Studio - {element.anzeigename}",
                f"Profil {profil.name}, Sehne {element.sehne:.1f} mm, "
                f"Anstellwinkel {element.anstellwinkel:+.1f} Grad",
                "Kurvenform: " + (
                    f"Kaskade, {len(plan.sektionen)} geschlossene Kurven - "
                    f"eine je Element, Hauptelement zuerst"
                    if plan.ausgabe == "kaskade" else
                    "eine geschlossene Kurve" if plan.geschlossen
                    else "Ober- und Unterseite getrennt"),
                f"AERO_SPEC_HASH: {spec.hash()}",
            ])
            geschrieben = ziel

        status = _creo_oeffnen(ziel) if nach_creo else ""
        return (_exportinfo(plan, ziel, geschrieben), export.vorschau(plan),
                darstellung.exportpunkte(plan, profil.name), status,
                _regelkarte(plan))
    except Exception as fehler:
        return _fehlerkarte(fehler), "", leer, "", ""


@app.callback(Output("stuetzstellen", "data", allow_duplicate=True),
              Input("btn-vorgabe", "n_clicks"), Input("btn-sektion", "n_clicks"),
              State("verteilung", "value"),
              State(wert("halbspannweite"), "value"),
              State("stuetzstellen", "data"), prevent_initial_call=True)
def _tabelle_fuellen(n_vorgabe, n_sektion, verteilung, weite, daten):
    """Vorgabe laden oder eine Sektion anhaengen.

    Beides in EINEM Callback, weil Dash sonst zwei Schreiber auf dieselbe
    Tabelle haette und sich beschwert. Welcher Knopf gedrueckt wurde, sagt der
    Ausloeser.
    """
    if _ausgeloest_von("btn-vorgabe"):
        weite = float(weite or 600.0)
        vorgabe = (Spannweite.gerade(weite) if verteilung == "gerade"
                   else Spannweite.frontfluegel_aussen().skaliert(weite))
        return _tabellendaten(vorgabe)

    zeilen = list(daten or [])
    if not zeilen:
        return _tabellendaten(Spannweite.frontfluegel_aussen())

    # Neue Sektion hinter der aeussersten, mit deren Werten. So bleibt der
    # Fluegel beim Hinzufuegen unveraendert, bis jemand die Zeile bearbeitet -
    # eine Sektion mit Nullwerten wuerde ihn dagegen sofort verbiegen.
    letzte = max(zeilen, key=lambda z: float(z.get("y") or 0.0))
    neue = dict(letzte)
    neue["y"] = round(float(letzte.get("y") or 0.0) + 100.0, 1)
    return zeilen + [neue]


@app.callback(Output("sektionen-meldung", "children"),
              Output("fig-verteilung", "figure"),
              Output("fig-fluegel3d", "figure"),
              Input("spec", "data"), Input("ansicht3d", "value"))
def _fluegel_zeichnen(daten, ansicht):
    """Verlaeufe und Raumbild zum aktuellen Stand der Tabelle."""
    leer = {"data": [], "layout": {"height": 260}}
    if not daten:
        return "", leer, leer
    try:
        spec = AeroSpec.model_validate(daten)
        element = spec.elemente[0]
        profil = profil_fuer(element)
        stapel = spannweite.schnitte(
            profil, element.spannweite, element.sehne, element.anstellwinkel, 40,
            lage=(element.pos_x, element.pos_y, element.pos_z))

        anzahl = len(element.spannweite.stuetzstellen)
        werte = spannweite.huellwerte(stapel)
        zeilen = [html.Div(
            f"{anzahl} Sektionen, {element.spannweite.schnitte} Schnitte, "
            f"Halbspannweite {werte['spannweite']:.0f} mm, "
            f"Grundrissfläche je Seite {werte['flaeche'] / 100:.0f} cm².",
            className="as-hinweis")]

        # Abrisswinkel nur holen, wenn NeuralFoil da ist - ohne das Paket
        # bleibt die Ratenpruefung, die braucht keine Aerodynamik.
        abriss = None
        if aero_verfuegbar():
            try:
                from ..aero.profilpolare import polare, reynolds
                abriss = polare(profil, reynolds(15.0, element.sehne)).abriss_winkel
            except Exception:
                abriss = None

        for befund in verwindung.pruefe(element.spannweite,
                                        element.anstellwinkel, abriss):
            zeilen.append(html.Div([
                html.Span("!" if befund.stufe == "warnung" else "i",
                          className=f"as-zeichen "
                                    f"{'fehler' if befund.stufe == 'warnung' else 'hinweis'}"),
                html.Span(befund.text),
                html.Span(f"  {befund.ort}", className="as-regel") if befund.ort
                else html.Span(),
            ], className="as-befund-hinweis", style={"marginLeft": 0}))

        meldung = html.Div(zeilen)
        return (meldung, darstellung.spannweitenverlauf(stapel, element),
                darstellung.fluegel3d(stapel, profil.name,
                                      darstellung=ansicht or "flaeche"))
    except Exception as fehler:
        return _fehlerkarte(fehler), leer, leer


@app.callback(Output("aero-ergebnis", "children"),
              Input("btn-aero", "n_clicks"),
              State("spec", "data"), State(wert("tempo"), "value"),
              prevent_initial_call=True)
def _abtrieb_rechnen(n, daten, tempo):
    """Abtrieb abschaetzen. Auf Knopfdruck, nicht bei jeder Aenderung.

    Die Traglinienrechnung braucht ein paar Sekunden. Liefe sie bei jedem
    Reglerzug mit, waere die Oberflaeche unbenutzbar - und die Zahl ist eine
    Abschaetzung, die man bewusst abruft, kein Live-Messwert.
    """
    if not daten:
        return ""
    try:
        spec = AeroSpec.model_validate(daten)
        element = spec.elemente[0]
        profil = profil_fuer(element)
        stapel = spannweite.schnitte(
            profil, element.spannweite, element.sehne, element.anstellwinkel, 60,
            lage=(element.pos_x, element.pos_y, element.pos_z))
        v = float(tempo or 15.0)
        ergebnis = traglinie.rechne(stapel, profil, geschwindigkeit=v)
        kennlinie = traglinie.bodenkennlinie(
            stapel, profil, [40, 60, 80, 120, 200], geschwindigkeit=v)
        return _aerokarte(ergebnis, kennlinie)
    except Exception as fehler:
        return _fehlerkarte(fehler)


@app.callback(Output("vorschlag-ergebnis", "children"),
              Output("vorschlag", "data"),
              Input("btn-vorschlag", "n_clicks"),
              State("spec", "data"), State(wert("tempo"), "value"),
              State(wert("zielabtrieb"), "value"),
              State(wert("sehne-min"), "value"), State(wert("sehne-max"), "value"),
              State(wert("weite-min"), "value"), State(wert("weite-max"), "value"),
              State(wert("winkel-min"), "value"),
              prevent_initial_call=True)
def _vorschlag_rechnen(n, daten, tempo, ziel, sehne_min, sehne_max,
                       weite_min, weite_max, winkel_min):
    if not daten:
        return "", None
    try:
        spec = AeroSpec.model_validate(daten)
        element = spec.elemente[0]
        profil = profil_fuer(element)

        grenzen = aero_entwurf.Grenzen(
            sehne=(float(sehne_min or 120.0), float(sehne_max or 400.0)),
            halbspannweite=(float(weite_min or 300.0), float(weite_max or 695.0)),
            anstellwinkel=(float(winkel_min or -16.0), 0.0))

        v = aero_entwurf.suche(
            float(ziel or 60.0), profil, element.spannweite,
            geschwindigkeit=float(tempo or 15.0),
            lage=(element.pos_x, element.pos_y, element.pos_z),
            grenzen=grenzen)
        # ALLE Vorschlaege merken, nicht nur den besten - der Anwender soll
        # auswaehlen koennen, welchen er uebernimmt.
        gemerkt = [{"sehne": k.sehne, "halbspannweite": k.halbspannweite,
                    "anstellwinkel": k.anstellwinkel, "hoehe": k.hoehe}
                   for k in ([v.treffer] + v.alternativen) if k is not None]
        return _vorschlagskarte(v), gemerkt
    except Exception as fehler:
        return _fehlerkarte(fehler), None


def _vorschlagskarte(v) -> html.Div:
    """Der Vorschlag, mit Begruendung und Alternativen."""
    if not v.gefunden:
        return html.Div([
            html.Div(f"{v.ziel:.0f} N sind in diesem Rahmen nicht erreichbar.",
                     className="as-ampel-kopf fehl"),
            html.Div([html.Div(b, style={"marginBottom": "5px"})
                      for b in v.begruendung], className="as-hinweis"),
        ])

    t = v.treffer
    kopf = html.Div(
        "Vorschlag" if t.regelkonform else "Vorschlag — hält das Reglement NICHT ein",
        className=f"as-ampel-kopf {'ok' if t.regelkonform else 'fehl'}")

    zahlen = html.Div([
        html.Div([html.Div(f"{t.sehne:.0f} mm", className="as-grosszahl"),
                  html.Div("Wurzelsehne", className="as-hinweis")]),
        html.Div([html.Div(f"{t.halbspannweite:.0f} mm", className="as-grosszahl"),
                  html.Div("Halbspannweite", className="as-hinweis")]),
        html.Div([html.Div(f"{t.anstellwinkel:+.1f}°", className="as-grosszahl"),
                  html.Div("Anstellwinkel", className="as-hinweis")]),
        html.Div([html.Div(f"{t.hoehe:.0f} mm", className="as-grosszahl"),
                  html.Div("Höhe über Boden", className="as-hinweis")]),
        html.Div([html.Div(f"{t.abtrieb:.0f} N", className="as-grosszahl"),
                  html.Div("Abtrieb", className="as-hinweis")]),
        html.Div([html.Div(f"{t.wirkungsgrad:.1f}", className="as-grosszahl"),
                  html.Div("Abtrieb je Widerstand", className="as-hinweis")]),
    ], className="as-leiste",
        style={"gridTemplateColumns": "repeat(auto-fit, minmax(140px, 1fr))",
               "marginBottom": "14px"})

    teile = [kopf, zahlen,
             html.Div([
                 html.Button("Diesen Vorschlag übernehmen",
                             id={"typ": "uebernehmen", "nr": 0}, n_clicks=0,
                             className="as-knopf as-knopf-voll",
                             style={"width": "auto"}),
             ], style={"marginBottom": "14px"})]

    if t.verstoesse:
        teile.append(html.Div(
            [html.B("Verstöße: ")] + [html.Div(x) for x in t.verstoesse],
            className="as-status-fehler", style={"marginBottom": "10px"}))

    teile.append(html.Div([html.Div(b, style={"marginBottom": "5px"})
                           for b in v.begruendung], className="as-hinweis",
                          style={"marginBottom": "14px"}))

    if v.alternativen:
        teile.append(html.Div("Weitere Wege zum selben Ziel",
                              className="as-untertitel-dunkel"))
        teile.append(html.Table(
            [html.Tr([html.Th("Sehne"), html.Th("Halbspannw."),
                      html.Th("Winkel"), html.Th("Höhe"),
                      html.Th("Abtrieb"), html.Th("L/D"), html.Th("Regeln"),
                      html.Th("")])]
            + [html.Tr([html.Td(f"{k.sehne:.0f} mm"),
                        html.Td(f"{k.halbspannweite:.0f} mm"),
                        html.Td(f"{k.anstellwinkel:+.1f}°"),
                        html.Td(f"{k.hoehe:.0f} mm"),
                        html.Td(f"{k.abtrieb:.0f} N"),
                        html.Td(f"{k.wirkungsgrad:.1f}"),
                        html.Td("ok" if k.regelkonform else "Verstoß",
                                className="as-status-ok" if k.regelkonform
                                else "as-status-fehler"),
                        html.Td(html.Button(
                            "übernehmen",
                            id={"typ": "uebernehmen", "nr": i}, n_clicks=0,
                            className="as-knopf as-knopf-leer",
                            style={"width": "auto", "padding": "3px 10px",
                                   "fontSize": "11.5px", "marginTop": 0}))])
               for i, k in enumerate(v.alternativen, start=1)],
            className="as-tabelle"))

    teile.append(html.Div(
        "Übernehmen setzt Sehne, Anstellwinkel, Halbspannweite und Höhe. Die "
        "Verwindung aus der Sektionstabelle bleibt erhalten und wird nur auf "
        "die neue Spannweite gestreckt. Danach im Reiter Creo exportieren.",
        className="as-hinweis", style={"marginTop": "12px"}))
    teile.append(html.Div(id="uebernommen", style={"marginTop": "8px"}))
    return html.Div(teile)


@app.callback(Output(wert("sehne"), "value"), Output(wert("aoa"), "value"),
              Output(wert("halbspannweite"), "value"),
              Output(wert("pos-z"), "value"),
              Output("stuetzstellen", "data", allow_duplicate=True),
              Output("uebernommen", "children"),
              Input({"typ": "uebernehmen", "nr": ALL}, "n_clicks"),
              State("vorschlag", "data"), State("stuetzstellen", "data"),
              prevent_initial_call=True)
def _vorschlag_uebernehmen(klicks, vorschlaege, tabelle):
    """Schreibt den GEWAEHLTEN Vorschlag in die Bedienelemente.

    Jede Zeile der Vorschlagsliste hat einen eigenen Knopf. Welcher gedrueckt
    wurde, sagt der Ausloeser - deshalb Mustererkennung ueber ALL und nicht
    ein Knopf je fester Kennung: Die Zahl der Alternativen steht erst zur
    Laufzeit fest.

    Die Verwindung wird NICHT ueberschrieben, nur auf die neue Spannweite
    gestreckt - sie ist die Entwurfsabsicht des Anwenders, und die Suche hat
    sie ohnehin unangetastet gelassen.
    """
    leer = (no_update,) * 6
    if not vorschlaege or not klicks or not any(k for k in klicks):
        return leer

    ausloeser = callback_context.triggered_id
    if not isinstance(ausloeser, dict):
        return leer
    nummer = int(ausloeser.get("nr", 0))
    if nummer >= len(vorschlaege):
        return leer

    gewaehlt = vorschlaege[nummer]
    gestreckt = spannweite_aus_tabelle(tabelle).skaliert(
        float(gewaehlt["halbspannweite"]))
    bezeichnung = ("Der beste Vorschlag" if nummer == 0
                   else f"Alternative {nummer}")
    return (round(float(gewaehlt["sehne"]), 1),
            round(float(gewaehlt["anstellwinkel"]), 2),
            round(float(gewaehlt["halbspannweite"]), 1),
            round(float(gewaehlt["hoehe"]), 1),
            _tabellendaten(gestreckt),
            html.Div(f"{bezeichnung} ist übernommen: {gewaehlt['sehne']:.0f} mm "
                     f"Sehne, {gewaehlt['anstellwinkel']:+.1f} Grad, "
                     f"{gewaehlt['halbspannweite']:.0f} mm Halbspannweite, "
                     f"{gewaehlt['hoehe']:.0f} mm Höhe. Jetzt im Reiter Creo "
                     f"exportieren.", className="as-status-ok"))


def _aerokarte(e, kennlinie) -> html.Div:
    """Das Ergebnis der Abschaetzung, mit den Grenzen daneben.

    Die Grenzen stehen bewusst NEBEN der Zahl und nicht im Kleingedruckten
    weiter unten. Eine Abtriebszahl ohne den Hinweis, was sie nicht enthaelt,
    wird als Messwert gelesen - und dann wird damit ausgelegt.
    """
    zahlen = html.Div([
        html.Div([html.Div(f"{e.abtrieb:.0f} N", className="as-grosszahl"),
                  html.Div("Abtrieb", className="as-hinweis")]),
        html.Div([html.Div(f"{e.widerstand:.1f} N", className="as-grosszahl"),
                  html.Div("Widerstand", className="as-hinweis")]),
        html.Div([html.Div(f"{e.wirkungsgrad:.1f}", className="as-grosszahl"),
                  html.Div("Abtrieb je Widerstand", className="as-hinweis")]),
        html.Div([html.Div(f"{e.cl:+.2f}", className="as-grosszahl"),
                  html.Div("CL auf die Grundrissfläche", className="as-hinweis")]),
        html.Div([html.Div(f"{e.streckung:.1f}", className="as-grosszahl"),
                  html.Div("Streckung", className="as-hinweis")]),
    ], className="as-leiste",
        style={"gridTemplateColumns": "repeat(auto-fit, minmax(150px, 1fr))",
               "marginBottom": "14px"})

    warnungen = []
    if not e.konvergiert:
        warnungen.append("Die Rechnung ist nicht auskonvergiert — die Zahl ist "
                         "unsicher.")
    if e.abgerissen > 0.02:
        warnungen.append(f"Auf {e.abgerissen * 100:.0f} % der Fläche ist die "
                         f"Strömung abgerissen. Anstellwinkel oder Verwindung "
                         f"zurücknehmen.")
    if e.vertrauen < 0.85:
        warnungen.append(f"NeuralFoil ist sich bei diesem Arbeitspunkt selbst "
                         f"nur zu {e.vertrauen * 100:.0f} % sicher.")

    zeilen = [html.Div(w, className="as-status-hinweis",
                       style={"marginBottom": "5px"}) for w in warnungen]

    boden = html.Table([
        html.Tr([html.Th("Höhe über Boden"), html.Th("Abtrieb"), html.Th("CL")])
    ] + [
        html.Tr([html.Td(f"{h:.0f} mm"), html.Td(f"{k.abtrieb:.0f} N"),
                 html.Td(f"{k.cl:+.2f}")]) for h, k in kennlinie
    ], className="as-tabelle")

    return html.Div([
        zahlen,
        html.Div(zeilen) if zeilen else html.Div(),
        html.Div([
            html.Div([
                html.Div("Über den Bodenabstand", className="as-untertitel-dunkel"),
                boden,
            ], style={"flex": "0 0 300px", "marginRight": "22px"}),
            html.Div([
                html.Div("Was diese Zahl ist — und was nicht",
                         className="as-untertitel-dunkel"),
                html.Div([
                    html.P("Gerechnet mit NeuralFoil für das Profil und einer "
                           "Traglinienrechnung mit Bodenspiegelung für die "
                           "Spannweite. Das ist eine Abschätzung zum Vergleich "
                           "von Entwürfen, kein CFD-Ersatz."),
                    html.P([html.B("Nicht enthalten: "),
                            "die Beschleunigung im Kanal zwischen Flügel und "
                            "Boden — deshalb ist der Abtrieb bei kleinem "
                            "Bodenabstand eher zu niedrig. Ebenso fehlen "
                            "Endplatten, Räder, die Wirkung mehrerer Elemente "
                            "aufeinander und der Aufstau vor dem Fahrzeug."]),
                    html.P([html.B("Enthalten: "),
                            "Reynoldszahl aus Geschwindigkeit und Sehne, "
                            "Verwindung je Sektion, der induzierte Winkel über "
                            "die Spannweite, Abriss, und der Bodeneinfluss auf "
                            "die induzierte Strömung."]),
                ], className="as-hinweis"),
            ], style={"flex": "1 1 0", "minWidth": 0}),
        ], className="as-zeile"),
    ])


@app.callback(Output("skelett-status", "children"),
              Input("btn-skelett", "n_clicks"),
              State("spec", "data"), State("exportordner", "value"),
              State("dateiname", "value"), State("skelettname", "value"),
              prevent_initial_call=True)
def _skelett_schreiben(n, daten, ordner, dateiname, skelettname):
    """Schreibt die Drehachsen statt der Flaechen.

    Eigener Knopf und eigene Datei: Das Skelett wird EINMAL importiert und
    bleibt dann stehen. Die Fluegel haengen daran und lassen sich in Creo
    ueber ihren Anstellwinkel verstellen, ohne dass etwas neu importiert
    werden muss - genau das ist der Zweck.
    """
    if not daten:
        return ""
    try:
        spec = AeroSpec.model_validate(daten)
        element = spec.elemente[0]
        profil = profil_fuer(element)
        achse = skelett.aus_element(element, profil)
        plan = skelett.plane_skelett([achse], regeln.Bezugsgeometrie.aus_datei())
        name = (skelettname or "").strip() or (
            _exportname(dateiname, element) + " Skelett")
        ziel = PROJEKT / (ordner or "export") / export.dateiname(name)
        skelett.schreibe(plan, ziel)
        return html.Div([
            html.Div(f"Skelett geschrieben: {ziel}", className="as-status-ok"),
            html.Div(f"{len(plan.sektionen)} Linien — Drehachse, Querlinie und "
                     f"die Bezugslinien des Reglements. Die Reihenfolge steht "
                     f"als Kommentar im Kopf der Datei.",
                     style={"marginTop": "4px"}),
        ])
    except Exception as fehler:
        return _fehlerkarte(fehler)


@app.callback(Output("kaskadentabelle", "data", allow_duplicate=True),
              Input("btn-stufe", "n_clicks"),
              State("kaskadentabelle", "data"), prevent_initial_call=True)
def _stufe_hinzufuegen(n, daten):
    """Ein weiteres Element anhaengen.

    Jedes weitere Element ist kuerzer und flacher als sein Vorgaenger - so
    bauen es alle, und so bleibt der Entwurf beim Hinzufuegen brauchbar.
    """
    zeilen = list(daten or [])
    if not zeilen:
        return [{"profil": "e58.dat", "sehne": 0.35, "winkel": -20.0,
                 "spalt": 0.015, "ueberlappung": 0.02}]
    letzte = zeilen[-1]
    return zeilen + [{
        "profil": letzte.get("profil", "e58.dat"),
        "sehne": round(max(float(letzte.get("sehne", 0.35)) - 0.07, 0.1), 3),
        "winkel": round(float(letzte.get("winkel", -20.0)) + 4.0, 1),
        "spalt": letzte.get("spalt", 0.015),
        "ueberlappung": letzte.get("ueberlappung", 0.02)}]


@app.callback(Output("fig-kaskade", "figure"),
              Output("kaskaden-beiwerte", "children"),
              Input("spec", "data"), Input(wert("tempo"), "value"))
def _kaskade_zeichnen(daten, tempo):
    """Schnittbild und Beiwerte der Kaskade."""
    leer = {"data": [], "layout": {"height": 300}}
    if not daten:
        return leer, ""
    try:
        spec = AeroSpec.model_validate(daten)
        element = spec.elemente[0]
        haupt = profil_fuer(element)
        elemente = geo_kaskade.platziere(haupt, element.sehne,
                                         element.anstellwinkel,
                                         _vorgaben(element.kaskade),
                                         lage=(0.0, element.pos_z))
        bild = darstellung.kaskadenschnitt(elemente, element.pos_z)

        if not aero_verfuegbar():
            return bild, html.Div(
                "Ohne NeuralFoil lassen sich keine Beiwerte rechnen. Die "
                "Geometrie steht trotzdem und laesst sich exportieren.",
                className="as-hinweis")

        # Der Boden bleibt in der Zeichnung sichtbar. In der 2D-Rechnung
        # wäre seine Spiegelung jedoch ohne Grenzschichtmodell unphysikalisch
        # stark; der tatsächliche Bodeneffekt muss später mit CFD abgeglichen
        # werden.
        beiwert = aero_kaskade.rechne(elemente, float(tempo or 15.0),
                                      mit_boden=False)
        return bild, _kaskadenkarte(elemente, beiwert)
    except Exception as fehler:
        return leer, _fehlerkarte(fehler)


def _kaskadenkarte(elemente, b) -> html.Div:
    """Die Beiwerte, mit der Unsicherheit daneben statt im Kleingedruckten."""
    kopf = html.Div([
        html.Div(f"{b.cl:+.2f}", className="as-grosszahl"),
        html.Div(f"CL auf die Gesamtsehne von {b.gesamtsehne:.0f} mm",
                 className="as-hinweis"),
    ], style={"marginBottom": "10px"})

    zeilen = [html.Tr([html.Th("Element"), html.Th("Winkel"), html.Th("Spalt"),
                       html.Th("allein"), html.Th("im Verbund"), html.Th("Gewinn")])]
    for lage, e in zip(elemente, b.elemente):
        zeilen.append(html.Tr([
            html.Td(e.name), html.Td(f"{e.winkel:+.1f}°"),
            html.Td(f"{lage.spalt:.1f} mm" if lage.spalt else "—"),
            html.Td(f"{e.cl_allein:+.2f}"), html.Td(f"{e.cl_verbund:+.2f}"),
            html.Td(f"{e.gewinn:.2f}×",
                    className="as-status-ok" if e.gewinn > 1.05 else "")]))

    warnungen = []
    if b.abgerissen:
        betroffen = ", ".join(e.name for e in b.elemente if e.abgerissen)
        warnungen.append(
            f"Abriss gemeldet an: {betroffen}. Die Saugspitze übersteigt dort, "
            f"was die Grenzschicht des Profils trägt. Flachere Winkel oder ein "
            f"größerer Spalt helfen.")

    return html.Div([
        kopf,
        html.Table(zeilen, className="as-tabelle"),
        html.Div([html.Div(w, className="as-status-hinweis",
                           style={"marginTop": "8px"}) for w in warnungen]),
        html.Div([
            html.Div("Wie sicher ist das?", className="as-untertitel-dunkel",
                     style={"marginTop": "14px"}),
            html.Div([
                html.P([f"Reibungsfrei kämen {b.cl_reibungsfrei:+.2f} heraus. "
                        f"Der wahre Wert liegt dazwischen — das Modell rechnet "
                        f"die Grenzschicht über den Spalt hinweg nicht mit, "
                        f"und genau die hält die Strömung an."]),
                html.P("Für den VERGLEICH zweier Entwürfe ist das weniger "
                       "schlimm als für den Absolutwert: Der Fehler wirkt auf "
                       "beide in dieselbe Richtung."),
            ], className="as-hinweis"),
        ]),
    ])


@app.callback(Output("generator-ergebnis", "children"),
              Output("kombinationen", "data"),
              Input("btn-generator", "n_clicks"),
              State("spec", "data"), State(wert("tempo"), "value"),
              State(wert("maxelemente"), "value"),
              prevent_initial_call=True)
def _generator_rechnen(n, daten, tempo, maxelemente):
    if not daten:
        return "", None
    try:
        spec = AeroSpec.model_validate(daten)
        element = spec.elemente[0]
        stufe = element.kaskade[0] if element.kaskade else Kaskadenstufe()

        ergebnis = aero_generator.suche(
            element.spannweite, element.sehne, element.anstellwinkel,
            float(tempo or 15.0),
            lage=(element.pos_x, element.pos_y, element.pos_z),
            elementzahlen=tuple(range(1, int(maxelemente or 3) + 1)),
            spalt=stufe.spalt, ueberlappung=stufe.ueberlappung)

        # Jede Kombination so merken, wie die Tabellen sie brauchen: das
        # Hauptprofil fuer den Reiter Profil, die Flaps fuer die
        # Kaskadentabelle.
        gemerkt = []
        for b in ([ergebnis.bester] + ergebnis.alternativen):
            if b is None:
                continue
            gemerkt.append({
                "hauptprofil": b.hauptprofil,
                "zeilen": [
                    {"profil": b.flapprofil,
                     # Dieselbe Verjuengung, mit der der Generator rechnet.
                     "sehne": round(0.35 - 0.07 * i, 3),
                     "winkel": float(w),
                     "spalt": stufe.spalt, "ueberlappung": stufe.ueberlappung}
                    for i, w in enumerate(b.flapwinkel)]})
        return _generatorkarte(ergebnis), gemerkt
    except Exception as fehler:
        return _fehlerkarte(fehler), None


def _generatorkarte(e) -> html.Div:
    if e.bester is None:
        return html.Div([
            html.Div("Keine brauchbare Kombination gefunden.",
                     className="as-ampel-kopf fehl"),
            html.Div([html.Div(b) for b in e.begruendung],
                     className="as-hinweis"),
        ])

    zeilen = [html.Tr([html.Th("Elemente"), html.Th("Hauptprofil"),
                       html.Th("Flapprofil"), html.Th("Flapwinkel"),
                       html.Th("Abtrieb"), html.Th("L/D"), html.Th("Sehne"),
                       html.Th("")])]
    for i, b in enumerate([e.bester] + e.alternativen):
        winkel = ", ".join(f"{w:+.0f}°" for w in b.flapwinkel) or "—"
        zeilen.append(html.Tr([
            html.Td(str(b.elemente)), html.Td(b.hauptprofil.replace(".dat", "")),
            html.Td(b.flapprofil.replace(".dat", "")), html.Td(winkel),
            html.Td(f"{b.abtrieb:.0f} N"), html.Td(f"{b.wirkungsgrad:.1f}"),
            html.Td(f"{b.gesamtsehne:.0f} mm"),
            html.Td(html.Button("übernehmen",
                                id={"typ": "kombination", "nr": i}, n_clicks=0,
                                className="as-knopf as-knopf-leer",
                                style={"width": "auto", "padding": "3px 10px",
                                       "fontSize": "11.5px", "marginTop": 0}))]))

    return html.Div([
        html.Div(f"{e.bester.abtrieb:.0f} N", className="as-grosszahl"),
        html.Div(f"mit {e.bester.elemente} Element(en): "
                 f"{e.bester.hauptprofil.replace('.dat', '')} + "
                 f"{e.bester.flapprofil.replace('.dat', '')}",
                 className="as-hinweis", style={"marginBottom": "12px"}),
        html.Table(zeilen, className="as-tabelle"),
        html.Div([html.Div(b, style={"marginTop": "5px"})
                  for b in e.begruendung],
                 className="as-hinweis", style={"marginTop": "12px"}),
        html.Div("Übernehmen setzt Hauptprofil und die Elemententabelle oben. "
                 "Sehne, Anstellwinkel und Spannweite bleiben, wie sie sind — "
                 "der Generator hat sie nicht verändert.",
                 className="as-hinweis", style={"marginTop": "10px"}),
        html.Div(id="kombination-uebernommen", style={"marginTop": "8px"}),
    ])


@app.callback(Output("kaskadentabelle", "data", allow_duplicate=True),
              Output("katalogdatei", "value"),
              Output("kombination-uebernommen", "children"),
              Input({"typ": "kombination", "nr": ALL}, "n_clicks"),
              State("kombinationen", "data"), prevent_initial_call=True)
def _kombination_uebernehmen(klicks, kombinationen):
    """Setzt eine Kombination aus dem Generator als aktuellen Entwurf.

    Zwei Ziele auf einmal: das Hauptprofil im Reiter Profil und die
    Elemententabelle hier. Beides gehoert zusammen - eine Kombination ohne ihr
    Hauptprofil ist keine.

    Sehne, Anstellwinkel und Spannweite bleiben unangetastet: Der Generator
    hat sie als Vorgabe BEKOMMEN und nicht veraendert; sie jetzt zu
    ueberschreiben waere eine Aenderung, die niemand angefordert hat.
    """
    leer = (no_update,) * 3
    if not kombinationen or not klicks or not any(k for k in klicks):
        return leer

    ausloeser = callback_context.triggered_id
    if not isinstance(ausloeser, dict):
        return leer
    nummer = int(ausloeser.get("nr", 0))
    if nummer >= len(kombinationen):
        return leer

    gewaehlt = kombinationen[nummer]
    zeilen = gewaehlt["zeilen"]
    anzahl = len(zeilen) + 1
    meldung = (f"Übernommen: {anzahl} Element(e) mit "
               f"{gewaehlt['hauptprofil'].replace('.dat', '')} als "
               f"Hauptelement"
               + (f" und {len(zeilen)} Flap(s)." if zeilen else "."))
    return zeilen, gewaehlt["hauptprofil"], html.Div(
        meldung + " Die Elemententabelle oben ist gesetzt; das Schnittbild und "
        "die Beiwerte rechnen sich neu.", className="as-status-ok")


def _regelkarte(plan) -> html.Div:
    """Prueft den Fluegel gegen beide Regelstaende und zeigt es nebeneinander.

    Nur beim 3D-Fluegel: Ein einzelner Profilschnitt hat keine Lage am
    Fahrzeug, und ohne Lage laesst sich keine einzige Regel aus T 8.2 pruefen.
    Eine Ampel, die dann trotzdem gruen meldet, waere schlimmer als keine.
    """
    if not plan.ist_fluegel or not plan.stapel:
        return html.Div()

    bezug = regeln.Bezugsgeometrie.aus_datei()
    vorne = max(0.0, -min(s.punkte[:, 0].min() for s in plan.stapel))
    zustand = regeln.Fahrzustand.bremsend(vorne)

    spalten = []
    for satz in regeln.alle_staende():
        befunde = regeln.pruefe_fluegel(plan.stapel, satz, bezug, zustand)
        schlecht = [b for b in befunde if not b.ok]
        harte = [b for b in schlecht if b.blockiert]

        kopf = ("Regelkonform" if not schlecht else
                (f"{len(harte)} Verstoß" if len(harte) == 1 else
                 f"{len(harte)} Verstöße") if harte else
                f"{len(schlecht)} Punkt(e) zu prüfen")
        spalten.append(html.Div([
            html.Div([
                html.Span(satz.version, style={"fontWeight": 700}),
                html.Span(" · Entwurf, nicht verbindlich" if satz.entwurf
                          else " · geltend", className="as-regel"),
            ], style={"marginBottom": "6px"}),
            html.Div(kopf, className="as-ampel-kopf "
                     + ("fehl" if harte else "ok"),
                     style={"fontSize": "13.5px"}),
            html.Div([_regelzeile(b) for b in befunde]),
        ], className="as-spalte-rechts", style={"minWidth": "340px"}))

    return _karte([
        _ueberschrift("Regelprüfung im Fahrzustand"),
        html.Div(f"Geprüft über den Federungs-Envelope, wie T 8.2.4 es "
                 f"verlangt: {zustand.hoch:.1f} mm höher beim Ausfedern, "
                 f"{zustand.tief:.1f} mm tiefer beim Bremsen "
                 f"({zustand.quelle}).", className="as-hinweis",
                 style={"marginBottom": "12px"}),
        html.Div(spalten, className="as-zeile", style={"gap": "24px"}),
    ])


def _regelzeile(b) -> html.Div:
    stufe = "ok" if b.ok else b.stufe
    zeichen = "✓" if b.ok else ("✗" if b.stufe == "fehler" else "!")
    pfeil = "≤" if b.richtung == "max" else "≥"
    zeilen = [html.Div([
        html.Span(zeichen, className=f"as-zeichen {stufe}"),
        html.Span(b.pruefung, className="as-pruefung"),
        html.Span(f"  {b.ist:.1f} {pfeil} {b.grenze:.1f} {b.einheit}",
                  className="as-messwert"),
        html.Span(f"  {b.regel}", className="as-regel"),
    ])]
    if b.ort and not b.ok:
        zeilen.append(html.Div(b.ort, className="as-befund-hinweis"))
    if b.hinweis and not b.ok:
        zeilen.append(html.Div(b.hinweis, className="as-befund-hinweis"))
    return html.Div(zeilen, className="as-befund")


def _creo_oeffnen(ziel: Path):
    """Startet Creo mit der Datei und macht das Ergebnis lesbar."""
    ergebnis = creo_starten.oeffne(ziel)
    klasse = "as-status-ok" if ergebnis.gestartet else "as-status-hinweis"
    teile = [html.Div(ergebnis.meldung, className=klasse)]
    if ergebnis.hinweis:
        teile.append(html.Div(ergebnis.hinweis, style={"marginTop": "4px"}))
    return html.Div(teile)


def _ausgeloest_von(kennung: str) -> bool:
    """Wurde der Callback von diesem Bedienelement ausgeloest?

    Faengt den Fall ab, dass die Funktion ausserhalb eines echten Callbacks
    aufgerufen wird - etwa in einem Test. Dash wirft dort beim Zugriff auf den
    Kontext, und ein Test soll nicht an Dash scheitern, sondern an der Sache.
    """
    try:
        return callback_context.triggered_id == kennung
    except Exception:
        return False


def _exportname(dateiname: str | None, element) -> str:
    """Welcher Name auf die Datei kommt.

    Zwei Namen mit verschiedenen Aufgaben: Der ENTWURFSNAME beschreibt, was
    das Ding ist, und steht im Kopf der IBL-Datei. Der DATEINAME bestimmt, wie
    sie heisst. Meistens sind beide gleich - deshalb faellt der Dateiname auf
    den Entwurfsnamen zurueck, wenn das Feld leer bleibt.

    Getrennt, weil beim Erproben mehrere Staende desselben Entwurfs
    nebeneinander liegen sollen: "Frontfluegel v3 Spalt 1.2" als Datei, im
    Kopf weiter "Frontfluegel Hauptelement".
    """
    eigen = (dateiname or "").strip()
    return eigen or element.anzeigename


def _exportinfo(plan, ziel: Path, geschrieben: Path | None) -> html.Div:
    zeilen = [
        html.Div([html.Span("Punktzahl: ", style={"fontWeight": 600}),
                  html.Span(f"{plan.punktzahl} je Seite, berechnet für "
                            f"{plan.toleranz_mm:.4f} mm Toleranz "
                            f"({plan.punkte_gesamt} Punkte gesamt"
                            + (f", {len(plan.sektionen[0])} je Schnitt)"
                               if plan.ist_fluegel else ")"))]),
        html.Div(f"Die geforderten {plan.toleranz_gefordert:.4f} mm waren nicht "
                 f"erreichbar — gerechnet wurde mit {plan.toleranz_mm:.4f} mm.",
                 className="as-status-hinweis", style={"marginTop": "5px"})
        if plan.gelockert else html.Div(),
        html.Div([html.Span("Kurvenform: ", style={"fontWeight": 600}),
                  html.Span(
                      f"Kaskade aus {len(plan.sektionen)} Elementen, je eine "
                      "geschlossene Kurve — in Creo jede einzeln projizieren "
                      "und extrudieren"
                      if plan.ausgabe == "kaskade" else
                      f"{len(plan.sektionen)} geschlossene Schnitte über die "
                      "Spannweite — in Creo als Verbund zu einem Volumen"
                      if plan.ist_fluegel else
                      "eine geschlossene Kurve — in Creo unmittelbar als "
                      "Skizze verwendbar und damit extrudierbar"
                      if plan.geschlossen else
                      f"{len(plan.sektionen)} getrennte Kurven für Ober- und "
                      "Unterseite — sie berühren sich nur, für Creo ist das "
                      "keine geschlossene Kontur")]),
        html.Div(f"{plan.ausgeduennt} Punkte entfernt, die enger beieinander "
                 f"lagen als Creos Modellgenauigkeit von 0,010 mm — Creo hätte "
                 f"sie für denselben Punkt gehalten.",
                 className="as-hinweis", style={"marginTop": "4px"})
        if plan.ausgeduennt else html.Div(),
        html.Div([html.Span("Koordinaten: ", style={"fontWeight": 600}),
                  html.Span("bereits in das System der Creo-Vorlage gedreht — "
                            "in Creo ist nichts vorzubereiten")]),
        html.Div([html.Span("Ziel: ", style={"fontWeight": 600}),
                  html.Span(str(ziel))], style={"color": "#777"}),
    ]
    if geschrieben:
        zeilen.append(html.Div(f"Geschrieben: {geschrieben}",
                               className="as-status-ok",
                               style={"marginTop": "9px"}))
    return html.Div(zeilen, style={"fontSize": "13px"})


@app.callback(
    Output(wert("wandstaerke"), "value"), Output(wert("kern"), "value"),
    Output(wert("klebespalt"), "value"),
    Input("verfahren", "value"), State("verfahrensspeicher", "data"))
def _verfahren_gewaehlt(verfahren, speicher):
    """Beim Wechsel des Verfahrens die passenden Werte einsetzen.

    Erst das, was zu diesem Verfahren zuletzt benutzt wurde; gibt es das noch
    nicht, die Startwerte aus dem Datenmodell. Ohne das war das Feld eine
    reine Beschriftung - es stand etwas anderes da, aber gerechnet wurde
    weiter mit denselben Zahlen.
    """
    gemerkt = (speicher or {}).get(verfahren)
    werte = gemerkt if gemerkt else vorgaben_fuer(verfahren)
    return werte["wandstaerke"], werte["kern"], werte["klebespalt"]


@app.callback(
    Output("verfahrensspeicher", "data"),
    Input(wert("wandstaerke"), "value"), Input(wert("kern"), "value"),
    Input(wert("klebespalt"), "value"),
    State("verfahren", "value"), State("verfahrensspeicher", "data"))
def _verfahren_merken(wandstaerke, kern, klebespalt, verfahren, speicher):
    """Haelt fest, was zu diesem Verfahren zuletzt eingestellt war."""
    if verfahren is None:
        return no_update
    speicher = dict(speicher or {})
    speicher[verfahren] = {"wandstaerke": wandstaerke, "kern": kern,
                           "klebespalt": klebespalt}
    return speicher


def starten(port: int = 8051, browser: bool = True) -> None:
    if browser:
        Timer(1.2, lambda: webbrowser.open(f"http://127.0.0.1:{port}")).start()
    app.run(debug=False, port=port)


if __name__ == "__main__":
    starten()
