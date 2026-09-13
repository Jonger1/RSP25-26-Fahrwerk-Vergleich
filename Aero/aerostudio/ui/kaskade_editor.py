"""Interaktiver Editor fuer segmentierte MehrElement-Fluegel.

Der Editor trennt bewusst zwischen zwei Ebenen:

* Eine **Gruppe** ist ein lokaler 2D-Kaskadenquerschnitt. Dort gibt es genau
  ein Hauptelement und null bis fuenf Flaps.
* Jedes Element bekommt ausserdem einen eigenen Spannweitenbereich. Dadurch
  kann ein Fluegel links und rechts getrennt sein, einen Mittelteil auslassen
  oder auf einem anderen Fahrzeugbereich liegen.

Das Datenmodell ist damit bereits auf Frontfluegel, Seitenkasten-Fluegel,
Bullwings und Heckfluegel vorbereitet. Eine echte 3D-Traglinienrechnung ueber
mehrere Gruppen ist bewusst noch nicht behauptet; die lokale Kaskadenrechnung
bleibt zweidimensional.

Aufruf::

    python -m aerostudio.ui.kaskade_editor
"""

from __future__ import annotations

import traceback
import webbrowser
from threading import Timer

import plotly.graph_objects as go
from dash import Dash, Input, Output, State, dash_table, dcc, html

from ..aero import kaskade as aero_k
from ..geometrie import kaskade as geo_k
from ..geometrie.fluegel_system import FluegelElement, FluegelSystem, Spannweitenbereich
from ..geometrie.profil import KATALOG, Profil, katalogoptionen


MAX_ELEMENTE = 6

ELEMENT_SPALTEN = [
    {"id": "name", "name": "Name"},
    {"id": "gruppe", "name": "Gruppe"},
    {"id": "rolle", "name": "Rolle"},
    {"id": "profil", "name": "Profil"},
    {"id": "sehne_faktor", "name": "Sehne / Hauptsehne", "type": "numeric"},
    {"id": "winkel_relativ", "name": "Winkel relativ [°]", "type": "numeric"},
    {"id": "spalt", "name": "Gap / Hauptsehne", "type": "numeric"},
    {"id": "ueberlappung", "name": "Overlap / Hauptsehne", "type": "numeric"},
    {"id": "y_von", "name": "y von [mm]", "type": "numeric"},
    {"id": "y_bis", "name": "y bis [mm]", "type": "numeric"},
    {"id": "x", "name": "x [mm]", "type": "numeric"},
    {"id": "z", "name": "z [mm]", "type": "numeric"},
]


def vorgabe_zeilen(anzahl: int = 1) -> list[dict]:
    """Startwerte fuer bis zu sechs Elemente."""
    anzahl = max(0, min(int(anzahl), MAX_ELEMENTE))
    basis = [
        {"name": "Hauptelement", "gruppe": "Frontfluegel", "rolle": "Haupt",
         "profil": "e423.dat", "sehne_faktor": 1.00, "winkel_relativ": -4.0,
         "spalt": 0.020, "ueberlappung": 0.020, "y_von": -600.0, "y_bis": 600.0,
         "x": 0.0, "z": 90.0},
        {"name": "Flap 1", "gruppe": "Frontfluegel", "rolle": "Flap",
         "profil": "e58.dat", "sehne_faktor": 0.35, "winkel_relativ": -18.0,
         "spalt": 0.020, "ueberlappung": 0.020, "y_von": -600.0, "y_bis": 600.0,
         "x": 0.0, "z": 90.0},
        {"name": "Flap 2", "gruppe": "Frontfluegel", "rolle": "Flap",
         "profil": "e58.dat", "sehne_faktor": 0.28, "winkel_relativ": -14.0,
         "spalt": 0.018, "ueberlappung": 0.020, "y_von": -600.0, "y_bis": 600.0,
         "x": 0.0, "z": 90.0},
        {"name": "Flap 3", "gruppe": "Frontfluegel", "rolle": "Flap",
         "profil": "e58.dat", "sehne_faktor": 0.22, "winkel_relativ": -12.0,
         "spalt": 0.016, "ueberlappung": 0.018, "y_von": -600.0, "y_bis": 600.0,
         "x": 0.0, "z": 90.0},
        {"name": "Bullwing", "gruppe": "Bullwing", "rolle": "Haupt",
         "profil": "e423.dat", "sehne_faktor": 1.00, "winkel_relativ": -8.0,
         "spalt": 0.020, "ueberlappung": 0.020, "y_von": -170.0, "y_bis": 170.0,
         "x": 850.0, "z": 180.0},
        {"name": "Heckfluegel", "gruppe": "Heckfluegel", "rolle": "Haupt",
         "profil": "e423.dat", "sehne_faktor": 1.00, "winkel_relativ": -6.0,
         "spalt": 0.020, "ueberlappung": 0.020, "y_von": -550.0, "y_bis": 550.0,
         "x": 1500.0, "z": 550.0},
    ]
    return basis[:anzahl]


def _profil(datei: str, abtrieb: bool = True) -> Profil:
    p = Profil.aus_dat(KATALOG / datei)
    return p.gespiegelt() if abtrieb else p


def _float(row: dict, key: str, default: float = 0.0) -> float:
    value = row.get(key)
    return default if value in (None, "") else float(value)


def system_aus_zeilen(zeilen: list[dict] | None) -> FluegelSystem:
    """Validiert die Tabelle und bildet das allgemeine 3D-fähige Modell."""
    rows = list(zeilen or [])
    if len(rows) > MAX_ELEMENTE:
        raise ValueError(f"Maximal {MAX_ELEMENTE} Fluegelelemente sind erlaubt.")

    elemente = []
    for nummer, row in enumerate(rows, start=1):
        y_von = _float(row, "y_von")
        y_bis = _float(row, "y_bis")
        if y_bis <= y_von:
            raise ValueError(f"Zeile {nummer}: y bis muss groesser als y von sein.")
        sehne_faktor = _float(row, "sehne_faktor", 1.0)
        if not 0.05 <= sehne_faktor <= 1.5:
            raise ValueError(f"Zeile {nummer}: Sehnenfaktor muss zwischen 0,05 und 1,5 liegen.")
        winkel = _float(row, "winkel_relativ")
        if not -70.0 <= winkel <= 40.0:
            raise ValueError(f"Zeile {nummer}: Winkel ausserhalb des Editorbereichs.")

        elemente.append(FluegelElement(
            name=str(row.get("name") or f"Element {nummer}"),
            gruppe=str(row.get("gruppe") or "Frontfluegel"),
            profil=str(row.get("profil") or "e423.dat"),
            sehne_mm=250.0 * sehne_faktor,
            winkel_grad=winkel,
            spannweite=Spannweitenbereich(y_von, y_bis),
            x_mm=_float(row, "x"),
            z_mm=_float(row, "z"),
        ))

    return FluegelSystem(elemente)


def zeilen_fuer_gruppe(zeilen: list[dict], gruppe: str) -> list[dict]:
    return [dict(row) for row in zeilen if str(row.get("gruppe") or "") == gruppe]


def flaps_aus_zeilen(zeilen: list[dict] | None, abtrieb: bool = True) -> tuple[str, float, float, list[geo_k.Kaskadenvorgabe]]:
    """Erzeugt eine lokale 2D-Kaskade aus genau einer Gruppe.

    Die erste Zeile muss die Rolle ``Haupt`` besitzen. Weitere Zeilen werden
    als Flaps relativ zum jeweils vorherigen Element angeordnet.
    """
    rows = list(zeilen or [])
    if not rows:
        raise ValueError("Die lokale Kaskadengruppe ist leer.")
    haupt_rows = [r for r in rows if str(r.get("rolle") or "Flap") == "Haupt"]
    if len(haupt_rows) != 1:
        raise ValueError("Jede Gruppe braucht genau ein Hauptelement.")
    haupt = haupt_rows[0]
    if rows[0] is not haupt:
        rows = [haupt] + [r for r in rows if r is not haupt]

    haupt_sehne = _float(haupt, "sehne_faktor", 1.0) * 250.0
    haupt_winkel = _float(haupt, "winkel_relativ", 0.0)
    hauptprofil = str(haupt.get("profil") or "e423.dat")

    flaps = []
    for nummer, row in enumerate(rows[1:], start=1):
        faktor = _float(row, "sehne_faktor", 0.35)
        if not 0.05 <= faktor <= 1.5:
            raise ValueError(f"Flap {nummer}: Sehnenfaktor ausserhalb des Bereichs.")
        gap = _float(row, "spalt", 0.02)
        overlap = _float(row, "ueberlappung", 0.02)
        if not 0.002 <= gap <= 0.15:
            raise ValueError(f"Flap {nummer}: Gap muss zwischen 0,002 und 0,15 liegen.")
        if not -0.10 <= overlap <= 0.20:
            raise ValueError(f"Flap {nummer}: Overlap muss zwischen -0,10 und 0,20 liegen.")
        flaps.append(geo_k.Kaskadenvorgabe(
            profil=_profil(str(row.get("profil") or "e58.dat"), abtrieb),
            sehne_faktor=faktor,
            winkel_relativ=_float(row, "winkel_relativ", -15.0),
            spalt=gap,
            ueberlappung=overlap,
            name=str(row.get("name") or f"Flap {nummer}"),
        ))
    return hauptprofil, haupt_sehne, haupt_winkel, flaps


def baue_gruppe(zeilen: list[dict], geschwindigkeit: float,
                bodenhoehe: float | None):
    hauptprofil, sehne, winkel, flaps = flaps_aus_zeilen(zeilen)
    return aero_k.baue_und_rechne(
        _profil(hauptprofil, True), sehne, winkel, flaps,
        float(geschwindigkeit), None if bodenhoehe is None else float(bodenhoehe))


def figur(elemente) -> go.Figure:
    fig = go.Figure()
    for e in elemente:
        fig.add_trace(go.Scatter(
            x=e.punkte[:, 0], y=e.punkte[:, 1], mode="lines",
            name=e.name,
            hovertemplate="x=%{x:.1f} mm<br>z=%{y:.1f} mm<extra></extra>"))
    fig.update_layout(
        title="Lokaler 2D-Kaskadenquerschnitt", xaxis_title="x [mm]", yaxis_title="z [mm]",
        template="plotly_white", height=500, legend=dict(orientation="h"),
        margin=dict(l=55, r=20, t=55, b=50))
    fig.update_yaxes(scaleanchor="x", scaleratio=1)
    return fig


def spannweiten_figur(system: FluegelSystem) -> go.Figure:
    fig = go.Figure()
    for i, element in enumerate(system.elemente):
        y0, y1 = element.spannweite.y_von, element.spannweite.y_bis
        fig.add_trace(go.Bar(
            x=[y1 - y0], y=[element.name], base=[y0], orientation="h",
            hovertemplate=(f"{element.name}<br>Gruppe: {element.gruppe}<br>"
                           "y=%{base:.0f} bis %{x_end:.0f} mm<extra></extra>"),
            customdata=[[y1]],
            name=element.gruppe,
            showlegend=False,
        ))
    fig.update_layout(
        title="Spannweiten- und Segmentaufteilung",
        xaxis_title="y [mm] — Fahrzeugmitte = 0",
        yaxis_title="Element",
        template="plotly_white", height=max(260, 55 * len(system.elemente) + 100),
        margin=dict(l=120, r=20, t=55, b=50),
        barmode="overlay")
    fig.add_vline(x=0.0, line_dash="dash", annotation_text="Fahrzeugmitte")
    return fig


def _ergebniskarte(elemente, b):
    status = "ABRISS / Modellgrenze" if b.abgerissen else "innerhalb der Modellgrenze"
    klasse = "as-status-fehler" if b.abgerissen else "as-status-ok"
    unten, oben = b.spanne
    zeilen = []
    for lage, wert in zip(elemente, b.elemente):
        zeilen.append(html.Tr([
            html.Td(wert.name), html.Td(f"{lage.sehne:.1f} mm"),
            html.Td(f"{wert.winkel:+.1f}°"), html.Td(f"{wert.cl_zaeh:+.3f}"),
            html.Td(f"{wert.gewinn:.2f}×"), html.Td(f"{wert.reserve*100:+.0f} %"),
        ]))
    return html.Div([
        html.Div(status, className=klasse),
        html.Div([
            html.Div([html.B(f"{b.cl:+.3f}"), html.Br(), "CL zäh"]),
            html.Div([html.B(f"{b.cl_reibungsfrei:+.3f}"), html.Br(), "CL reibungsfrei"]),
            html.Div([html.B(f"{b.cd:.4f}"), html.Br(), "CD Profil"]),
            html.Div([html.B(f"{b.gesamtsehne:.1f} mm"), html.Br(), "Gesamtsehne"]),
            html.Div([html.B(f"{b.knappste_reserve*100:+.0f} %"), html.Br(), "knappste Reserve"]),
        ], style={"display": "grid", "gridTemplateColumns": "repeat(5, minmax(110px,1fr))", "gap": "12px", "margin": "14px 0"}),
        html.Div(
            f"Lokale Modellspanne für CL: {unten:+.3f} bis {oben:+.3f}. "
            "Der Slot-Grenzschichteffekt ist noch nicht kalibriert; das Ergebnis "
            "ist keine CFD- oder Messwert-Ersatzgröße.",
            className="as-hinweis", style={"marginBottom": "12px"}),
        html.Table([
            html.Thead(html.Tr([html.Th("Element"), html.Th("Sehne"), html.Th("Winkel"),
                                html.Th("CL"), html.Th("Verbundgewinn"), html.Th("Abrissreserve")])),
            html.Tbody(zeilen),
        ], className="as-tabelle"),
    ])


def layout():
    profile = katalogoptionen()
    return html.Div([
        html.H2("Aero Studio — Flügel- & Kaskaden-Editor"),
        html.P(
            "Bis zu sechs Elemente. Jedes Element kann einen eigenen Spannweitenbereich besitzen. "
            "Getrennte Gruppen bilden getrennte 2D-Kaskaden — geeignet als Grundlage für "
            "Frontflügel, Seitenkasten-Flügel, Bullwings und Heckflügel."),
        html.Div([
            html.Div([
                html.Label("Berechnungsgruppe"),
                dcc.Dropdown(id="k-gruppe", options=[], value=None, clearable=False),
            ]),
            html.Div([
                html.Label("Geschwindigkeit [m/s]"),
                dcc.Input(id="k-v", type="number", value=15.0),
            ]),
            html.Div([
                html.Label("Bodenhöhe [mm]"),
                dcc.Input(id="k-boden", type="number", value=90.0),
            ]),
        ], style={"display": "grid", "gridTemplateColumns": "2fr 1fr 1fr", "gap": "12px", "marginBottom": "12px"}),
        html.H4("Flügelelemente"),
        html.P(
            "Rolle = Haupt oder Flap. Das Hauptelement ist die Referenz der lokalen Gruppe. "
            "y von/y bis erlaubt Lücken und getrennte linke/rechte Segmente."),
        dash_table.DataTable(
            id="k-elemente", columns=ELEMENT_SPALTEN, data=vorgabe_zeilen(2),
            editable=True, row_deletable=True,
            dropdown={
                "profil": {"options": profile},
                "rolle": {"options": ["Haupt", "Flap"]},
            },
            style_table={"overflowX": "auto"},
            style_cell={"padding": "6px", "fontFamily": "Consolas, monospace", "minWidth": "95px"},
            style_header={"fontWeight": "bold"}),
        html.Div([
            html.Button("Element hinzufügen", id="k-add", n_clicks=0, className="as-knopf"),
            html.Button("Lokale Gruppe rechnen", id="k-rechnen", n_clicks=0, className="as-knopf", style={"marginLeft": "10px"}),
        ], style={"margin": "12px 0"}),
        html.Div(id="k-hinweis", className="as-hinweis"),
        dcc.Graph(id="k-spannweite", figure=go.Figure()),
        dcc.Loading(html.Div(id="k-ergebnis"), type="dot"),
        dcc.Graph(id="k-figur", figure=go.Figure()),
    ], style={"maxWidth": "1500px", "margin": "0 auto", "padding": "24px", "fontFamily": "Segoe UI, sans-serif"})


app = Dash(__name__, title="Aero Studio — Flügel/Kaskade")
app.layout = layout


@app.callback(
    Output("k-gruppe", "options"), Output("k-gruppe", "value"),
    Output("k-spannweite", "figure"), Output("k-hinweis", "children"),
    Input("k-elemente", "data"), State("k-gruppe", "value"),
)
def _system_aktualisieren(daten, bisherige_gruppe):
    try:
        system = system_aus_zeilen(daten)
        gruppen = system.gruppen()
        value = bisherige_gruppe if bisherige_gruppe in gruppen else (gruppen[0] if gruppen else None)
        optionen = [{"label": g, "value": g} for g in gruppen]
        return optionen, value, spannweiten_figur(system), (
            f"{len(system.elemente)} / {MAX_ELEMENTE} Elemente. "
            f"Gruppen: {', '.join(gruppen) if gruppen else 'keine'}. "
            "Eine Gruppe ist ein lokaler 2D-Querschnitt; die Spannweitenkarte ist die gemeinsame 3D-Geometrieebene."
        )
    except Exception as fehler:
        return [], None, go.Figure(), html.Div(str(fehler), className="as-status-fehler")


@app.callback(Output("k-elemente", "data"), Input("k-add", "n_clicks"), State("k-elemente", "data"), prevent_initial_call=True)
def _element_hinzufuegen(_n, daten):
    daten = list(daten or [])
    if len(daten) >= MAX_ELEMENTE:
        return daten
    index = len(daten) + 1
    return daten + [{
        "name": f"Element {index}", "gruppe": "Frontfluegel", "rolle": "Flap",
        "profil": "e58.dat", "sehne_faktor": 0.25, "winkel_relativ": -12.0,
        "spalt": 0.018, "ueberlappung": 0.020, "y_von": -600.0, "y_bis": 600.0,
        "x": 0.0, "z": 90.0,
    }]


@app.callback(Output("k-figur", "figure"), Output("k-ergebnis", "children"),
              Input("k-rechnen", "n_clicks"),
              State("k-gruppe", "value"), State("k-elemente", "data"),
              State("k-v", "value"), State("k-boden", "value"),
              prevent_initial_call=True)
def _rechnen(_n, gruppe, daten, v, boden):
    try:
        rows = zeilen_fuer_gruppe(daten or [], gruppe or "")
        elemente, b = baue_gruppe(rows, float(v or 15.0), None if boden is None else float(boden))
        return figur(elemente), _ergebniskarte(elemente, b)
    except Exception as fehler:
        return go.Figure(), html.Div([
            html.B("Berechnung fehlgeschlagen"), html.Div(str(fehler)),
            html.Details([html.Summary("Details"), html.Pre(traceback.format_exc())]),
        ], className="as-status-fehler")


def starten(port: int = 8052, browser: bool = True) -> None:
    if browser:
        Timer(1.0, lambda: webbrowser.open(f"http://127.0.0.1:{port}")).start()
    app.run(debug=False, port=port)


if __name__ == "__main__":
    starten()
