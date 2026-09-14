"""3D-Systemansicht fuer segmentierte Aero-Entwuerfe.

Die Tabelle benutzt dasselbe Datenmodell wie der Kaskadeneditor. Die lokale
2D-Kaskade bleibt die Detailrechnung; diese Ansicht loest die gemeinsamen
3D-Hufeisenwirbel ueber alle aktiven Spannweitenbereiche.
"""

from __future__ import annotations

import traceback
import webbrowser
from threading import Timer

from dash import Dash, Input, Output, State, dash_table, dcc, html
import plotly.graph_objects as go

from ..aero.traglinie_system import rechne, streifen_aus_system
from ..geometrie.fluegel_system import FluegelSystem
from .kaskade_editor import ELEMENT_SPALTEN, system_aus_zeilen, vorgabe_zeilen


def _karte_ergebnis(r):
    return html.Div([
        html.Div("3D-Traglinienrechnung", className="as-status-ok" if r.konvergiert else "as-status-fehler"),
        html.Div([
            html.Div([html.B(f"{r.abtrieb:+.1f} N"), html.Br(), "Abtrieb"]),
            html.Div([html.B(f"{r.widerstand:.1f} N"), html.Br(), "induzierter Widerstand"]),
            html.Div([html.B(f"{r.cl:+.4f}"), html.Br(), "CL"]),
            html.Div([html.B(f"{r.cd:.5f}"), html.Br(), "CDi"]),
            html.Div([html.B(f"{r.wirkungsgrad:.1f}"), html.Br(), "L/D"]),
        ], style={"display": "grid", "gridTemplateColumns": "repeat(5, minmax(120px, 1fr))", "gap": "12px", "margin": "14px 0"}),
        html.Div(
            f"{len(r.streifen)} Rechenstreifen. Die Rechnung ist inviscid; Profilreibung, Slot-Grenzschicht, "
            "Endplattenwirkung sowie Fahrzeug-/Radinteraktion sind noch nicht enthalten.",
            className="as-hinweis"),
    ])


def _spannweite(system: FluegelSystem) -> go.Figure:
    fig = go.Figure()
    for e in system.elemente:
        fig.add_trace(go.Bar(
            x=[e.spannweite.breite], y=[e.name], base=[e.spannweite.y_von], orientation="h",
            name=e.baugruppe, showlegend=False,
            customdata=[[e.baugruppe, e.gruppe, e.spannweite.y_bis]],
            hovertemplate="%{y}<br>%{customdata[0]} / %{customdata[1]}<br>y=%{base:.0f} … %{customdata[2]:.0f} mm<extra></extra>",
        ))
    fig.update_layout(
        title="3D-System: aktive Spannweitenbereiche",
        xaxis_title="y [mm]", yaxis_title="Element",
        barmode="overlay", template="plotly_white",
        height=max(300, 55 * len(system.elemente) + 100),
        margin=dict(l=130, r=20, t=55, b=50),
    )
    fig.add_vline(x=0, line_dash="dash", annotation_text="Mitte")
    return fig


def layout():
    return html.Div([
        html.H2("Aero Studio — gekoppeltes 3D-System"),
        html.P("Alle aktiven Spannweitenbereiche werden gemeinsam als Hufeisenwirbelsystem gelöst. Lücken bleiben echte Lücken."),
        html.Div([
            html.Div([html.Label("Geschwindigkeit [m/s]"), dcc.Input(id="s-v", type="number", value=15.0)]),
            html.Div([html.Label("Panels je Element"), dcc.Input(id="s-panels", type="number", value=12, min=2, max=50, step=1)]),
            html.Div([html.Label("Boden-Spiegelung"), dcc.Checklist(id="s-boden", options=[{"label": " aktiv", "value": "an"}], value=[])]),
        ], style={"display": "grid", "gridTemplateColumns": "1fr 1fr 1fr", "gap": "12px"}),
        html.H4("Elemente"),
        dash_table.DataTable(
            id="s-elemente", columns=ELEMENT_SPALTEN, data=vorgabe_zeilen(6),
            editable=True, row_deletable=True,
            dropdown={"profil": {"options": []}, "rolle": {"options": [{"label": "Haupt", "value": "Haupt"}, {"label": "Flap", "value": "Flap"}]}},
            style_cell={"padding": "6px", "fontSize": "12px"},
            style_table={"overflowX": "auto"},
        ),
        html.Button("3D-System rechnen", id="s-rechnen", n_clicks=0, className="as-knopf", style={"margin": "14px 0"}),
        dcc.Graph(id="s-spannweite"),
        dcc.Loading(html.Div(id="s-ergebnis"), type="dot"),
    ], style={"maxWidth": "1450px", "margin": "0 auto", "padding": "24px", "fontFamily": "Segoe UI, sans-serif"})


app = Dash(__name__, title="Aero Studio — 3D-System")
app.layout = layout


@app.callback(Output("s-spannweite", "figure"), Output("s-ergebnis", "children"),
              Input("s-rechnen", "n_clicks"), State("s-elemente", "data"),
              State("s-v", "value"), State("s-panels", "value"),
              State("s-boden", "value"), prevent_initial_call=True)
def rechnen_system(_n, daten, v, panels, boden):
    try:
        system = system_aus_zeilen(daten)
        streifen = streifen_aus_system(system, int(panels or 12))
        result = rechne(streifen, float(v or 15.0), mit_boden=bool(boden))
        return _spannweite(system), _karte_ergebnis(result)
    except Exception as exc:
        return go.Figure(), html.Div([
            html.B("Berechnung fehlgeschlagen"), html.Div(str(exc)),
            html.Details([html.Summary("Details"), html.Pre(traceback.format_exc())]),
        ], className="as-status-fehler")


def starten(port: int = 8053, browser: bool = True) -> None:
    if browser:
        Timer(1.0, lambda: webbrowser.open(f"http://127.0.0.1:{port}")).start()
    app.run(debug=False, port=port)


if __name__ == "__main__":
    starten()
