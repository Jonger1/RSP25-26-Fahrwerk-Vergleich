"""
Diagramme fuer die Oberflaeche.

Bewusst ausserhalb der Callbacks: Ein Dash-Callback nimmt Eingaben entgegen,
ruft hier eine Funktion auf und gibt das Ergebnis zurueck. Nur so bleibt die
Fachlogik von der Oberflaeche getrennt - und nur so laesst sich dieselbe
Darstellung spaeter auch in einen Report schreiben, ohne Dash zu starten.
"""

from __future__ import annotations

import numpy as np
import plotly.graph_objects as go

from ..geometrie.profil import Profil

# Eine Farbe je Laminatzone, durchgehend im ganzen Werkzeug verwendet.
FARBE = {
    "sandwich": "#2c7fb8",
    "schale": "#7fcdbb",
    "vollmaterial": "#d95f0e",
}
FARBE_KONTUR = "#253494"
FARBE_HILFE = "#9e9e9e"


def _grundlayout(titel: str, hoehe: int = 340) -> dict:
    return dict(
        title=dict(text=titel, font=dict(size=14)),
        height=hoehe,
        margin=dict(l=55, r=20, t=40, b=45),
        plot_bgcolor="white",
        paper_bgcolor="white",
        showlegend=False,
        hovermode="x unified",
    )


def _achsen(fig: go.Figure) -> go.Figure:
    fig.update_xaxes(gridcolor="#eeeeee", zerolinecolor="#dddddd")
    fig.update_yaxes(gridcolor="#eeeeee", zerolinecolor="#dddddd")
    return fig


def kontur(profil: Profil, sehne_mm: float, anstellwinkel: float,
           fertigung=None) -> go.Figure:
    """Profilkontur in Millimetern, mit den Laminatzonen als Hinterlegung.

    Massstabsgetreu - `scaleanchor` erzwingt gleiche Skalierung beider Achsen.
    Ohne das sieht jedes Profil viel dicker aus, als es ist, und man beurteilt
    Formen, die es gar nicht gibt.
    """
    punkte = profil.angestellt(anstellwinkel, sehne_mm)
    fig = go.Figure()

    if fertigung is not None:
        for zone in profil.laminatzonen(fertigung, sehne_mm):
            if zone.laenge < 0.004:
                continue
            fig.add_vrect(x0=zone.von * sehne_mm, x1=zone.bis * sehne_mm,
                          fillcolor=FARBE[zone.art], opacity=0.13,
                          line_width=0, layer="below")

    fig.add_trace(go.Scatter(
        x=punkte[:, 0], y=punkte[:, 1], mode="lines",
        line=dict(color=FARBE_KONTUR, width=2),
        name=profil.name,
        hovertemplate="x %{x:.1f} mm<br>y %{y:.1f} mm<extra></extra>"))

    fig.update_layout(**_grundlayout(
        f"{profil.name} — Sehne {sehne_mm:.0f} mm, Anstellwinkel {anstellwinkel:+.1f}°"))
    fig.update_yaxes(scaleanchor="x", scaleratio=1, title="mm")
    fig.update_xaxes(title="mm")
    return _achsen(fig)


def dickenverlauf(profil: Profil, sehne_mm: float, fertigung) -> go.Figure:
    """Dickenverlauf mit den Schwellen des Laminataufbaus.

    Die beiden waagerechten Linien sind die eigentliche Aussage: Wo die Kurve
    unter die obere faellt, passt kein Kern mehr hinein; unter der unteren
    passt nicht einmal mehr eine Schale.
    """
    x, d = profil.dickenverlauf(401)
    fig = go.Figure()

    fig.add_trace(go.Scatter(
        x=x * sehne_mm, y=d * sehne_mm, mode="lines",
        line=dict(color=FARBE_KONTUR, width=2),
        hovertemplate="x %{x:.1f} mm<br>Dicke %{y:.2f} mm<extra></extra>"))

    schwellen = [(fertigung.dicke_schale, "2 Häute", FARBE["schale"])]
    if fertigung.kern > 0:
        schwellen.append((fertigung.dicke_sandwich, "2 Häute + Kern", FARBE["sandwich"]))
    for wert, beschriftung, farbe in schwellen:
        fig.add_hline(y=wert, line=dict(color=farbe, width=1.5, dash="dash"),
                      annotation_text=f"{beschriftung}: {wert:.1f} mm",
                      annotation_position="top left",
                      annotation_font=dict(size=11, color=farbe))

    fig.update_layout(**_grundlayout("Dickenverlauf"))
    fig.update_xaxes(title="mm ab Nase")
    fig.update_yaxes(title="Dicke [mm]", rangemode="tozero")
    return _achsen(fig)


def kruemmung(profil: Profil) -> go.Figure:
    """Kruemmungsverlauf ueber die Lauflaenge.

    Der beste Fruehwarnindikator fuer ein schlechtes Profil: Ein zappelnder
    Verlauf erzeugt im CFD Laminarblasen, die es real nicht gibt, und faellt an
    der fertigen Form als Welligkeit auf. Was zaehlt, ist nicht die Hoehe der
    Spitze an der Nase - die gehoert dort hin - sondern ob die Kurve dazwischen
    ruhig laeuft.
    """
    s, k = profil.kruemmung(801)
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=s / s[-1] * 100.0, y=k, mode="lines",
        line=dict(color=FARBE_KONTUR, width=1.5),
        hovertemplate="%{x:.0f} %% Lauflänge<br>κ %{y:.1f}<extra></extra>"))
    fig.add_hline(y=0, line=dict(color=FARBE_HILFE, width=1))

    # Die Nasenspitze staucht sonst alles Uebrige platt.
    innen = k[(s > 0.02 * s[-1]) & (s < 0.98 * s[-1])]
    if len(innen):
        grenze = float(np.percentile(np.abs(innen), 99)) * 2.5
        if grenze > 0:
            fig.update_yaxes(range=[-grenze, grenze])

    fig.update_layout(**_grundlayout("Krümmungsverlauf (Einheitssehne)"))
    fig.update_xaxes(title="% Lauflänge ab Hinterkante oben")
    fig.update_yaxes(title="Krümmung κ")
    return _achsen(fig)


def zonenbalken(profil: Profil, sehne_mm: float, fertigung) -> go.Figure:
    """Die Laminatzonen als einfacher Balken - auf einen Blick lesbar."""
    fig = go.Figure()
    for zone in profil.laminatzonen(fertigung, sehne_mm):
        if zone.laenge < 0.002:
            continue
        fig.add_trace(go.Bar(
            x=[zone.laenge * 100.0], y=["Aufbau"], base=zone.von * 100.0,
            orientation="h", marker=dict(color=FARBE[zone.art]),
            name=zone.art,
            hovertemplate=(f"{zone.art}<br>{zone.von*100:.1f} % .. "
                           f"{zone.bis*100:.1f} %<extra></extra>")))
    fig.update_layout(**_grundlayout("Laminataufbau über die Sehne", hoehe=150))
    fig.update_layout(barmode="stack", showlegend=True,
                      legend=dict(orientation="h", y=-0.5))
    fig.update_xaxes(title="% Sehne", range=[0, 100])
    fig.update_yaxes(showticklabels=False)
    return _achsen(fig)
