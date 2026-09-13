"""Interaktiver Editor fuer Mehr­element-Kaskaden.

Der Editor ist absichtlich als eigenes UI-Modul aufgebaut. Die eigentliche
Geometrie und Aerodynamik bleiben in ``geometrie.kaskade`` bzw.
``aero.kaskade``; hier werden nur Eingaben eingesammelt, die Rechnung
angestossen und Ergebnisse dargestellt.

Aufruf::

    python -m aerostudio.ui.kaskade_editor

Damit ist der M4-Kaskadenentwurf bereits benutzbar, ohne die bestehende
Aero-Studio-Oberflaeche mit einer zweiten Kopie der Fachlogik zu belasten.
Eine spaetere Einbindung als Reiter kann dieselben Funktionen direkt nutzen.
"""

from __future__ import annotations

import traceback
import webbrowser
from dataclasses import asdict
from threading import Timer

import plotly.graph_objects as go
from dash import Dash, Input, Output, State, dash_table, dcc, html

from ..aero import kaskade as aero_k
from ..geometrie import kaskade as geo_k
from ..geometrie.profil import KATALOG, Profil, katalogoptionen


FLAP_SPALTEN = [
    {"id": "profil", "name": "Profil"},
    {"id": "sehne_faktor", "name": "Sehne / Hauptsehne", "type": "numeric"},
    {"id": "winkel_relativ", "name": "Winkel relativ [°]", "type": "numeric"},
    {"id": "spalt", "name": "Gap / Hauptsehne", "type": "numeric"},
    {"id": "ueberlappung", "name": "Overlap / Hauptsehne", "type": "numeric"},
]


def vorgabe_zeilen(anzahl: int = 1) -> list[dict]:
    """Plausibler Startpunkt fuer ein bis drei Flaps."""
    anzahl = max(0, min(int(anzahl), 3))
    basis = [
        {"profil": "e58.dat", "sehne_faktor": 0.35, "winkel_relativ": -18.0,
         "spalt": 0.020, "ueberlappung": 0.020},
        {"profil": "e58.dat", "sehne_faktor": 0.28, "winkel_relativ": -14.0,
         "spalt": 0.018, "ueberlappung": 0.020},
        {"profil": "e58.dat", "sehne_faktor": 0.22, "winkel_relativ": -12.0,
         "spalt": 0.016, "ueberlappung": 0.018},
    ]
    return basis[:anzahl]


def _profil(datei: str, abtrieb: bool = True) -> Profil:
    p = Profil.aus_dat(KATALOG / datei)
    return p.gespiegelt() if abtrieb else p


def flaps_aus_zeilen(zeilen: list[dict] | None,
                     abtrieb: bool = True) -> list[geo_k.Kaskadenvorgabe]:
    """Validiert Tabellenzeilen und macht daraus Domain-Objekte.

    Prozentwerte werden bewusst NICHT verwendet: 0.02 bedeutet 2 % der
    Hauptsehne, genau wie im Geometriemodul und in der Literatur.
    """
    ergebnis = []
    for nr, z in enumerate(zeilen or [], start=1):
        datei = str(z.get("profil") or "e58.dat")
        sehne = float(z.get("sehne_faktor") or 0.0)
        winkel = float(z.get("winkel_relativ") or 0.0)
        spalt = float(z.get("spalt") or 0.0)
        overlap = float(z.get("ueberlappung") or 0.0)
        if not 0.05 <= sehne <= 1.0:
            raise ValueError(f"Flap {nr}: Sehnenfaktor muss zwischen 0,05 und 1 liegen.")
        if not 0.002 <= spalt <= 0.15:
            raise ValueError(f"Flap {nr}: Gap muss zwischen 0,002 und 0,15 liegen.")
        if not -0.10 <= overlap <= 0.20:
            raise ValueError(f"Flap {nr}: Overlap muss zwischen -0,10 und 0,20 liegen.")
        if not -60.0 <= winkel <= 30.0:
            raise ValueError(f"Flap {nr}: relativer Winkel ausserhalb des Editorbereichs.")
        ergebnis.append(geo_k.Kaskadenvorgabe(
            profil=_profil(datei, abtrieb), sehne_faktor=sehne,
            winkel_relativ=winkel, spalt=spalt, ueberlappung=overlap,
            name=f"Flap {nr}"))
    return ergebnis


def baue_geometrie(hauptprofil: str, sehne: float, winkel: float,
                   zeilen: list[dict] | None, hoehe: float = 0.0):
    """Reine Geometriefunktion fuer UI und Tests."""
    haupt = _profil(hauptprofil, True)
    return geo_k.platziere(haupt, float(sehne), float(winkel),
                           flaps_aus_zeilen(zeilen), lage=(0.0, float(hoehe)))


def rechne_entwurf(hauptprofil: str, sehne: float, winkel: float,
                   zeilen: list[dict] | None, geschwindigkeit: float,
                   bodenhoehe: float | None):
    """Einzige Bruecke von Editor zu Fachlogik."""
    haupt = _profil(hauptprofil, True)
    return aero_k.baue_und_rechne(
        haupt, float(sehne), float(winkel), flaps_aus_zeilen(zeilen),
        float(geschwindigkeit),
        None if bodenhoehe is None else float(bodenhoehe))


def figur(elemente) -> go.Figure:
    fig = go.Figure()
    for e in elemente:
        fig.add_trace(go.Scatter(
            x=e.punkte[:, 0], y=e.punkte[:, 1], mode="lines",
            name=e.name, hovertemplate="x=%{x:.1f} mm<br>z=%{y:.1f} mm<extra></extra>"))
    fig.update_layout(
        title="2D-Kaskade", xaxis_title="x [mm]", yaxis_title="z [mm]",
        template="plotly_white", height=520,
        legend=dict(orientation="h"), margin=dict(l=55, r=20, t=55, b=50))
    fig.update_yaxes(scaleanchor="x", scaleratio=1)
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
        ], style={"display": "grid", "gridTemplateColumns": "repeat(5, minmax(110px,1fr))",
                  "gap": "12px", "margin": "14px 0"}),
        html.Div(
            f"Modellspanne fuer CL: {unten:+.3f} bis {oben:+.3f}. "
            "Der Slot-Grenzschichteffekt ist noch nicht kalibriert; die zähe Rechnung "
            "ist daher keine CFD- oder Messwert-Ersatzgröße.",
            className="as-hinweis", style={"marginBottom": "12px"}),
        html.Table([
            html.Thead(html.Tr([html.Th("Element"), html.Th("Sehne"),
                                html.Th("Winkel"), html.Th("CL"),
                                html.Th("Verbundgewinn"), html.Th("Abrissreserve")])),
            html.Tbody(zeilen),
        ], className="as-tabelle"),
    ])


def layout():
    profile = katalogoptionen()
    return html.Div([
        html.H2("Aero Studio — Kaskaden-Editor"),
        html.P("Mehr­element-Frontflügel parametrisch über Gap, Overlap, Sehne und Winkel auslegen."),
        html.Div([
            html.Div([
                html.Label("Hauptelement"),
                dcc.Dropdown(id="k-haupt", options=profile, value="e423.dat", clearable=False),
            ]),
            html.Div([html.Label("Hauptsehne [mm]"), dcc.Input(id="k-sehne", type="number", value=250.0)]),
            html.Div([html.Label("Hauptwinkel [°]"), dcc.Input(id="k-winkel", type="number", value=-4.0)]),
            html.Div([html.Label("Geschwindigkeit [m/s]"), dcc.Input(id="k-v", type="number", value=15.0)]),
            html.Div([html.Label("Nasenhöhe über Boden [mm]"), dcc.Input(id="k-boden", type="number", value=90.0)]),
        ], style={"display": "grid", "gridTemplateColumns": "2fr repeat(4, 1fr)", "gap": "12px"}),
        html.H4("Flaps"),
        html.P("Gap und Overlap sind Anteile der Hauptsehne: 0,020 = 2,0 %."),
        dash_table.DataTable(
            id="k-flaps", columns=FLAP_SPALTEN, data=vorgabe_zeilen(1),
            editable=True, row_deletable=True,
            dropdown={"profil": {"options": profile}},
            style_cell={"padding": "7px", "fontFamily": "Consolas, monospace"}),
        html.Div([
            html.Button("Flap hinzufügen", id="k-add", n_clicks=0),
            html.Button("Geometrie + Aerodynamik rechnen", id="k-rechnen", n_clicks=0,
                        style={"marginLeft": "10px"}),
        ], style={"margin": "12px 0"}),
        dcc.Loading(html.Div(id="k-ergebnis"), type="dot"),
        dcc.Graph(id="k-figur", figure=go.Figure()),
    ], style={"maxWidth": "1250px", "margin": "0 auto", "padding": "24px",
              "fontFamily": "Segoe UI, sans-serif"})


app = Dash(__name__, title="Aero Studio — Kaskade")
app.layout = layout


@app.callback(Output("k-flaps", "data"), Input("k-add", "n_clicks"),
              State("k-flaps", "data"), prevent_initial_call=True)
def _flap_hinzufuegen(_n, daten):
    daten = list(daten or [])
    if len(daten) >= 3:
        return daten
    return daten + vorgabe_zeilen(len(daten) + 1)[-1:]


@app.callback(Output("k-figur", "figure"), Output("k-ergebnis", "children"),
              Input("k-rechnen", "n_clicks"),
              State("k-haupt", "value"), State("k-sehne", "value"),
              State("k-winkel", "value"), State("k-flaps", "data"),
              State("k-v", "value"), State("k-boden", "value"),
              prevent_initial_call=True)
def _rechnen(_n, haupt, sehne, winkel, flaps, v, boden):
    try:
        elemente, b = rechne_entwurf(
            haupt or "e423.dat", float(sehne or 250.0), float(winkel or 0.0),
            flaps, float(v or 15.0), None if boden is None else float(boden))
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
