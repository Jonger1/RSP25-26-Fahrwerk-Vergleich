"""
Diagramme fuer die Oberflaeche.

Bewusst ausserhalb der Callbacks: Ein Dash-Callback nimmt Eingaben entgegen,
ruft hier eine Funktion auf und gibt das Ergebnis zurueck. Nur so bleibt die
Fachlogik von der Oberflaeche getrennt - und nur so laesst sich dieselbe
Darstellung spaeter auch in einen Report schreiben, ohne Dash zu starten.
"""

from __future__ import annotations

import math

import numpy as np
import plotly.graph_objects as go

from ..geometrie.profil import Profil

# Eine Farbe je Laminatzone, durchgehend im ganzen Werkzeug verwendet.
# Abgestimmt auf die Palette in assets/aerostudio.css - wer dort die
# Hausfarben aendert, sollte diese hier mitziehen.
FARBE = {
    "sandwich": "#3d6fa5",
    "schale": "#8fb4d4",
    "vollmaterial": "#ea7317",
}
FARBE_KONTUR = "#16181c"
FARBE_HILFE = "#c8ccd4"
FARBE_ZIEL = "#2e7d32"
FARBE_AKZENT = "#cf2027"


def _grundlayout(titel: str, hoehe: int = 340) -> dict:
    return dict(
        title=dict(text=titel, font=dict(size=14)),
        height=hoehe,
        margin=dict(l=55, r=20, t=40, b=45),
        plot_bgcolor="#ffffff",
        paper_bgcolor="#ffffff",
        font=dict(family="Segoe UI, system-ui, sans-serif", size=12,
                  color="#1c1f24"),
        showlegend=False,
        hovermode="x unified",
    )


def _achsen(fig: go.Figure) -> go.Figure:
    fig.update_xaxes(gridcolor="#eef0f3", zerolinecolor="#dfe3e8",
                     linecolor="#dfe3e8", ticks="outside", tickcolor="#dfe3e8")
    fig.update_yaxes(gridcolor="#eef0f3", zerolinecolor="#dfe3e8",
                     linecolor="#dfe3e8", ticks="outside", tickcolor="#dfe3e8")
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


def exportpunkte(plan, name: str = "") -> go.Figure:
    """Genau die Punkte, die in die IBL-Datei geschrieben werden.

    Nicht die glatte Kontur, sondern die Stuetzstellen - damit sichtbar ist,
    wie fein die Kurve tatsaechlich aufgeloest wird und wo die
    Kosinusverteilung verdichtet.

    Beim 3D-Fluegel wird raeumlich gezeichnet: Ein Stapel von dreizehn
    uebereinandergelegten Schnitten in der Seitenansicht waere ein Knaeuel,
    aus dem sich weder Verwindung noch Pfeilung ablesen laesst.
    """
    if getattr(plan, "ist_fluegel", False):
        return _fluegelpunkte(plan, name)

    farben = [FARBE_KONTUR, FARBE_AKZENT]
    fig = go.Figure()
    for i, sektion in enumerate(plan.sektionen):
        fig.add_trace(go.Scatter(
            x=sektion[:, 0], y=sektion[:, 2], mode="lines+markers",
            line=dict(color=farben[i % len(farben)], width=1),
            marker=dict(size=3, color=farben[i % len(farben)]),
            name=f"Sektion {i + 1} ({len(sektion)} Punkte)",
            hovertemplate="x %{x:.2f} mm<br>z %{y:.2f} mm<extra></extra>"))

    fig.update_layout(**_grundlayout(
        f"{name} — {plan.punktzahl} Punkte je Seite bei "
        f"{plan.toleranz_mm:.4f} mm Toleranz"))
    fig.update_layout(showlegend=True,
                      legend=dict(orientation="h", y=-0.25, font=dict(size=11)))
    fig.update_yaxes(scaleanchor="x", scaleratio=1, title="mm")
    fig.update_xaxes(title="mm")
    return _achsen(fig)


def _fluegelpunkte(plan, name: str = "") -> go.Figure:
    """Der Schnittstapel raeumlich, in Fahrzeugkoordinaten.

    Achsen bewusst so beschriftet, wie das Reglement spricht: x nach hinten ab
    Vorderachse, y ab Fahrzeugmitte, z ueber Boden. Wer hier eine Zahl abliest,
    kann sie unmittelbar gegen T 8.2 halten.
    """
    fig = go.Figure()
    anzahl = len(plan.sektionen)
    for i, sektion in enumerate(plan.sektionen):
        # Innen dunkel, aussen im Akzentton - so ist die Reihenfolge der
        # Schnitte auch ohne Legende erkennbar.
        anteil = i / max(anzahl - 1, 1)
        farbe = FARBE_AKZENT if anteil > 0.999 else (
            FARBE_KONTUR if anteil < 0.001 else "rgba(120,128,140,0.55)")
        fig.add_trace(go.Scatter3d(
            x=sektion[:, 0], y=sektion[:, 1], z=sektion[:, 2],
            mode="lines", line=dict(color=farbe, width=2),
            name=f"Schnitt {i + 1}", showlegend=False,
            hovertemplate="x %{x:.1f}<br>y %{y:.1f}<br>z %{z:.1f} mm<extra></extra>"))

    fig.update_layout(
        title=dict(text=f"{name} — {anzahl} Schnitte, je {len(plan.sektionen[0])} "
                        f"Punkte bei {plan.toleranz_mm:.4f} mm Toleranz",
                   font=dict(size=12)),
        margin=dict(l=0, r=0, t=34, b=0), height=460,
        paper_bgcolor="white",
        scene=dict(
            aspectmode="data",
            xaxis=dict(title="x [mm] ab Vorderachse, nach hinten"),
            yaxis=dict(title="y [mm] ab Mitte"),
            zaxis=dict(title="z [mm] über Boden"),
        ))
    return fig


def spannweitenverlauf(stapel, element) -> go.Figure:
    """Sehne und Eindrehen ueber die Spannweite, mit den Sektionen markiert.

    Zwei Groessen in einem Bild mit zwei Achsen: Sie haengen zusammen - wer
    aussen die Sehne verlaengert und gleichzeitig weiter eindreht, bekommt
    dort sehr viel mehr Last. Getrennte Bilder verstecken diesen Zusammenhang.
    Die Sektionen stehen als senkrechte Linien darin, damit sichtbar ist,
    welcher Knick von einer Stuetzstelle kommt und welcher aus der
    Interpolation.
    """
    y = [s.y for s in stapel]
    sehne = [s.sehne for s in stapel]
    winkel = [s.anstellwinkel for s in stapel]

    fig = go.Figure()
    fig.add_trace(go.Scatter(x=y, y=sehne, name="Sehne [mm]", mode="lines",
                             line=dict(color=FARBE_KONTUR, width=2),
                             hovertemplate="y %{x:.0f} mm<br>Sehne %{y:.1f} mm"
                                           "<extra></extra>"))
    fig.add_trace(go.Scatter(x=y, y=winkel, name="Anstellwinkel [°]", mode="lines",
                             yaxis="y2", line=dict(color=FARBE_AKZENT, width=2),
                             hovertemplate="y %{x:.0f} mm<br>Winkel %{y:.2f}°"
                                           "<extra></extra>"))

    if element is not None and element.spannweite is not None:
        for st in element.spannweite.stuetzstellen:
            fig.add_vline(x=st.y, line=dict(color="#c8ccd4", width=1, dash="dot"))

    fig.update_layout(**_grundlayout("Sehne und Eindrehen über die Spannweite"))
    fig.update_layout(
        showlegend=True,
        legend=dict(orientation="h", y=-0.28, font=dict(size=11)),
        yaxis=dict(title="Sehne [mm]"),
        yaxis2=dict(title="Anstellwinkel [°]", overlaying="y", side="right",
                    showgrid=False))
    fig.update_xaxes(title="y [mm] ab Fahrzeugmitte")
    return fig


def fluegel3d(stapel, name: str = "", darstellung: str = "flaeche") -> go.Figure:
    """Der Flügel räumlich, in Fahrzeugkoordinaten.

    Achsen so beschriftet, wie das Reglement spricht: x nach hinten ab
    Vorderachse, y ab Fahrzeugmitte, z über Boden. Wer hier eine Zahl abliest,
    kann sie unmittelbar gegen T 8.2 halten.

    `darstellung` wählt zwischen:

    * ``"flaeche"`` — die Schnitte sind zu einer durchgehenden Haut verbunden.
      So sieht man den FLÜGEL statt eines Stapels Ringe, und eine Verdrehung
      fällt sofort auf.
    * ``"schnitte"`` — nur die Linien, jede in eigener Farbe. Zum Nachmessen
      einzelner Stationen.
    * ``"beides"`` — Haut und Linien übereinander.

    Die Linien waren vorher innen durchgehend hellgrau und auf weißem Grund
    kaum zu erkennen. Jetzt läuft eine Farbskala von innen nach außen, und
    jeder Schnitt ist einzeln in der Legende an- und abschaltbar.
    """
    fig = go.Figure()
    anzahl = len(stapel)
    if anzahl == 0:
        return fig

    if darstellung in ("flaeche", "beides"):
        _haut(fig, stapel)
    if darstellung in ("schnitte", "beides"):
        _schnittlinien(fig, stapel, nur_linien=(darstellung == "schnitte"))

    fig.update_layout(
        title=dict(text=f"{name} — {anzahl} Schnitte", font=dict(size=12)),
        margin=dict(l=0, r=0, t=32, b=0), height=420, paper_bgcolor="white",
        showlegend=(darstellung != "flaeche"),
        legend=dict(font=dict(size=10), itemsizing="constant"),
        scene=dict(aspectmode="data",
                   xaxis=dict(title="x [mm] nach hinten"),
                   yaxis=dict(title="y [mm] ab Mitte"),
                   zaxis=dict(title="z [mm] über Boden")))
    return fig


def _haut(fig: go.Figure, stapel) -> None:
    """Verbindet die Schnitte zu einer durchgehenden Fläche.

    Voraussetzung ist, dass alle Schnitte gleich viele Punkte haben und in
    derselben Richtung laufen - genau das stellt der Export sicher, weil Creo
    sonst den Verbund verdreht. Ist es hier nicht erfüllt, wird auf die
    kleinste Punktzahl gekürzt statt die Anzeige zu verweigern.
    """
    laenge = min(len(s.punkte) for s in stapel)
    netz = np.stack([s.punkte[:laenge] for s in stapel])     # (Schnitte, Punkte, 3)

    # Einfärbung nach der Höhe: Die Unterseite eines Abtriebsflügels ist die
    # arbeitende Seite, und die hebt sich damit ab.
    fig.add_trace(go.Surface(
        x=netz[:, :, 0], y=netz[:, :, 1], z=netz[:, :, 2],
        surfacecolor=netz[:, :, 2],
        colorscale=[[0.0, "#8c1a1f"], [0.35, "#cf2027"],
                    [0.7, "#ea7317"], [1.0, "#f4c20d"]],
        showscale=False, opacity=1.0,
        lighting=dict(ambient=0.55, diffuse=0.8, specular=0.15, roughness=0.85),
        hovertemplate="x %{x:.0f}<br>y %{y:.0f}<br>z %{z:.0f} mm<extra></extra>",
        name="Haut", showlegend=False))


def _schnittlinien(fig: go.Figure, stapel, nur_linien: bool = True) -> None:
    """Jeden Schnitt als eigene Spur, mit eigener Farbe und Legendeneintrag.

    Eigene Spuren und nicht eine gemeinsame: Nur so lässt sich in der Legende
    ein einzelner Schnitt aus- und wieder einblenden.
    """
    anzahl = len(stapel)
    for i, schnitt in enumerate(stapel):
        p = schnitt.punkte
        anteil = i / max(anzahl - 1, 1)
        fig.add_trace(go.Scatter3d(
            x=p[:, 0], y=p[:, 1], z=p[:, 2], mode="lines",
            line=dict(color=_schnittfarbe(anteil), width=3 if nur_linien else 2),
            name=f"y = {schnitt.y:.0f} mm",
            legendgroup=f"schnitt{i}",
            hovertemplate=f"Schnitt y {schnitt.y:.0f} mm<br>"
                          "x %{x:.0f}<br>z %{z:.0f} mm<extra></extra>"))


def _schnittfarbe(anteil: float) -> str:
    """Farbverlauf von innen nach außen, aus der Lackierung des Fahrzeugs.

    Dunkelrot innen über Rot und Orange nach Gelb außen. Bewusst dunkel
    beginnend: Auf weißem Grund war die alte hellgraue Mitte praktisch
    unsichtbar.
    """
    stufen = [(0.0, (60, 14, 17)), (0.33, (176, 24, 30)),
              (0.66, (224, 112, 24)), (1.0, (232, 176, 20))]
    for (a1, c1), (a2, c2) in zip(stufen[:-1], stufen[1:]):
        if anteil <= a2 or a2 == 1.0:
            t = 0.0 if a2 == a1 else (anteil - a1) / (a2 - a1)
            t = min(max(t, 0.0), 1.0)
            rgb = [round(v1 + t * (v2 - v1)) for v1, v2 in zip(c1, c2)]
            return f"rgb({rgb[0]},{rgb[1]},{rgb[2]})"
    return "rgb(60,14,17)"


def kaskadenschnitt(elemente, bodenhoehe: float = 0.0) -> go.Figure:
    """Die Kaskade im Schnitt, mit Boden und eingezeichneten Spalten.

    Der Boden gehoert ins Bild: Bei einem Frontfluegel ist der Abstand zum
    Boden genauso wichtig wie der Spalt zwischen den Elementen, und beide
    zusammen sieht man nur, wenn beide da sind.
    """
    fig = go.Figure()
    farben = [FARBE_KONTUR, FARBE_AKZENT, "#ea7317", "#f4c20d"]

    alle_x = np.concatenate([e.punkte[:, 0] for e in elemente])
    rand = 0.08 * (alle_x.max() - alle_x.min() + 1e-9)

    # Boden zuerst, damit er hinter den Profilen liegt.
    fig.add_trace(go.Scatter(
        x=[alle_x.min() - rand, alle_x.max() + rand], y=[0.0, 0.0],
        mode="lines", line=dict(color="#9aa1ab", width=2, dash="dash"),
        name="Boden", hovertemplate="Boden<extra></extra>"))

    for i, e in enumerate(elemente):
        farbe = farben[i % len(farben)]
        fig.add_trace(go.Scatter(
            x=e.punkte[:, 0], y=e.punkte[:, 1], mode="lines",
            fill="toself", fillcolor=_durchsichtig(farbe, 0.12),
            line=dict(color=farbe, width=2),
            name=f"{e.name} ({e.winkel:+.1f}°)",
            hovertemplate="x %{x:.1f}<br>z %{y:.1f} mm<extra></extra>"))

        if i > 0 and e.spalt > 0:
            # Den Spalt als Mass eintragen, zwischen Nase und Vorgaenger.
            nase = e.nase
            fig.add_annotation(
                x=nase[0], y=nase[1], ax=25, ay=-30, xref="x", yref="y",
                axref="pixel", ayref="pixel", showarrow=True, arrowhead=2,
                arrowsize=0.8, arrowcolor=farbe,
                text=f"Spalt {e.spalt:.1f} mm", font=dict(size=10, color=farbe),
                bgcolor="rgba(255,255,255,0.85)", borderpad=2)

    fig.update_layout(**_grundlayout(
        f"{len(elemente)} Element(e), Gesamtsehne "
        f"{alle_x.max() - alle_x.min():.0f} mm"))
    fig.update_layout(showlegend=True,
                      legend=dict(orientation="h", y=-0.22, font=dict(size=11)))
    fig.update_yaxes(scaleanchor="x", scaleratio=1, title="z [mm] über Boden")
    fig.update_xaxes(title="x [mm]")
    return _achsen(fig)


def _durchsichtig(farbe: str, anteil: float) -> str:
    """Macht aus einer Hexfarbe eine halbdurchsichtige Fuellung."""
    farbe = farbe.lstrip("#")
    r, g, b = (int(farbe[i:i + 2], 16) for i in (0, 2, 4))
    return f"rgba({r},{g},{b},{anteil})"


ELEMENTFARBEN = ["#3b3f46", "#cf2027", "#ea7317", "#f4c20d", "#3d6fa5"]


def kaskade3d(stapel_je_element, namen=None, befunde=None) -> go.Figure:
    """Die räumliche Kaskade: jedes Element als eigene, einfarbige Fläche.

    Einfarbig je Element und nicht nach der Höhe eingefärbt wie beim
    einfachen Flügel: Hier ist die Frage, WELCHES Element wo liegt und ob
    zwei sich berühren - das sieht man nur, wenn sie sich farblich trennen.
    Stellen, an denen die Prüfung eine Durchdringung gefunden hat, sind rot
    markiert. Jedes Element lässt sich über die Legende ausblenden, um in die
    Schlitze zu sehen.
    """
    fig = go.Figure()
    for i, stapel in enumerate(stapel_je_element):
        if not stapel:
            continue
        laenge = min(len(s.punkte) for s in stapel)
        netz = np.stack([s.punkte[:laenge] for s in stapel])
        farbe = ELEMENTFARBEN[i % len(ELEMENTFARBEN)]
        name = (namen[i] if namen and i < len(namen)
                else ("Hauptelement" if i == 0 else f"Flap {i}"))
        fig.add_trace(go.Surface(
            x=netz[:, :, 0], y=netz[:, :, 1], z=netz[:, :, 2],
            surfacecolor=np.zeros(netz.shape[:2]),
            colorscale=[[0.0, farbe], [1.0, farbe]], cmin=0.0, cmax=1.0,
            showscale=False, opacity=1.0, name=name, showlegend=True,
            lighting=dict(ambient=0.6, diffuse=0.8, specular=0.1,
                          roughness=0.9),
            hovertemplate=f"{name}<br>x %{{x:.0f}}<br>y %{{y:.0f}}"
                          f"<br>z %{{z:.0f}} mm<extra></extra>"))

    fehler = [b for b in (befunde or [])
              if getattr(b, "stufe", "") == "fehler" and b.y is not None]
    if fehler:
        orte = []
        for b in fehler:
            naechste = [min(st, key=lambda s: abs(s.y - b.y))
                        for st in stapel_je_element if st]
            punkte = np.vstack([s.punkte for s in naechste])
            orte.append(punkte.mean(axis=0))
        orte = np.array(orte)
        fig.add_trace(go.Scatter3d(
            x=orte[:, 0], y=orte[:, 1], z=orte[:, 2], mode="markers",
            marker=dict(size=9, color="#c62828", symbol="x"),
            name="Durchdringung", hovertemplate="Durchdringung<extra></extra>"))

    anzahl = sum(1 for st in stapel_je_element if st)
    fig.update_layout(
        title=dict(text=f"{anzahl} Element(e) räumlich", font=dict(size=12)),
        margin=dict(l=0, r=0, t=32, b=0), height=460, paper_bgcolor="white",
        showlegend=True, legend=dict(font=dict(size=11), itemsizing="constant"),
        scene=dict(aspectmode="data",
                   xaxis=dict(title="x [mm] nach hinten"),
                   yaxis=dict(title="y [mm] ab Mitte"),
                   zaxis=dict(title="z [mm] über Boden")))
    return fig


# ------------------------------------------------ Fahrzeug und Reglement

def _rad(fig: go.Figure, mitte_x: float, radius: float, *,
         name: str) -> None:
    """Ein Rad in der Seitenansicht, als Kreis auf dem Boden."""
    t = np.linspace(0.0, 2.0 * np.pi, 80)
    fig.add_trace(go.Scatter(
        x=mitte_x + radius * np.cos(t), y=radius + radius * np.sin(t),
        mode="lines", line=dict(color="#6b7280", width=1.5),
        fill="toself", fillcolor="rgba(107,114,128,0.12)",
        name=name, hoverinfo="name"))


def _zone(fig: go.Figure, x0: float, x1: float, y0: float, y1: float,
          farbe: str, name: str) -> None:
    """Eine Keep-out- oder Grenzflaeche als getoentes Rechteck."""
    fig.add_shape(type="rect", x0=x0, x1=x1, y0=y0, y1=y1,
                  line=dict(color=farbe, width=1, dash="dot"),
                  fillcolor=_durchsichtig(farbe, 0.10), layer="below")
    fig.add_trace(go.Scatter(x=[(x0 + x1) / 2], y=[(y0 + y1) / 2],
                             mode="markers", marker=dict(size=0.1, opacity=0),
                             name=name, hoverinfo="name"))


def seitenansicht(stapel, bezug, regelsatz, zustand=None) -> go.Figure:
    """Fahrzeug von der Seite, mit den Hoehengrenzen aus T 8.2.

    Hier wird sichtbar, was die Regelampel als Zahl sagt. Eine Ampel allein
    beantwortet die Frage "wo genau ist es zu hoch?" nicht - und genau die
    stellt sich, sobald sie rot wird.

    Der Fluegel wird in seiner HOECHSTEN Lage gezeichnet, denn dort werden
    die Hoehengrenzen kritisch. Die Konstruktionslage steht blass daneben,
    damit der Unterschied sichtbar bleibt.
    """
    fig = go.Figure()
    hoch = zustand.hoch if zustand is not None else 0.0

    punkte = np.vstack([s.punkte for s in stapel])
    x_min = min(float(punkte[:, 0].min()), bezug.vorderreifen_vorderkante_x) - 150
    x_max = max(float(punkte[:, 0].max()), bezug.hinterreifen_hinterkante_x) + 150

    r = regelsatz["t8_2_1"] or {}
    vor = r.get("vor_vorderreifen") or {}
    grenze_vorn = float(vor.get("max_hoehe", 250))

    # Der Mittelbereich: 2026 die Kopfstuetzenebene mit 500 mm, 2027 die
    # REIFENOBERKANTE mit 406 mm. Bis zum 26.09.2026 stand hier fest 500 -
    # das Bild war damit grosszuegiger als die Ampel daneben, und
    # ausgerechnet im Entwurfsstand, wo man genauer hinsieht.
    kopf = r.get("vor_kopfstuetze") or {}
    if kopf:
        grenze_mitte = float(kopf["max_hoehe"])
        bis_x = bezug.kopfstuetze_x
        text_mitte = f"T 8.2.1: max {grenze_mitte:.0f} mm"
    else:
        grenze_mitte = bezug.reifenoberkante_z
        bis_x = bezug.kopfstuetze_x
        text_mitte = f"T 8.2.1: unter Reifenoberkante ({grenze_mitte:.0f} mm)"

    # Die Grenzflaechen zuerst, damit der Fluegel darueber liegt.
    bezugsebene = (0.0 if "zusatzbedingung" in vor
                   else bezug.vorderreifen_vorderkante_x)
    _zone(fig, x_min, bezugsebene, 0.0, grenze_vorn, FARBE_AKZENT,
          f"T 8.2.1: max {grenze_vorn:.0f} mm")
    _zone(fig, bezugsebene, bis_x, 0.0, grenze_mitte, "#2f6f4e", text_mitte)

    # Keep-out T 2.1.3, in der Seitenansicht der auffaelligste Bereich.
    r213 = regelsatz["t2_1_3"] or {}
    vorn = float(r213.get("abstand_vor_reifen", 75))
    hint = float(r213.get("abstand_hinter_reifen", 75))
    _zone(fig, -bezug.radius_vorne - vorn, bezug.radius_vorne + hint,
          0.0, bezug.reifen_durchmesser_vorne, "#9333ea",
          "T 2.1.3: Keep-out Vorderrad")

    _rad(fig, 0.0, bezug.radius_vorne, name="Vorderrad")
    _rad(fig, bezug.radstand, bezug.radius_hinten, name="Hinterrad")

    # Boden.
    fig.add_trace(go.Scatter(x=[x_min, x_max], y=[0, 0], mode="lines",
                             line=dict(color=FARBE_KONTUR, width=2),
                             name="Boden", hoverinfo="name"))

    # Der Fluegel: Konstruktionslage blass, hoechste Lage kraeftig.
    for schnitt in stapel:
        p = schnitt.punkte
        if hoch:
            fig.add_trace(go.Scatter(
                x=p[:, 0], y=p[:, 2], mode="lines",
                line=dict(color=FARBE_HILFE, width=1),
                name="Konstruktionslage", hoverinfo="skip"))
        fig.add_trace(go.Scatter(
            x=p[:, 0], y=p[:, 2] + hoch, mode="lines",
            line=dict(color=FARBE_KONTUR, width=1.5),
            name="höchste Lage" if hoch else "Flügel", hoverinfo="skip"))

    titel = "Seitenansicht — Höhengrenzen T 8.2.1 und Keep-out T 2.1.3"
    if hoch:
        titel += f" (Flügel {hoch:.0f} mm ausgefedert)"
    fig.update_layout(**_grundlayout(titel, hoehe=380))
    fig.update_yaxes(scaleanchor="x", scaleratio=1.0, title="z [mm]")
    fig.update_xaxes(title="x [mm] — 0 = Vorderachse, positiv nach hinten")
    return _achsen(fig)


def draufsicht(stapel, bezug, regelsatz) -> go.Figure:
    """Fahrzeug von oben, mit den Breitengrenzen aus T 8.2.2.

    Gespiegelt gezeichnet, wie der Validator auch rechnet: Das Reglement
    begrenzt ueber den BETRAG von y, und ein nur rechts modellierter Fluegel
    steht links genauso weit aussen.
    """
    fig = go.Figure()

    punkte = np.vstack([s.punkte for s in stapel])
    x_min = min(float(punkte[:, 0].min()), bezug.vorderreifen_vorderkante_x) - 150
    x_max = max(float(punkte[:, 0].max()), bezug.hinterreifen_hinterkante_x) + 150

    # Zwei Grenzen, nicht eine. Unterhalb der Schwelle gilt der aeusserste
    # Radpunkt, oberhalb 2026 der INNERSTE des Hinterrads (494,75 statt
    # 695,25 mm) und erst 2027 wieder der aeusserste. Bis zum 26.09.2026
    # zeichnete die Draufsicht immer nur rad_aussen und las ihren
    # Regelsatz gar nicht - die Auswahl im Dropdown aenderte am Bild nichts.
    r = regelsatz["t8_2_2"] or {}
    oben = r.get("oberhalb_reifenoberkante") or {}
    grenze_oben = (bezug.rad_innen_hinten if oben.get("schwelle_hoehe")
                   is not None else bezug.rad_aussen_hinten)

    for grenze, beschriftung, farbe in (
            (bezug.rad_aussen, "T 8.2.2 unten: |y| ≤ "
             f"{bezug.rad_aussen:.0f} mm", FARBE_AKZENT),
            (grenze_oben, f"T 8.2.2 oben: |y| ≤ {grenze_oben:.0f} mm",
             "#9333ea")):
        for s in (+1, -1):
            fig.add_trace(go.Scatter(
                x=[x_min, x_max], y=[s * grenze, s * grenze], mode="lines",
                line=dict(color=farbe, width=1.5, dash="dot"),
                name=beschriftung, hoverinfo="name"))

    # Die Raeder als Rechtecke in der Draufsicht.
    for mitte_x, radius, innen, aussen, name in (
            (0.0, bezug.radius_vorne, bezug.rad_innen_vorne,
             bezug.rad_aussen_vorne, "Vorderrad"),
            (bezug.radstand, bezug.radius_hinten, bezug.rad_innen_hinten,
             bezug.rad_aussen_hinten, "Hinterrad")):
        for s in (+1, -1):
            fig.add_shape(type="rect", x0=mitte_x - radius, x1=mitte_x + radius,
                          y0=s * innen, y1=s * aussen,
                          line=dict(color="#6b7280", width=1),
                          fillcolor="rgba(107,114,128,0.12)", layer="below")

    # Der Fluegel, beide Seiten.
    for schnitt in stapel:
        p = schnitt.punkte
        for s in (+1, -1):
            fig.add_trace(go.Scatter(
                x=p[:, 0], y=s * p[:, 1], mode="lines",
                line=dict(color=FARBE_KONTUR, width=1),
                name="Flügel", hoverinfo="skip"))

    fig.update_layout(**_grundlayout(
        "Draufsicht — Breitengrenze T 8.2.2", hoehe=380))
    fig.update_yaxes(scaleanchor="x", scaleratio=1.0, title="y [mm]")
    fig.update_xaxes(title="x [mm] — 0 = Vorderachse, positiv nach hinten")
    return _achsen(fig)


# ------------------------------------------------------- Druckverteilung

# Blau = Unterdruck (Sog), Rot = Ueberdruck. Die Richtung ist Konvention in
# jeder Aerodynamikveroeffentlichung; wer sie umdreht, verwirrt jeden, der
# schon einmal ein cp-Diagramm gesehen hat.
FARBSKALA_CP = [[0.0, "#1d4e8f"], [0.35, "#6b9bd2"], [0.5, "#f2f4f7"],
                [0.7, "#e8894a"], [1.0, "#b32218"]]


def druckverlauf(verlaeufe, y_schnitt: float = 0.0) -> go.Figure:
    """Der Druckbeiwert ueber die Sehne, je Element.

    **Die cp-Achse zeigt nach unten.** Das ist keine Willkuer: In dieser
    Darstellung liegt die Saugseite oben, und die Flaeche zwischen den beiden
    Aesten ist proportional zum Auftrieb - man sieht dem Bild an, wieviel
    das Element traegt. Jede Aerodynamikveroeffentlichung zeichnet es so.

    Bei einem Abtriebsfluegel ist die Saugseite die UNTERE. Oben im Bild
    liegt also die Unterseite des Profils, und das ist richtig so.
    """
    fig = go.Figure()
    farben = [FARBE_KONTUR, FARBE_AKZENT, "#ea7317", "#f4c20d"]

    for i, v in enumerate(verlaeufe):
        farbe = farben[i % len(farben)]
        # Saug- und Druckseite getrennt zeichnen, sonst laeuft die Linie an
        # der Nase quer durchs Bild zurueck.
        for maske, strich in ((v.saugseite, "solid"), (~v.saugseite, "dot")):
            if not maske.any():
                continue
            ordnung = np.argsort(v.x_rel[maske])
            fig.add_trace(go.Scatter(
                x=v.x_rel[maske][ordnung], y=v.cp[maske][ordnung],
                mode="lines", line=dict(color=farbe, width=1.8, dash=strich),
                name=f"{v.name} ({'Saug' if strich == 'solid' else 'Druck'}seite)",
                hovertemplate="x/c %{x:.3f}<br>cp %{y:.2f}<extra></extra>"))

        # Die Saugspitze markieren - sie ist die Zahl, an der das
        # Abrisskriterium haengt.
        fig.add_trace(go.Scatter(
            x=[v.saugspitze_bei], y=[v.saugspitze], mode="markers",
            marker=dict(color=farbe, size=8, symbol="circle-open",
                        line=dict(width=2)),
            name=f"{v.name}: cp_min {v.saugspitze:.2f}", hoverinfo="name"))

    fig.add_hline(y=0.0, line=dict(color=FARBE_HILFE, width=1))

    titel = "Druckverteilung"
    if y_schnitt:
        titel += f" bei y = {y_schnitt:.0f} mm"
    titel += " — reibungsfrei, Saugseite oben"
    fig.update_layout(**_grundlayout(titel, hoehe=340))
    fig.update_layout(showlegend=True,
                      legend=dict(font=dict(size=10), orientation="h",
                                  yanchor="bottom", y=1.02))
    # Invertiert: Unterdruck nach oben.
    fig.update_yaxes(autorange="reversed", title="c_p")
    fig.update_xaxes(title="x / c des jeweiligen Elements", range=[-0.02, 1.02])
    return _achsen(fig)


def druckbild(elemente, verlaeufe, bodenhoehe: float = 0.0) -> go.Figure:
    """Die Kaskade im Schnitt, Kontur nach dem Druckbeiwert eingefaerbt.

    Das Gegenstueck zum cp-Diagramm: Dort liest man Zahlen ab, hier sieht
    man auf einen Blick, WO am Profil der Sog sitzt. Beides zusammen
    beantwortet die Frage, die man beim Verschieben des Schnitts hat -
    verlagert sich die Saugspitze nach aussen, oder bleibt sie, wo sie war?

    Die Farbskala ist ueber alle Elemente GEMEINSAM: Sonst sahe ein Flap mit
    cp_min = -1,5 genauso tiefblau aus wie ein Hauptelement mit -6,6, und der
    Vergleich zwischen ihnen waere gerade das, was das Bild verhindert.
    """
    fig = go.Figure()

    alle_cp = np.concatenate([v.cp for v in verlaeufe]) if verlaeufe else np.array([0.0])
    # Symmetrisch um cp = 0, damit die Mitte der Skala wirklich der
    # Umgebungsdruck ist und nicht irgendein Zwischenwert.
    spanne = float(max(abs(alle_cp.min()), abs(alle_cp.max()), 1e-6))

    alle_x = np.concatenate([e.punkte[:, 0] for e in elemente])
    rand = 0.08 * (float(alle_x.max() - alle_x.min()) + 1e-9)

    fig.add_trace(go.Scatter(
        x=[float(alle_x.min()) - rand, float(alle_x.max()) + rand],
        y=[0.0, 0.0], mode="lines",
        line=dict(color=FARBE_KONTUR, width=2), name="Boden", hoverinfo="name"))

    for i, (element, v) in enumerate(zip(elemente, verlaeufe)):
        fig.add_trace(go.Scatter(
            x=v.punkte[:, 0], y=v.punkte[:, 1], mode="markers",
            marker=dict(color=v.cp, colorscale=FARBSKALA_CP,
                        cmin=-spanne, cmax=spanne, size=5,
                        colorbar=dict(title="c_p", thickness=12, len=0.8)
                        if i == 0 else None),
            name=v.name,
            hovertemplate="%{text}<br>cp %{marker.color:.2f}<extra></extra>",
            text=[v.name] * len(v.cp)))

    fig.update_layout(**_grundlayout(
        "Druck am Schnitt — blau ist Sog, rot Überdruck", hoehe=360))
    fig.update_yaxes(scaleanchor="x", scaleratio=1.0, title="z [mm]")
    fig.update_xaxes(title="x [mm]")
    return _achsen(fig)


# ------------------------------------------------------------ Unterboden

def unterbodenschnitt(ergebnis, ub) -> go.Figure:
    """Der Kanal von der Seite: Boden, Strasse, Kehle, Diffusor.

    Ueberhoeht gezeichnet (z fuenffach), sonst ist ein 50-mm-Kanal unter
    einem 1300 mm langen Boden ein Strich. Das steht im Titel, damit
    niemand die Winkel im Bild nachmisst.
    """
    fig = go.Figure()
    ueberhoehung = 5.0
    x, h = ergebnis.x, ergebnis.hoehe

    fig.add_trace(go.Scatter(x=[x[0] - 50, x[-1] + 50], y=[0, 0], mode="lines",
                             line=dict(color=FARBE_KONTUR, width=2),
                             name="Straße", hoverinfo="name"))

    # Der Kanal als Flaeche zwischen Strasse und Boden, nach cp eingefaerbt
    # waere schoen - aber Plotly kann keine Flaeche mit Farbverlauf. Also
    # der Boden als Linie, gefaerbt nach Abschnitt.
    diffusor_start = ub.x_start + ub.einlass_laenge + ub.kehle_laenge
    for maske, farbe, name in (
            (x <= ub.x_start + ub.einlass_laenge, FARBE_HILFE, "Einlass"),
            ((x >= ub.x_start + ub.einlass_laenge) & (x <= diffusor_start),
             FARBE_KONTUR, "Kehle"),
            (x >= diffusor_start,
             FARBE_AKZENT if ergebnis.abgeloest else "#2f6f4e",
             "Diffusor, abgelöst" if ergebnis.abgeloest else "Diffusor")):
        fig.add_trace(go.Scatter(
            x=x[maske], y=h[maske] * ueberhoehung, mode="lines",
            line=dict(color=farbe, width=3), name=name,
            customdata=h[maske],
            hovertemplate="x %{x:.0f} mm<br>Höhe %{customdata:.1f} mm<extra></extra>"))

    fig.add_trace(go.Scatter(
        x=[ergebnis.kehle_x], y=[ergebnis.kehle_hoehe * ueberhoehung],
        mode="markers+text", marker=dict(color=FARBE_KONTUR, size=8),
        text=[f"Kehle {ergebnis.kehle_hoehe:.0f} mm"], textposition="top center",
        name="engste Stelle", hoverinfo="name"))

    fig.update_layout(**_grundlayout(
        f"Unterboden im Schnitt — Höhen fünffach überhöht, "
        f"Diffusor wirksam {ergebnis.diffusor_winkel_wirksam:.1f}°", hoehe=300))
    fig.update_layout(showlegend=True, legend=dict(orientation="h", y=1.1,
                                                   font=dict(size=10)))
    fig.update_xaxes(title="x [mm] — 0 = Vorderachse")
    fig.update_yaxes(title="Höhe × 5 [mm]")
    return _achsen(fig)


def bodendruck(ergebnis) -> go.Figure:
    """cp entlang des Bodens, Achse nach unten wie beim Profil.

    Die Flaeche unter der Kurve ist der Abtrieb - man sieht, welcher
    Abschnitt ihn liefert. Beim guten Unterboden ist es die Kehle; liefert
    ihn der Einlass, ist der Kanal zu frueh zu eng.
    """
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=ergebnis.x, y=ergebnis.cp, mode="lines", fill="tozeroy",
        line=dict(color="#1d4e8f", width=2), fillcolor="rgba(29,78,143,0.15)",
        name="c_p", hovertemplate="x %{x:.0f} mm<br>c_p %{y:.2f}<extra></extra>"))
    fig.add_vline(x=ergebnis.druckpunkt_x, line=dict(color=FARBE_AKZENT, dash="dot"),
                  annotation_text=f"Druckpunkt {ergebnis.druckpunkt_x:.0f} mm",
                  annotation_position="bottom right")
    fig.add_hline(y=0.0, line=dict(color=FARBE_HILFE, width=1))
    fig.update_layout(**_grundlayout("Druck entlang des Bodens — Sog oben",
                                     hoehe=280))
    fig.update_yaxes(autorange="reversed", title="c_p")
    fig.update_xaxes(title="x [mm]")
    return _achsen(fig)


def hoehenkennlinie(kennlinie) -> go.Figure:
    """Abtrieb ueber dem Hub. Flach ist gut - steil heisst unruhiges Auto."""
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=kennlinie.hub, y=kennlinie.abtrieb, mode="lines+markers",
        line=dict(color=FARBE_KONTUR, width=2), marker=dict(size=6),
        name="Abtrieb", hovertemplate="Hub %{x:+.1f} mm<br>%{y:.1f} N<extra></extra>"))
    fig.update_layout(**_grundlayout(
        f"Abtrieb über den Federweg — Stabilität {kennlinie.stabilitaet:.2f}",
        hoehe=260))
    fig.update_xaxes(title="Hub [mm] — negativ = eingefedert")
    fig.update_yaxes(title="Abtrieb [N]", rangemode="tozero")
    return _achsen(fig)


def paretobild(lauf) -> go.Figure:
    """Die Pareto-Front: Abtrieb gegen Widerstand, Farbe = Stabilitaet.

    Ungueltige Varianten stehen grau mit drin. Man soll sehen, wo die Grenze
    verlaeuft - und dass der meiste Abtrieb oft genau jenseits davon liegt.
    Anklicken eines Frontpunkts uebernimmt ihn.
    """
    fig = go.Figure()
    front = set(lauf.front)

    ungueltig = [i for i, e in enumerate(lauf.ergebnisse)
                 if not e.get("gueltig") and e.get("widerstand") is not None]
    if ungueltig:
        fig.add_trace(go.Scatter(
            x=[lauf.ergebnisse[i]["widerstand"] for i in ungueltig],
            y=[lauf.ergebnisse[i]["abtrieb"] for i in ungueltig],
            mode="markers", marker=dict(color=FARBE_HILFE, size=6, symbol="x"),
            name="ungültig", customdata=ungueltig,
            hovertemplate="%{y:.1f} N / %{x:.1f} N — ungültig<extra></extra>"))

    for auswahl, name, groesse, linie in (
            ([i for i, e in enumerate(lauf.ergebnisse)
              if e.get("gueltig") and i not in front], "Variante", 6, 0),
            (sorted(front), "Pareto-Front", 11, 1.5)):
        if not auswahl:
            continue
        fig.add_trace(go.Scatter(
            x=[lauf.ergebnisse[i]["widerstand"] for i in auswahl],
            y=[lauf.ergebnisse[i]["abtrieb"] for i in auswahl],
            mode="markers", name=name, customdata=auswahl,
            marker=dict(size=groesse,
                        color=[lauf.ergebnisse[i]["stabilitaet"] for i in auswahl],
                        colorscale="Viridis", cmin=0.0, cmax=1.0,
                        line=dict(color=FARBE_KONTUR, width=linie),
                        colorbar=dict(title="Stabilität", thickness=12)
                        if name == "Pareto-Front" else None),
            text=[f"{lauf.ergebnisse[i]['stabilitaet']:.2f}" for i in auswahl],
            hovertemplate="Variante %{customdata}<br>%{y:.1f} N Abtrieb<br>"
                          "%{x:.1f} N Widerstand<br>Stabilität %{text}"
                          "<extra></extra>"))

    # Die Front laeuft ueber DREI Ziele, das Bild zeigt zwei. Frontpunkte bei
    # wenig Abtrieb und viel Widerstand sind deshalb kein Fehler - sie
    # gewinnen bei der Stabilitaet. Ohne diesen Satz haelt man die Rechnung
    # fuer kaputt, sobald man das Bild zum ersten Mal sieht.
    fig.add_annotation(
        text="Front über drei Ziele: Punkte, die hier dominiert wirken, "
             "liegen bei der Stabilität (Farbe) vorn.",
        xref="paper", yref="paper", x=0.0, y=-0.3, showarrow=False,
        xanchor="left", font=dict(size=11, color="#6b7280"))

    fig.update_layout(**_grundlayout(
        f"{len(lauf.varianten)} Varianten, {len(lauf.front)} auf der Front — "
        f"anklicken übernimmt", hoehe=440))
    # Legende UNTER den Titel und Platz dafuer: Oben uebereinander gelegt
    # schnitten sie sich gegenseitig ab.
    fig.update_layout(showlegend=True, hovermode="closest",
                      margin=dict(l=55, r=20, t=75, b=105),
                      legend=dict(orientation="h", y=1.02, yanchor="bottom",
                                  x=0.0, font=dict(size=10)))
    fig.update_xaxes(title="Widerstand [N] — weniger ist besser")
    fig.update_yaxes(title="Abtrieb [N] — mehr ist besser")
    return _achsen(fig)


def balancebild(bilanz, ziel: float | None = None) -> go.Figure:
    """Seitenansicht mit den Abtriebskraeften als Pfeile nach unten.

    Die Achsen als senkrechte Linien, dazwischen der Druckpunkt des ganzen
    Autos. Ein Blick zeigt, welches Teil die Balance wohin zieht.
    """
    fig = go.Figure()
    L = bilanz.radstand
    groesster = max([abs(b.abtrieb) for b in bilanz.beitraege] + [1.0])
    for x, name in ((0.0, "Vorderachse"), (L, "Hinterachse")):
        fig.add_vline(x=x, line=dict(color=FARBE_HILFE, width=2),
                      annotation_text=name, annotation_position="top")

    for i, b in enumerate(bilanz.beitraege):
        farbe = ELEMENTFARBEN[i % len(ELEMENTFARBEN)]
        fig.add_trace(go.Bar(
            x=[b.x], y=[-b.abtrieb], width=[max(60.0, L * 0.05)],
            marker_color=farbe, name=b.name,
            text=[f"{b.name}<br>{b.abtrieb:.0f} N"], textposition="outside",
            cliponaxis=False, constraintext="none", textfont=dict(size=11),
            hovertemplate=(f"{b.name}<br>{b.abtrieb:.0f} N bei x = {b.x:.0f} mm"
                           f"<br>Widerstand {b.widerstand:.1f} N in "
                           f"{b.z:.0f} mm Höhe<extra></extra>")))

    if math.isfinite(bilanz.druckpunkt_x):
        fig.add_vline(x=bilanz.druckpunkt_x,
                      line=dict(color=FARBE_AKZENT, width=2, dash="dash"),
                      annotation_text=f"Druckpunkt {bilanz.druckpunkt_x:.0f} mm",
                      annotation_position="top right")
    if ziel is not None:
        # Wo der Druckpunkt fuer die Zielbalance liegen muesste.
        x_ziel = bilanz.druckpunkt_fuer(ziel)
        fig.add_vline(x=x_ziel, line=dict(color=FARBE_ZIEL, width=2, dash="dot"),
                      annotation_text=f"Ziel {ziel:.0f} % vorn",
                      annotation_position="bottom right")

    titel = (f"Balance {100 * bilanz.balance_vorne:.1f} % vorn — "
             f"{bilanz.abtrieb:.0f} N bei {bilanz.geschwindigkeit:.0f} m/s"
             if math.isfinite(bilanz.balance_vorne) else "Kein Abtrieb")
    fig.update_layout(**_grundlayout(titel, hoehe=340))
    fig.update_layout(barmode="overlay", bargap=0,
                      legend=dict(orientation="h", y=-0.2))
    lagen = [b.x for b in bilanz.beitraege] + [0.0, L]
    fig.update_xaxes(title="x ab Vorderachse [mm]",
                     range=[min(lagen) - 250.0, max(lagen) + 250.0])
    fig.update_yaxes(title="Abtrieb [N]", range=[-1.5 * groesster, 0.1 * groesster])
    return _achsen(fig)


def wanderungsbild(reihe, ziel: float | None = None) -> go.Figure:
    """Balance ueber dem Nickwinkel - flach ist gut."""
    fig = go.Figure()
    x = [b.zustand.nick_grad for b in reihe]
    y = [100.0 * b.balance_vorne for b in reihe]
    fig.add_trace(go.Scatter(
        x=x, y=y, mode="lines+markers", name="Balance vorn",
        line=dict(color=FARBE_KONTUR, width=2), marker=dict(size=7),
        text=[b.zustand.name for b in reihe],
        customdata=[b.abtrieb for b in reihe],
        hovertemplate="%{text}<br>%{y:.1f} % vorn, %{customdata:.0f} N"
                      "<extra></extra>"))
    if ziel is not None:
        fig.add_hline(y=float(ziel), line=dict(color=FARBE_ZIEL, dash="dot"),
                      annotation_text=f"Ziel {ziel:.0f} %")
    fig.update_layout(**_grundlayout("Nickwanderung der Balance", hoehe=300))
    fig.update_xaxes(title="Nicken [°] — positiv = Nase tiefer (Bremsen)")
    fig.update_yaxes(title="Abtrieb auf der Vorderachse [%]")
    return _achsen(fig)


def paketbild(lauf) -> go.Figure:
    """Pareto-Front des Paket-DoE: Abtrieb ueber dem Balancefehler, Farbe =
    Nickwanderung. Links oben ist gut: viel Abtrieb, Balance am Ziel."""
    fig = go.Figure()
    front = set(lauf.front)
    alle = [i for i, e in enumerate(lauf.ergebnisse)
            if e.get("balancefehler") is not None and e.get("abtrieb") is not None]
    ungueltig = [i for i in alle if not lauf.ergebnisse[i].get("gueltig")]
    if ungueltig:
        fig.add_trace(go.Scatter(
            x=[lauf.ergebnisse[i]["balancefehler"] for i in ungueltig],
            y=[lauf.ergebnisse[i]["abtrieb"] for i in ungueltig],
            mode="markers", marker=dict(color=FARBE_HILFE, size=6, symbol="x"),
            name="ungültig", customdata=ungueltig,
            hovertemplate="Variante %{customdata} — ungültig<extra></extra>"))

    wanderungen = [lauf.ergebnisse[i]["wanderung"] for i in alle
                   if lauf.ergebnisse[i].get("gueltig")
                   and lauf.ergebnisse[i].get("wanderung") is not None]
    obergrenze = max(wanderungen + [0.1])
    for auswahl, name, groesse, linie in (
            ([i for i in alle if lauf.ergebnisse[i].get("gueltig")
              and i not in front], "Variante", 6, 0),
            (sorted(front), "Pareto-Front", 11, 1.5)):
        if not auswahl:
            continue
        e = [lauf.ergebnisse[i] for i in auswahl]
        fig.add_trace(go.Scatter(
            x=[r["balancefehler"] for r in e], y=[r["abtrieb"] for r in e],
            mode="markers", name=name, customdata=auswahl,
            marker=dict(size=groesse, color=[r.get("wanderung") or 0.0 for r in e],
                        colorscale="Viridis_r", cmin=0.0, cmax=obergrenze,
                        line=dict(color=FARBE_KONTUR, width=linie),
                        colorbar=dict(title="Wanderung<br>[%/°]", thickness=12)
                        if name == "Pareto-Front" else None),
            text=[f"{r['balance']:.1f} % vorn, Wanderung "
                  f"{r.get('wanderung') or 0.0:.2f} %/°" for r in e],
            hovertemplate="Variante %{customdata}<br>%{y:.0f} N<br>%{text}"
                          "<extra></extra>"))

    fig.add_annotation(
        text="Front über drei Ziele: Punkte, die hier dominiert wirken, "
             "wandern beim Nicken weniger (Farbe).",
        xref="paper", yref="paper", x=0.0, y=-0.3, showarrow=False,
        xanchor="left", font=dict(size=11, color="#6b7280"))
    fig.update_layout(**_grundlayout(
        f"{len(lauf.varianten)} Varianten, {len(lauf.front)} auf der Front — "
        f"anklicken zeigt die Werte", hoehe=440))
    fig.update_layout(showlegend=True, hovermode="closest",
                      margin=dict(l=55, r=20, t=75, b=105),
                      legend=dict(orientation="h", y=1.02, yanchor="bottom",
                                  x=0.0, font=dict(size=10)))
    fig.update_xaxes(title="Abstand zur Zielbalance [Prozentpunkte] — weniger ist besser",
                     rangemode="tozero")
    fig.update_yaxes(title="Abtrieb [N]")
    return _achsen(fig)
