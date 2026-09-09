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

from dash import (MATCH, Dash, Input, Output, State, callback_context, dcc, html,
                  no_update)

from ..creo import starten as creo_starten
from ..formate import export
from ..geometrie.profil import katalogprofile, profil_fuer
from ..spec.modell import (Fertigung, ProfilAusDatei, ProfilNaca,
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

_KNOPF = {"width": "32px", "flexShrink": 0, "border": "1px solid #ccc",
          "background": "#f7f7f7", "cursor": "pointer", "fontSize": "16px",
          "lineHeight": "1", "padding": "5px 0", "userSelect": "none"}


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
                    style={**_KNOPF, "borderRadius": "4px 0 0 4px"}),
        dcc.Input(id=wert(feld), type="number", value=vorgabe, step="any",
                  min=minimum, max=maximum, debounce=False,
                  style={"flex": 1, "minWidth": 0, "padding": "5px",
                         "fontSize": "13px", "textAlign": "center",
                         "border": "1px solid #ccc", "borderLeft": "none",
                         "borderRight": "none"}),
        html.Button("+", id={"typ": "plus", "feld": feld}, n_clicks=0,
                    style={**_KNOPF, "borderRadius": "0 4px 4px 0"}),
    ], style={"display": "flex"})


# ------------------------------------------------------------------ Bausteine

def _feld(beschriftung: str, komponente, hinweis: str = "") -> html.Div:
    kinder = []
    if beschriftung:
        kinder.append(html.Label(beschriftung, style={
            "fontSize": "13px", "fontWeight": 600, "display": "block",
            "marginBottom": "3px"}))
    kinder.append(komponente)
    if hinweis:
        kinder.append(html.Div(hinweis, style={"fontSize": "11px", "color": "#777",
                                               "marginTop": "3px"}))
    return html.Div(kinder, style={"marginBottom": "14px"})


def _karte(kinder, **stil) -> html.Div:
    grund = {"background": "white", "border": "1px solid #e0e0e0",
             "borderRadius": "6px", "padding": "14px", "marginBottom": "14px"}
    grund.update(stil)
    return html.Div(kinder, style=grund)


def _ueberschrift(text: str) -> html.H4:
    return html.H4(text, style={"marginTop": 0, "marginBottom": "10px",
                                "fontSize": "15px"})


_GRAPH = dict(config={"displaylogo": False, "displayModeBar": False})


# ------------------------------------------------------------------- Ansichten

def _steuerung() -> html.Div:
    return html.Div([
        _karte([
            _ueberschrift("Profil"),
            _feld("Quelle", dcc.RadioItems(
                id="quelle", value="datei",
                options=[{"label": " Katalog", "value": "datei"},
                         {"label": " NACA", "value": "naca"}],
                inline=True, style={"fontSize": "13px"})),
            html.Div(id="quelle-katalog", children=[
                _feld("Katalogprofil", dcc.Dropdown(
                    id="katalogdatei", options=katalogprofile(),
                    value="e423.dat", clearable=False,
                    style={"fontSize": "13px"}))]),
            html.Div(id="quelle-naca", children=[
                _feld("Wölbung [%]",
                      _zahlenfeld("naca-woelbung", 4.0, 0.5, -25.0, 25.0),
                      "Negativ wölbt nach unten. Über 9,5 % verlässt man die "
                      "Standard-NACA-Familie — die Formel gilt weiter, "
                      "Literaturdaten gibt es dann aber keine."),
                _feld("Wölbungslage [%]",
                      _zahlenfeld("naca-lage", 40.0, 5.0, 5.0, 95.0)),
                _feld("Dicke [%]", _zahlenfeld("naca-dicke", 12.0, 0.5, 1.0, 40.0)),
            ]),
        ]),
        _karte([
            _ueberschrift("Wirkrichtung"),
            _feld("", dcc.RadioItems(
                id="wirkrichtung", value="abtrieb",
                options=[{"label": " Abtrieb", "value": "abtrieb"},
                         {"label": " Auftrieb (Bullwing)", "value": "auftrieb"}],
                style={"fontSize": "13px"}),
                "Katalogprofile sind für Auftrieb gezeichnet — sie stammen aus "
                "dem Flugzeugbau. Für Abtrieb, den Normalfall am Rennwagen, "
                "werden sie gespiegelt. Auftrieb wählt man für Bullwings, die "
                "die Aerobalance nach hinten verschieben."),
        ]),
        _karte([
            _ueberschrift("Geometrie"),
            _feld("Sehnenlänge [mm]", _zahlenfeld("sehne", 250.0, 5.0, 1.0, 5000.0),
                  "Beliebige Zahl, auch mit Komma. Die Knöpfe springen in 5-mm-Schritten."),
            _feld("Anstellwinkel [°]", _zahlenfeld("aoa", -4.0, 0.5, -60.0, 60.0),
                  "Negativ = Nase nach unten."),
        ]),
        _karte([
            _ueberschrift("Fertigung"),
            _feld("Verfahren", dcc.Dropdown(
                id="verfahren", clearable=False, value="prepreg",
                options=["nasslaminat", "prepreg", "autoklav", "unbestimmt"],
                style={"fontSize": "13px"}),
                "Setzt die drei Werte darunter auf Startwerte für dieses "
                "Verfahren. Änderst du sie, merkt sich das Werkzeug sie und "
                "stellt sie beim nächsten Wechsel wieder her."),
            _feld("Wandstärke je Haut [mm]",
                  _zahlenfeld("wandstaerke", 0.6, 0.1, 0.05, 20.0)),
            _feld("Kerndicke [mm]", _zahlenfeld("kern", 3.0, 0.5, 0.0, 100.0),
                  "0 = keine. Der Kern wird nur dort eingelegt, wo er hineinpasst."),
            _feld("Klebespalt [mm]", _zahlenfeld("klebespalt", 0.2, 0.05, 0.0, 5.0),
                  "Bestimmt zusammen mit der Wandstärke die gebaute Hinterkante."),
        ]),
    ])


def _ansicht_profil() -> html.Div:
    return html.Div([
        html.Div(_steuerung(), style={"width": "300px", "flexShrink": 0,
                                      "marginRight": "16px"}),
        html.Div([
            _karte([html.Div(id="ampel")]),
            _karte([dcc.Graph(id="fig-kontur", **_GRAPH)]),
            html.Div([
                html.Div(_karte([dcc.Graph(id="fig-dicke", **_GRAPH)]),
                         style={"flex": 1, "marginRight": "14px", "minWidth": 0}),
                html.Div(_karte([dcc.Graph(id="fig-kruemmung", **_GRAPH)]),
                         style={"flex": 1, "minWidth": 0}),
            ], style={"display": "flex"}),
            _karte([dcc.Graph(id="fig-zonen", **_GRAPH)]),
        ], style={"flex": 1, "minWidth": 0}),
    ], style={"display": "flex", "alignItems": "flex-start"})


def _ansicht_creo() -> html.Div:
    return html.Div([
        html.Div([
            _karte([
                _ueberschrift("Export nach Creo"),
                _feld("Zielordner", dcc.Input(
                    id="exportordner", type="text", value="export",
                    style={"width": "100%", "padding": "5px", "fontSize": "13px",
                           "border": "1px solid #ccc", "borderRadius": "4px"}),
                    "Relativ zum Projektordner."),
                _feld("Toleranz [mm]",
                      _zahlenfeld("toleranz", 0.005, 0.001, 0.0005, 0.5),
                      "Creos Modellgenauigkeit liegt bei 0,010 mm."),
                html.Button("IBL schreiben", id="btn-export", n_clicks=0,
                            style={"width": "100%", "padding": "9px",
                                   "background": FARBE_AKZENT, "color": "white",
                                   "border": "none", "borderRadius": "4px",
                                   "fontSize": "14px", "cursor": "pointer"}),
                html.Button("Schreiben und in Creo öffnen", id="btn-creo", n_clicks=0,
                            style={"width": "100%", "padding": "9px",
                                   "marginTop": "8px", "background": "white",
                                   "color": FARBE_AKZENT,
                                   "border": f"1px solid {FARBE_AKZENT}",
                                   "borderRadius": "4px", "fontSize": "14px",
                                   "cursor": "pointer"}),
                html.Div(id="creo-status", style={"fontSize": "12px",
                                                  "marginTop": "10px"}),
            ]),
        ], style={"width": "300px", "flexShrink": 0, "marginRight": "16px"}),
        html.Div([
            _karte([html.Div(id="export-info")]),
            _karte([_ueberschrift("Diese Punkte gehen nach Creo"),
                    dcc.Graph(id="fig-export", **_GRAPH)]),
            _karte([_ueberschrift("Vorschau der IBL-Datei"),
                    html.Pre(id="ibl-vorschau",
                             style={"fontSize": "11px", "background": "#fafafa",
                                    "padding": "10px", "borderRadius": "4px",
                                    "maxHeight": "300px", "overflow": "auto",
                                    "margin": 0})]),
        ], style={"flex": 1, "minWidth": 0}),
    ], style={"display": "flex", "alignItems": "flex-start"})


def _ansicht_projekt() -> html.Div:
    return html.Div([
        _karte([_ueberschrift("Aktueller Stand"),
                html.Div(id="projekt-info", style={"fontSize": "13px"})]),
        _karte([
            _ueberschrift("AeroSpec"),
            html.Div("Das hier ist der gesamte Zustand des Programms. Genau diese "
                     "Datei wird gespeichert und liegt im Git.",
                     style={"fontSize": "12px", "color": "#777", "marginBottom": "8px"}),
            html.Pre(id="spec-yaml",
                     style={"fontSize": "11px", "background": "#fafafa",
                            "padding": "10px", "borderRadius": "4px",
                            "maxHeight": "500px", "overflow": "auto", "margin": 0}),
        ]),
    ])


def layout() -> html.Div:
    return html.Div([
        dcc.Store(id="spec"),
        # Merkt sich je Verfahren die zuletzt benutzten Werte. Bewusst nur
        # Bedienkomfort und nicht Teil des Spec: Es beschreibt nicht den
        # Entwurf, sondern die Gewohnheit des Bearbeiters.
        dcc.Store(id="verfahrensspeicher", data={}),
        html.Div([
            html.Div([
                html.Span("Aero Studio", style={"fontSize": "19px", "fontWeight": 700}),
                html.Span(id="kopf-hash", style={"fontSize": "12px", "color": "#777",
                                                 "marginLeft": "12px"}),
            ]),
            html.Div([
                html.Span(id="kopf-status", style={"fontSize": "12px",
                                                   "marginRight": "12px"}),
                html.Button("Spec speichern", id="btn-speichern", n_clicks=0,
                            style={"padding": "6px 14px", "fontSize": "13px",
                                   "cursor": "pointer", "borderRadius": "4px",
                                   "border": "1px solid #bbb", "background": "white"}),
            ]),
        ], style={"display": "flex", "justifyContent": "space-between",
                  "alignItems": "center", "padding": "10px 18px",
                  "background": "white", "borderBottom": "1px solid #e0e0e0"}),
        dcc.Tabs(id="reiter", value="profil", children=[
            dcc.Tab(label="Profil", value="profil"),
            dcc.Tab(label="Creo", value="creo"),
            dcc.Tab(label="Projekt", value="projekt"),
        ]),
        # Alle Ansichten stehen dauerhaft hier, der Reiter blendet nur um.
        html.Div([
            html.Div(_ansicht_profil(), id="view-profil"),
            html.Div(_ansicht_creo(), id="view-creo"),
            html.Div(_ansicht_projekt(), id="view-projekt"),
        ], style={"padding": "16px"}),
    ], style={"fontFamily": "Segoe UI, system-ui, sans-serif",
              "background": "#f5f5f5", "minHeight": "100vh"})


# ------------------------------------------------------------------ Callbacks

app = Dash(__name__, title="Aero Studio")
app.layout = layout


@app.callback(Output("view-profil", "style"), Output("view-creo", "style"),
              Output("view-projekt", "style"), Input("reiter", "value"))
def _reiter_umblenden(reiter):
    an, aus = {"display": "block"}, {"display": "none"}
    return tuple(an if reiter == r else aus for r in ("profil", "creo", "projekt"))


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


def _baue_spec(quelle, katalogdatei, w, lage, dicke, wirkrichtung, sehne, aoa,
               verfahren, wandstaerke, kern, klebespalt) -> AeroSpec:
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
    element.wirkrichtung = Wirkrichtung(wirkrichtung or "abtrieb")
    element.sehne = float(sehne or 250.0)
    element.anstellwinkel = float(0.0 if aoa is None else aoa)
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


def _ampel(profil, sehne, fertigung, befunde) -> html.Div:
    kennwerte = html.Div([
        html.Span(f"Dicke {profil.max_dicke*100:.1f} % bei "
                  f"{profil.max_dicke_bei*100:.0f} %"),
        html.Span(f"Wölbung {profil.max_woelbung*100:.1f} %",
                  style={"marginLeft": "18px"}),
        html.Span(f"Nasenradius {profil.nasenradius()*sehne:.1f} mm",
                  style={"marginLeft": "18px"}),
        html.Span(f"{len(profil.punkte)} Punkte in der Quelle",
                  style={"marginLeft": "18px", "color": "#777"}),
    ], style={"fontSize": "12px", "color": "#555", "marginBottom": "10px"})

    zeilen = []
    for b in befunde:
        farbe = FARBE_OK if b.ok else (FARBE_FEHLER if b.stufe == "fehler"
                                       else FARBE_HINWEIS)
        zeichen = "✓" if b.ok else ("✗" if b.stufe == "fehler" else "!")
        kopf = [html.Span(f"{zeichen} ", style={"color": farbe, "fontWeight": 700}),
                html.Span(b.pruefung, style={"fontWeight": 600}),
                html.Span(f"  {b.ist:.2f} {b.einheit}, gefordert ≥ {b.soll:.2f}",
                          style={"color": "#555"})]
        if b.regel:
            kopf.append(html.Span(f"  [{b.regel}]", style={"color": "#999"}))
        eintrag = [html.Div(kopf)]
        if b.hinweis and not b.ok:
            eintrag.append(html.Div(b.hinweis, style={
                "fontSize": "11px", "color": "#777", "marginLeft": "16px",
                "marginTop": "2px"}))
        zeilen.append(html.Div(eintrag, style={"marginBottom": "7px",
                                               "fontSize": "13px"}))

    blockiert = any(b.blockiert for b in befunde)
    return html.Div([
        html.Div("Nicht baubar in dieser Form" if blockiert
                 else "Regel- und fertigungskonform",
                 style={"fontWeight": 700, "marginBottom": "8px",
                        "color": FARBE_FEHLER if blockiert else FARBE_OK}),
        kennwerte, html.Div(zeilen)])


def _fehlerkarte(fehler: Exception) -> html.Div:
    return html.Div([
        html.Div("Das lässt sich so nicht berechnen.",
                 style={"fontWeight": 700, "color": FARBE_FEHLER}),
        html.Div(str(fehler), style={"fontSize": "13px", "marginTop": "6px"}),
        html.Details([html.Summary("Einzelheiten",
                                   style={"fontSize": "12px", "cursor": "pointer"}),
                      html.Pre(traceback.format_exc(),
                               style={"fontSize": "10px", "overflow": "auto"})],
                     style={"marginTop": "8px"}),
    ])


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
        return html.Span(f"gespeichert: {SPEC_VORGABE.name}", style={"color": FARBE_OK})
    except Exception as fehler:
        return html.Span(f"Speichern fehlgeschlagen: {fehler}",
                         style={"color": FARBE_FEHLER})


@app.callback(Output("export-info", "children"), Output("ibl-vorschau", "children"),
              Output("fig-export", "figure"),
              Output("creo-status", "children"),
              Input("spec", "data"), Input(wert("toleranz"), "value"),
              Input("exportordner", "value"), Input("btn-export", "n_clicks"),
              Input("btn-creo", "n_clicks"))
def _export(daten, toleranz, ordner, n_export, n_creo):
    leer = {"data": [], "layout": {"height": 200}}
    if not daten:
        return "", "", leer, ""
    try:
        spec = AeroSpec.model_validate(daten)
        element = spec.elemente[0]
        profil = profil_fuer(element)

        plan = export.plane_element(profil, element.sehne, element.anstellwinkel,
                                    float(toleranz or 0.005))
        ziel = PROJEKT / (ordner or "export") / f"{element.id}.ibl"

        # Beide Schaltflaechen schreiben - die zweite oeffnet zusaetzlich Creo.
        nach_creo = _ausgeloest_von("btn-creo")
        geschrieben = None
        if _ausgeloest_von("btn-export") or nach_creo:
            export.schreibe(plan, ziel, kommentare=[
                f"Aero Studio - {element.id}",
                f"Profil {profil.name}, Sehne {element.sehne:.1f} mm, "
                f"Anstellwinkel {element.anstellwinkel:+.1f} Grad",
                f"AERO_SPEC_HASH: {spec.hash()}",
            ])
            geschrieben = ziel

        status = _creo_oeffnen(ziel) if nach_creo else ""
        return (_exportinfo(plan, ziel, geschrieben), export.vorschau(plan),
                darstellung.exportpunkte(plan, profil.name), status)
    except Exception as fehler:
        return _fehlerkarte(fehler), "", leer, ""


def _creo_oeffnen(ziel: Path):
    """Startet Creo mit der Datei und macht das Ergebnis lesbar."""
    ergebnis = creo_starten.oeffne(ziel)
    farbe = FARBE_OK if ergebnis.gestartet else FARBE_HINWEIS
    teile = [html.Div(ergebnis.meldung, style={"fontWeight": 600, "color": farbe})]
    if ergebnis.hinweis:
        teile.append(html.Div(ergebnis.hinweis, style={"color": "#666",
                                                       "marginTop": "3px"}))
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


def _exportinfo(plan, ziel: Path, geschrieben: Path | None) -> html.Div:
    zeilen = [
        html.Div([html.Span("Punktzahl: ", style={"fontWeight": 600}),
                  html.Span(f"{plan.punktzahl} je Seite, berechnet für "
                            f"{plan.toleranz_mm:.4f} mm Toleranz "
                            f"({plan.punkte_gesamt} Punkte gesamt)")]),
        html.Div(f"Die geforderten {plan.toleranz_gefordert:.4f} mm waren nicht "
                 f"erreichbar — gerechnet wurde mit {plan.toleranz_mm:.4f} mm.",
                 style={"color": FARBE_HINWEIS, "marginTop": "4px"})
        if plan.gelockert else html.Div(),
        html.Div([html.Span("Sektionen: ", style={"fontWeight": 600}),
                  html.Span("2 — Ober- und Unterseite getrennt, damit der Spline "
                            "an der Nase keine Beule bekommt")]),
        html.Div([html.Span("Koordinaten: ", style={"fontWeight": 600}),
                  html.Span("bereits in das System der Creo-Vorlage gedreht — "
                            "in Creo ist nichts vorzubereiten")]),
        html.Div([html.Span("Ziel: ", style={"fontWeight": 600}),
                  html.Span(str(ziel))], style={"color": "#777"}),
    ]
    if geschrieben:
        zeilen.append(html.Div(f"Geschrieben: {geschrieben}",
                               style={"color": FARBE_OK, "marginTop": "8px",
                                      "fontWeight": 600}))
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
