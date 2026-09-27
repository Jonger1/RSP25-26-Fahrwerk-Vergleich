"""Kleine Dash-Oberflaeche fuer transparente Kaskadenparameter-Sweeps."""

from __future__ import annotations

from threading import Timer
import webbrowser

from dash import Dash, Input, Output, dcc, html
from dash import dash_table

from ..aero import kaskaden_sweep
from .kaskade_editor import rechne_entwurf, vorgabe_zeilen


app = Dash(__name__, title="Aero Studio — Kaskaden-Sweep")


def layout():
    return html.Div([
        html.H2("Aero Studio — Kaskaden-Sweep"),
        html.P("Gap, Overlap und Flapwinkel als transparenten Designraum untersuchen."),
        html.Div([
            html.Div([html.Label("Gap von"), dcc.Input(id="s-gap-min", type="number", value=0.012, step=0.002),
                      html.Label("bis"), dcc.Input(id="s-gap-max", type="number", value=0.030, step=0.002),
                      html.Label("Schritt"), dcc.Input(id="s-gap-step", type="number", value=0.003, step=0.001)]),
            html.Div([html.Label("Overlap von"), dcc.Input(id="s-ov-min", type="number", value=0.0, step=0.005),
                      html.Label("bis"), dcc.Input(id="s-ov-max", type="number", value=0.04, step=0.005),
                      html.Label("Schritt"), dcc.Input(id="s-ov-step", type="number", value=0.01, step=0.005)]),
            html.Div([html.Label("Flapwinkel von [°]"), dcc.Input(id="s-a-min", type="number", value=-22, step=1),
                      html.Label("bis"), dcc.Input(id="s-a-max", type="number", value=-10, step=1),
                      html.Label("Schritt"), dcc.Input(id="s-a-step", type="number", value=2, step=1)]),
        ], style={"display": "grid", "gridTemplateColumns": "repeat(3, 1fr)", "gap": "16px"}),
        html.Br(),
        html.Button("Sweep rechnen", id="s-run", n_clicks=0),
        html.Div(id="s-status", style={"margin": "12px 0"}),
        dash_table.DataTable(
            id="s-table",
            columns=[
                {"id": "rank", "name": "Rang"},
                {"id": "gap", "name": "Gap / c"},
                {"id": "overlap", "name": "Overlap / c"},
                {"id": "winkel_relativ", "name": "Flapwinkel [°]"},
                {"id": "cl", "name": "CL"},
                {"id": "cd", "name": "CD"},
                {"id": "effizienz", "name": "|CL| / CD"},
                {"id": "reserve", "name": "Reserve"},
                {"id": "status", "name": "Status"},
            ],
            data=[],
            sort_action="native",
            page_size=20,
            style_cell={"padding": "7px", "fontFamily": "Consolas, monospace", "textAlign": "right"},
            style_header={"fontWeight": "bold"},
        ),
        html.Div(id="s-warning", className="as-hinweis", style={"marginTop": "12px"}),
    ], style={"maxWidth": "1250px", "margin": "0 auto", "padding": "24px",
              "fontFamily": "Segoe UI, sans-serif"})


app.layout = layout


@app.callback(Output("s-table", "data"), Output("s-status", "children"), Output("s-warning", "children"),
              Input("s-run", "n_clicks"),
              *[Input(x, "value") for x in (
                  "s-gap-min", "s-gap-max", "s-gap-step",
                  "s-ov-min", "s-ov-max", "s-ov-step",
                  "s-a-min", "s-a-max", "s-a-step")],
              prevent_initial_call=True)
def rechnen(_n, gap_min, gap_max, gap_step, ov_min, ov_max, ov_step,
            a_min, a_max, a_step):
    try:
        gaeps = kaskaden_sweep.raster(gap_min, gap_max, gap_step)
        overlaps = kaskaden_sweep.raster(ov_min, ov_max, ov_step)
        winkel = kaskaden_sweep.raster(a_min, a_max, a_step)

        basis = vorgabe_zeilen(1)[0]

        def rechner(gap, overlap, winkel_relativ):
            zeile = dict(basis, spalt=gap, ueberlappung=overlap,
                         winkel_relativ=winkel_relativ)
            _, b = rechne_entwurf("e423.dat", 250.0, -4.0, [zeile], 15.0, 90.0)
            return b

        resultate = kaskaden_sweep.sweep(
            gaeps=gaeps, overlaps=overlaps, winkel=winkel,
            rechner=rechner, modellgrenze=(-3.0, 0.0), min_reserve=0.0)
        sortiert = kaskaden_sweep.sortiere_nach_effizienz(resultate)

        daten = []
        gueltig = 0
        for rang, e in enumerate(sortiert, start=1):
            if e.gueltig:
                gueltig += 1
            daten.append({
                "rank": rang,
                "gap": e.gap,
                "overlap": e.overlap,
                "winkel_relativ": e.winkel_relativ,
                "cl": round(e.cl, 5),
                "cd": round(e.cd, 5),
                "effizienz": round(abs(e.cl) / e.cd, 2) if e.cd > 0 else None,
                "reserve": round(e.reserve * 100, 1),
                "status": "OK" if e.gueltig else ("ABRISS" if e.abgerissen else "Modellgrenze"),
            })

        warn = (
            "Das Ranking ist nur innerhalb des verwendeten Kaskadenmodells gültig. "
            "Slot-Grenzschicht und CFD-/Messdaten-Kalibrierung fehlen noch."
        )
        return daten, f"{len(resultate)} Varianten gerechnet; {gueltig} davon innerhalb der Modellgrenzen.", warn
    except Exception as exc:
        return [], "Sweep fehlgeschlagen", str(exc)


def starten(port: int = 8053, browser: bool = True):
    if browser:
        Timer(1.0, lambda: webbrowser.open(f"http://127.0.0.1:{port}")).start()
    app.run(debug=False, port=port)


if __name__ == "__main__":
    starten()
