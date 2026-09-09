"""
Aero Studio - Oberflaeche.

Aufruf:
    python -m aerostudio.ui.app
oder per Doppelklick auf "Aero Studio.bat" im Projektordner.

Zum Zustand: Der Bearbeitungsstand liegt waehrend der Sitzung in einem
einzigen dcc.Store, nicht verteilt ueber die Bedienelemente. Die Wahrheit auf
der Platte ist die YAML-Datei; Speichern ist ein bewusster Schritt, wie in
jedem Editor. Damit gilt weiter, was von Anfang an gelten sollte: Es gibt
genau eine Stelle, an der der Entwurf steht.

Die Callbacks bleiben duenn - sie nehmen Eingaben entgegen, rufen eine
Funktion aus aerostudio.* auf und geben das Ergebnis zurueck. Fachlogik steht
hier keine.
"""

from __future__ import annotations

import traceback
import webbrowser
from pathlib import Path
from threading import Timer

from dash import Dash, Input, Output, State, callback_context, dcc, html, no_update

from ..geometrie.profil import katalogprofile, profil_fuer
from ..spec.modell import Fertigung, ProfilAusDatei, ProfilNaca
from ..formate import export
from ..spec.projekt import AeroSpec
from . import darstellung

PROJEKT = Path(__file__).resolve().parents[2]
SPEC_VORGABE = PROJEKT / "specs" / "aktuell.yaml"

FARBE_OK = "#2e7d32"
FARBE_HINWEIS = "#ef6c00"
FARBE_FEHLER = "#c62828"


# ------------------------------------------------------------------ Bausteine

def _feld(beschriftung: str, komponente, hinweis: str = "") -> html.Div:
    kinder = [html.Label(beschriftung, style={"fontSize": "13px", "fontWeight": 600,
                                              "display": "block", "marginBottom": "3px"}),
              komponente]
    if hinweis:
        kinder.append(html.Div(hinweis, style={"fontSize": "11px", "color": "#777",
                                               "marginTop": "2px"}))
    return html.Div(kinder, style={"marginBottom": "14px"})


def _zahl(kennung: str, wert: float, schritt: float = 0.1,
          minimum: float = 0.0) -> dcc.Input:
    return dcc.Input(id=kennung, type="number", value=wert, step=schritt, min=minimum,
                     style={"width": "100%", "padding": "5px", "fontSize": "13px"})


def _karte(kinder, **stil) -> html.Div:
    grund = {"background": "white", "border": "1px solid #e0e0e0",
             "borderRadius": "6px", "padding": "14px", "marginBottom": "14px"}
    grund.update(stil)
    return html.Div(kinder, style=grund)


# ------------------------------------------------------------------- Aufbau

def _steuerung() -> html.Div:
    return html.Div([
        _karte([
            html.H4("Profil", style={"marginTop": 0, "fontSize": "15px"}),
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
                _feld("Wölbung [%]", _zahl("naca-woelbung", 4.0, 0.5)),
                _feld("Wölbungslage [%]", _zahl("naca-lage", 40.0, 5.0)),
                _feld("Dicke [%]", _zahl("naca-dicke", 12.0, 0.5)),
            ]),
        ]),
        _karte([
            html.H4("Geometrie", style={"marginTop": 0, "fontSize": "15px"}),
            _feld("Sehnenlänge [mm]", _zahl("sehne", 250.0, 5.0, 10.0)),
            _feld("Anstellwinkel [°]", _zahl("aoa", -4.0, 0.5, -90.0),
                  "Negativ = Nase nach unten."),
            _feld("", dcc.Checklist(
                id="invertiert", value=["ja"], style={"fontSize": "13px"},
                options=[{"label": " Profil spiegeln (Abtrieb)", "value": "ja"}]),
                "Katalogprofile sind für Auftrieb gezeichnet. Ohne Spiegelung "
                "drückt der Flügel das Auto nach oben."),
        ]),
        _karte([
            html.H4("Fertigung", style={"marginTop": 0, "fontSize": "15px"}),
            _feld("Verfahren", dcc.Dropdown(
                id="verfahren", clearable=False, value="prepreg",
                options=["nasslaminat", "prepreg", "autoklav", "unbestimmt"],
                style={"fontSize": "13px"})),
            _feld("Wandstärke je Haut [mm]", _zahl("wandstaerke", 0.6, 0.1, 0.05)),
            _feld("Kerndicke [mm]", _zahl("kern", 3.0, 0.5),
                  "0 = keine. Der Kern wird nur dort eingelegt, wo er hineinpasst."),
            _feld("Klebespalt [mm]", _zahl("klebespalt", 0.2, 0.05),
                  "Bestimmt zusammen mit der Wandstärke die gebaute Hinterkante."),
        ]),
    ])


def _ansicht_profil() -> html.Div:
    return html.Div([
        html.Div(_steuerung(), style={"width": "290px", "flexShrink": 0,
                                      "marginRight": "16px"}),
        html.Div([
            _karte([html.Div(id="ampel")]),
            _karte([dcc.Graph(id="fig-kontur", config={"displaylogo": False})]),
            html.Div([
                html.Div(_karte([dcc.Graph(id="fig-dicke", config={"displaylogo": False})]),
                         style={"flex": 1, "marginRight": "14px"}),
                html.Div(_karte([dcc.Graph(id="fig-kruemmung", config={"displaylogo": False})]),
                         style={"flex": 1}),
            ], style={"display": "flex"}),
            _karte([dcc.Graph(id="fig-zonen", config={"displaylogo": False})]),
        ], style={"flex": 1, "minWidth": 0}),
    ], style={"display": "flex", "alignItems": "flex-start"})


def _ansicht_creo() -> html.Div:
    return html.Div([
        html.Div([
            _karte([
                html.H4("Export nach Creo", style={"marginTop": 0, "fontSize": "15px"}),
                _feld("Zielordner", dcc.Input(
                    id="exportordner", type="text", value="export",
                    style={"width": "100%", "padding": "5px", "fontSize": "13px"}),
                    "Relativ zum Projektordner."),
                _feld("Toleranz [mm]", _zahl("toleranz", 0.005, 0.001, 0.0005),
                      "Creos Modellgenauigkeit liegt bei 0,010 mm."),
                html.Button("IBL schreiben", id="btn-export", n_clicks=0,
                            style={"width": "100%", "padding": "9px",
                                   "background": "#253494", "color": "white",
                                   "border": "none", "borderRadius": "4px",
                                   "fontSize": "14px", "cursor": "pointer"}),
            ]),
        ], style={"width": "290px", "flexShrink": 0, "marginRight": "16px"}),
        html.Div([
            _karte([html.Div(id="export-info")]),
            _karte([html.H4("Vorschau der IBL-Datei",
                            style={"marginTop": 0, "fontSize": "15px"}),
                    html.Pre(id="ibl-vorschau",
                             style={"fontSize": "11px", "background": "#fafafa",
                                    "padding": "10px", "borderRadius": "4px",
                                    "maxHeight": "420px", "overflow": "auto",
                                    "margin": 0})]),
        ], style={"flex": 1, "minWidth": 0}),
    ], style={"display": "flex", "alignItems": "flex-start"})


def _ansicht_projekt() -> html.Div:
    return html.Div([
        _karte([
            html.H4("Aktueller Stand", style={"marginTop": 0, "fontSize": "15px"}),
            html.Div(id="projekt-info", style={"fontSize": "13px"}),
        ]),
        _karte([
            html.H4("AeroSpec", style={"marginTop": 0, "fontSize": "15px"}),
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
        dcc.Store(id="spec", data=AeroSpec.beispiel().model_dump(mode="json")),
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
        html.Div(id="inhalt", style={"padding": "16px"}),
    ], style={"fontFamily": "Segoe UI, system-ui, sans-serif",
              "background": "#f5f5f5", "minHeight": "100vh"})


# ------------------------------------------------------------------ Callbacks

app = Dash(__name__, title="Aero Studio", suppress_callback_exceptions=True)
app.layout = layout


@app.callback(Output("inhalt", "children"), Input("reiter", "value"))
def _reiter_wechseln(reiter):
    return {"profil": _ansicht_profil, "creo": _ansicht_creo,
            "projekt": _ansicht_projekt}[reiter]()


@app.callback(Output("quelle-katalog", "style"), Output("quelle-naca", "style"),
              Input("quelle", "value"))
def _quelle_umschalten(quelle):
    an, aus = {"display": "block"}, {"display": "none"}
    return (an, aus) if quelle == "datei" else (aus, an)


def _baue_spec(quelle, katalogdatei, w, lage, dicke, sehne, aoa, invertiert,
               verfahren, wandstaerke, kern, klebespalt) -> AeroSpec:
    """Sammelt die Bedienelemente zu einem gueltigen Spec.

    Einzige Stelle, an der aus Widgets Fachdaten werden - alles Weitere
    arbeitet nur noch mit dem Spec.
    """
    spec = AeroSpec.beispiel()
    if quelle == "naca":
        spec.elemente[0].profil = ProfilNaca(
            woelbung=(w or 0) / 100.0, woelbungslage=(lage or 40) / 100.0,
            dicke=(dicke or 12) / 100.0)
    else:
        spec.elemente[0].profil = ProfilAusDatei(datei=katalogdatei or "e423.dat")
    spec.elemente[0].sehne = float(sehne or 250.0)
    spec.elemente[0].anstellwinkel = float(aoa or 0.0)
    spec.elemente[0].invertiert = bool(invertiert)
    spec.fertigung = Fertigung(
        verfahren=verfahren or "unbestimmt",
        wandstaerke=float(wandstaerke or 0.6),
        kern=float(kern or 0.0),
        klebespalt=float(klebespalt or 0.2))
    return spec


_EINGABEN = [Input("quelle", "value"), Input("katalogdatei", "value"),
             Input("naca-woelbung", "value"), Input("naca-lage", "value"),
             Input("naca-dicke", "value"), Input("sehne", "value"),
             Input("aoa", "value"), Input("invertiert", "value"),
             Input("verfahren", "value"),
             Input("wandstaerke", "value"), Input("kern", "value"),
             Input("klebespalt", "value")]


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

        befunde = profil.pruefe_fertigung(fert, sehne)
        return (spec.model_dump(mode="json"),
                _ampel(profil, sehne, fert, befunde),
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
        farbe = FARBE_OK if b.ok else (FARBE_FEHLER if b.stufe == "fehler" else FARBE_HINWEIS)
        zeichen = "✓" if b.ok else ("✗" if b.stufe == "fehler" else "!")
        text = [html.Span(f"{zeichen} ", style={"color": farbe, "fontWeight": 700}),
                html.Span(b.pruefung, style={"fontWeight": 600}),
                html.Span(f"  {b.ist:.2f} {b.einheit}, gefordert ≥ {b.soll:.2f}",
                          style={"color": "#555"})]
        if b.regel:
            text.append(html.Span(f"  [{b.regel}]", style={"color": "#999"}))
        eintrag = [html.Div(text)]
        if b.hinweis and not b.ok:
            eintrag.append(html.Div(b.hinweis, style={
                "fontSize": "11px", "color": "#777", "marginLeft": "16px",
                "marginTop": "2px"}))
        zeilen.append(html.Div(eintrag, style={"marginBottom": "7px", "fontSize": "13px"}))

    blockiert = any(b.blockiert for b in befunde)
    kopf = ("Regel- und fertigungskonform" if not blockiert
            else "Nicht baubar in dieser Form")
    return html.Div([
        html.Div(kopf, style={"fontWeight": 700, "marginBottom": "8px",
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


# Getrennte Callbacks fuer Kopfzeile und Projektreiter.
#
# Zusammen in einem waeren sie ein Fehler: Der Projektreiter existiert nur,
# solange er ausgewaehlt ist. Ein Callback, der gleichzeitig in die immer
# vorhandene Kopfzeile und in ein nur zeitweise vorhandenes Element schreibt,
# scheitert bei abgeschaltetem suppress_callback_exceptions - und mit ihm
# still, also unbemerkt. Genau das ist beim ersten Start passiert: Der Hash
# blieb leer.
@app.callback(Output("kopf-hash", "children"), Input("spec", "data"))
def _kopfzeile(daten):
    if not daten:
        return ""
    return f"Spec {AeroSpec.model_validate(daten).hash()}"


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
        html.Div(f"Datei: {SPEC_VORGABE}", style={"color": "#777",
                                                  "fontSize": "12px"}),
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
              Input("spec", "data"), Input("toleranz", "value"),
              Input("exportordner", "value"), Input("btn-export", "n_clicks"))
def _export(daten, toleranz, ordner, n_clicks):
    if not daten:
        return "", ""
    try:
        spec = AeroSpec.model_validate(daten)
        element = spec.elemente[0]
        profil = profil_fuer(element)

        plan = export.plane_element(profil, element.sehne, element.anstellwinkel,
                                    float(toleranz or 0.005))
        ziel = PROJEKT / (ordner or "export") / f"{element.id}.ibl"

        geschrieben = None
        if _ausgeloest_von("btn-export"):
            export.schreibe(plan, ziel, kommentare=[
                f"Aero Studio - {element.id}",
                f"Profil {profil.name}, Sehne {element.sehne:.1f} mm, "
                f"Anstellwinkel {element.anstellwinkel:+.1f} Grad",
                f"AERO_SPEC_HASH: {spec.hash()}",
            ])
            geschrieben = ziel

        return _exportinfo(plan, ziel, geschrieben), export.vorschau(plan)
    except Exception as fehler:
        return _fehlerkarte(fehler), ""


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


def starten(port: int = 8051, browser: bool = True) -> None:
    if browser:
        Timer(1.2, lambda: webbrowser.open(f"http://127.0.0.1:{port}")).start()
    app.run(debug=False, port=port)


if __name__ == "__main__":
    starten()
