"""
Zweidimensionales Panelverfahren für MEHRERE Profile.

Warum das sein muss: NeuralFoil kennt nur das einzelne Profil. Eine Kaskade
lebt aber genau davon, dass die Elemente sich gegenseitig beeinflussen — der
Spalt zwischen Hauptelement und Flap beschleunigt die Strömung und hält sie
anliegend. Ohne ein Verfahren, das mehrere Körper gleichzeitig sieht, lässt
sich ein zweites Element weder auslegen noch bewerten.

**Verfahren:** Hess-Smith. Jedes Panel trägt eine konstante Quellstärke, jeder
Körper zusätzlich EINE über den ganzen Körper konstante Wirbelstärke. Die
Unbekannten sind damit N Quellstärken plus M Wirbelstärken, die Gleichungen N
Tangentialbedingungen plus M Kutta-Bedingungen. Das ist die klassische
Formulierung für Mehrkörperprobleme: Jeder Körper bekommt seine eigene
Zirkulation, und die stellt sich aus der Kutta-Bedingung an seiner eigenen
Hinterkante ein.

**Reibungsfrei.** Das Verfahren kennt keine Grenzschicht und damit keinen
Abriss. Es liefert die Zirkulation, die sich ohne Reibung einstellen würde —
bei anliegender Strömung ist das eine gute Näherung, im Abriss völlig falsch.
Deshalb wird es hier nie allein benutzt, sondern immer im Verhältnis zum
Einzelprofil: Das Panelverfahren sagt, um welchen FAKTOR die Kaskade den
Auftrieb des Einzelprofils anhebt, und dieser Faktor wird auf den zähen
Beiwert aus NeuralFoil angewendet. Siehe kaskade.py.

**Boden** über Spiegelung: Zu jedem Panel gehört ein gespiegeltes mit
gleicher Quellstärke und umgekehrter Wirbelstärke. Damit ist die Bodenebene
undurchlässig.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass
class Koerper:
    """Ein Profil im Panelverfahren, in Metern oder Millimetern — einerlei,
    solange alle Körper dieselbe Einheit benutzen."""

    punkte: np.ndarray          # Nx2, im Uhrzeigersinn ab Hinterkante (Selig)
    name: str = ""

    @property
    def sehne(self) -> float:
        return float(np.ptp(self.punkte[:, 0]))


@dataclass
class Panelloesung:
    """Ergebnis einer Panelrechnung."""

    cl_gesamt: float
    cl_je_koerper: np.ndarray
    cp: list[np.ndarray]           # Druckbeiwert je Körper und Panel
    zirkulation: np.ndarray        # je Körper
    geschwindigkeit: list[np.ndarray]   # Tangentialgeschwindigkeit je Panel
    bezugssehne: float
    # Der Widerstand einer reibungsfreien Rechnung MUSS null sein (d'Alembert).
    # Steht hier etwas Nennenswertes, ist die Vernetzung zu grob oder die
    # Loesung krumm - deshalb wird der Wert mitgeliefert statt weggeworfen.
    cd_scheinbar: float = 0.0


def umlaufsinn(punkte: np.ndarray) -> float:
    """+1 gegen den Uhrzeigersinn, -1 im Uhrzeigersinn. Über die Gaußsche
    Trapezformel, also über das Vorzeichen der eingeschlossenen Fläche."""
    x, y = punkte[:, 0], punkte[:, 1]
    flaeche = 0.5 * np.sum(x[:-1] * y[1:] - x[1:] * y[:-1])
    return 1.0 if flaeche > 0 else -1.0


def _panelgeometrie(punkte: np.ndarray):
    """Mittelpunkte, Längen, Winkel, Tangenten und Normalen der Panels.

    Die Normale muss NACH AUSSEN zeigen, sonst steht die ganze
    Tangentialbedingung auf dem Kopf. Welche der beiden Senkrechten das ist,
    hängt am Umlaufsinn - und der ist bei Profildateien nicht einheitlich:
    Manche laufen von der Hinterkante über die Oberseite, manche über die
    Unterseite. Deshalb wird er gemessen und nicht angenommen.

    Ein erster Anlauf nahm fest die linke Senkrechte. Beim Zylinder, den der
    Test im Uhrzeigersinn aufbaute, stimmte das; beim Profil zeigten alle
    Normalen nach innen, und heraus kam ein Profil ohne Auftrieb.

    Der zweite Anlauf waehlte die Senkrechte je nach Umlaufsinn - und lief in
    dieselbe Falle an anderer Stelle: Der Sonderfall fuer das eigene Panel in
    `_einfluss` haengt ebenfalls am Umlaufsinn, weil dort das Panel-eigene
    Koordinatensystem benutzt wird. Zwei gekoppelte Fallunterscheidungen an
    verschiedenen Stellen sind eine Fehlerquelle, keine Loesung.

    Deshalb wird die Eingabe in `loese` einmal auf den Uhrzeigersinn gedreht.
    Hier steht dann fest die linke Senkrechte, und die zeigt nach aussen.
    """
    a = punkte[:-1]
    b = punkte[1:]
    mitte = 0.5 * (a + b)
    d = b - a
    laenge = np.linalg.norm(d, axis=1)
    theta = np.arctan2(d[:, 1], d[:, 0])
    tangente = d / laenge[:, None]
    normale = np.column_stack([-tangente[:, 1], tangente[:, 0]])
    return mitte, laenge, theta, tangente, normale


def im_uhrzeigersinn(punkte: np.ndarray) -> np.ndarray:
    """Dreht einen geschlossenen Streckenzug auf den Uhrzeigersinn.

    Profildateien laufen mal so und mal so herum - Selig von der Hinterkante
    ueber die Oberseite, Lednicer getrennt nach Seiten. Statt das an drei
    Stellen abzufangen, wird hier einmal vereinheitlicht.
    """
    return punkte[::-1] if umlaufsinn(punkte) > 0 else punkte


def _einfluss(ziel: np.ndarray, a: np.ndarray, b: np.ndarray,
              theta: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Geschwindigkeit an `ziel` durch Panels mit Einheits-Quell- und
    -Wirbelstärke.

    Gibt zwei (Z, P, 2)-Felder zurück: den Beitrag der Quellbelegung und den
    der Wirbelbelegung, jeweils im globalen Koordinatensystem.

    Gerechnet wird im Panel-Koordinatensystem, in dem das Panel von (0,0) bis
    (L,0) läuft; dort sind die Formeln geschlossen und stabil. Anschließend
    zurückgedreht.
    """
    z = ziel[:, None, :]                     # (Z,1,2)
    versatz = z - a[None, :, :]              # (Z,P,2)

    kos, sin = np.cos(theta), np.sin(theta)
    # In Panelkoordinaten drehen.
    xp = versatz[..., 0] * kos + versatz[..., 1] * sin
    zp = -versatz[..., 0] * sin + versatz[..., 1] * kos
    laenge = np.linalg.norm(b - a, axis=1)[None, :]

    r1 = np.hypot(xp, zp)
    r2 = np.hypot(xp - laenge, zp)
    # Winkel, den das Panel am Zielpunkt aufspannt. atan2 waehlt den Zweig
    # richtig: Liegt der Punkt AUF dem Panel, ergibt sich genau pi.
    dtheta = np.arctan2(zp, xp - laenge) - np.arctan2(zp, xp)

    # Liegt der Zielpunkt auf dem Panel selbst, muessen die Grenzwerte von
    # Hand gesetzt werden - und zwar BEIDE konsistent. Rechnerisch ist die
    # Formel dort zwar regulaer (r1 = r2 = L/2, dtheta = pi), aber zp ist
    # eine Rundungsnull, deren VORZEICHEN kippen kann. Kippt es, springt
    # dtheta von +pi auf -pi und die Diagonale der Matrix dreht sich um.
    #
    # Zwei Anlaeufe sind hier schon gescheitert: einmal mit u_w = +1/2, was
    # der Formel widersprach und ein Profil ohne Auftrieb ergab; einmal ganz
    # ohne Sonderfall, was am kippenden Vorzeichen scheiterte und sogar den
    # Zylinder zerlegte. Richtig ist: Quelle 1/2 nach aussen, Wirbel -1/2
    # tangential, entsprechend dem Grenzwert von aussen.
    eigen = (np.abs(zp) < 1e-9 * np.maximum(laenge, 1e-12)) &             (xp > 1e-9) & (xp < laenge - 1e-9)

    laenge_log = np.log(np.maximum(r1, 1e-300) / np.maximum(r2, 1e-300))
    u_q = np.where(eigen, 0.0, laenge_log / (2 * np.pi))
    w_q = np.where(eigen, 0.5, dtheta / (2 * np.pi))
    # Die Wirbelbelegung ist die um 90 Grad gedrehte Quellbelegung.
    u_w = np.where(eigen, -0.5, -dtheta / (2 * np.pi))
    w_w = np.where(eigen, 0.0, laenge_log / (2 * np.pi))

    def zurueck(u, w):
        return np.stack([u * kos - w * sin, u * sin + w * kos], axis=-1)

    return zurueck(u_q, w_q), zurueck(u_w, w_w)


def loese(koerper: list[Koerper], alpha_grad: float = 0.0,
          mit_boden: bool = False, bodenhoehe: float = 0.0,
          bezugssehne: float | None = None) -> Panelloesung:
    """Löst die Umströmung mehrerer Profile.

    `alpha_grad` dreht die ANSTRÖMUNG, nicht die Körper - so bleiben die
    Koordinaten der Körper unverändert, was bei einer Kaskade wichtig ist:
    Die Elemente stehen zueinander fest, gedreht wird das ganze Paket.

    `bodenhoehe` ist die z-Lage der Bodenebene in denselben Einheiten wie die
    Punkte. Gespiegelt wird daran.
    """
    alpha = np.radians(float(alpha_grad))
    anstroemung = np.array([np.cos(alpha), np.sin(alpha)])

    # Einmal vereinheitlichen, damit die linke Senkrechte ueberall nach aussen
    # zeigt und der Sonderfall in _einfluss eindeutig bleibt.
    punkte_je = [im_uhrzeigersinn(k.punkte) for k in koerper]
    geo = [_panelgeometrie(pk) for pk in punkte_je]
    anzahl = [len(g[1]) for g in geo]
    n = sum(anzahl)
    m = len(koerper)

    a_alle = np.vstack([pk[:-1] for pk in punkte_je])
    b_alle = np.vstack([pk[1:] for pk in punkte_je])
    theta_alle = np.concatenate([g[2] for g in geo])
    mitte_alle = np.vstack([g[0] for g in geo])
    tangente_alle = np.vstack([g[3] for g in geo])
    normale_alle = np.vstack([g[4] for g in geo])

    quelle, wirbel = _einfluss(mitte_alle, a_alle, b_alle, theta_alle)

    if mit_boden:
        spiegel = np.array([1.0, -1.0])
        versatz = np.array([0.0, 2.0 * bodenhoehe])
        a_s = (a_alle - versatz) * spiegel + versatz * 0
        b_s = (b_alle - versatz) * spiegel + versatz * 0
        # Spiegelung an z = bodenhoehe: z -> 2*bodenhoehe - z. Die Reihenfolge
        # der Panelenden wird dabei NICHT getauscht; die Umkehrung des
        # Umlaufsinns steckt im Vorzeichen der Wirbelstaerke.
        a_s = np.column_stack([a_alle[:, 0], 2.0 * bodenhoehe - a_alle[:, 1]])
        b_s = np.column_stack([b_alle[:, 0], 2.0 * bodenhoehe - b_alle[:, 1]])
        theta_s = np.arctan2((b_s - a_s)[:, 1], (b_s - a_s)[:, 0])
        quelle_s, wirbel_s = _einfluss(mitte_alle, a_s, b_s, theta_s)
        quelle = quelle + quelle_s
        wirbel = wirbel - wirbel_s        # Spiegelwirbel dreht sich um

    # Zuordnung Panel -> Koerper
    koerper_von_panel = np.concatenate([np.full(k, i) for i, k in enumerate(anzahl)])

    # --- Gleichungssystem -------------------------------------------------
    A = np.zeros((n + m, n + m))
    rechte = np.zeros(n + m)

    # Tangentialbedingung: keine Normalgeschwindigkeit auf jedem Panel.
    A[:n, :n] = np.einsum("zpk,zk->zp", quelle, normale_alle)
    for j in range(m):
        maske = koerper_von_panel == j
        A[:n, n + j] = np.einsum("zpk,zk->z", wirbel[:, maske, :], normale_alle)
    rechte[:n] = -normale_alle @ anstroemung

    # Kutta-Bedingung je Koerper: Die Tangentialgeschwindigkeit auf dem ersten
    # und dem letzten Panel muss betragsgleich und gegenlaeufig sein. Beide
    # liegen an der Hinterkante, ober- und unterseitig.
    start = 0
    for j, k in enumerate(anzahl):
        erstes, letztes = start, start + k - 1
        t_summe = tangente_alle[erstes] + tangente_alle[letztes]
        A[n + j, :n] = (quelle[erstes] @ tangente_alle[erstes]
                        + quelle[letztes] @ tangente_alle[letztes])
        for jj in range(m):
            maske = koerper_von_panel == jj
            A[n + j, n + jj] = (wirbel[erstes, maske, :] @ tangente_alle[erstes]
                                ).sum() + (wirbel[letztes, maske, :]
                                           @ tangente_alle[letztes]).sum()
        rechte[n + j] = -t_summe @ anstroemung
        start += k

    loesung = np.linalg.solve(A, rechte)
    sigma, gamma = loesung[:n], loesung[n:]

    # --- Auswertung -------------------------------------------------------
    geschwindigkeit = np.einsum("zpk,p->zk", quelle, sigma) + anstroemung
    for j in range(m):
        maske = koerper_von_panel == j
        geschwindigkeit = geschwindigkeit + gamma[j] * wirbel[:, maske, :].sum(axis=1)

    v_t = np.einsum("zk,zk->z", geschwindigkeit, tangente_alle)
    cp_alle = 1.0 - v_t ** 2

    sehne = bezugssehne if bezugssehne is not None else max(k.sehne for k in koerper)

    # Auftrieb aus dem DRUCK, nicht aus der Zirkulation. Der Weg ueber die
    # Zirkulation braucht eine Vorzeichenverabredung ueber den Umlaufsinn, und
    # genau daran ist ein erster Anlauf gescheitert: Das Vorzeichen war
    # gedreht und der Betrag um ein Viertel zu klein. Die Druckintegration
    # kennt diese Falle nicht - und sie prueft sich selbst, weil der
    # Widerstand einer reibungsfreien Rechnung null sein muss (d'Alembert).
    laenge_alle = np.concatenate([g[1] for g in geo])
    kraft = -cp_alle[:, None] * normale_alle * laenge_alle[:, None]

    kos, sin = np.cos(alpha), np.sin(alpha)
    cl_je = np.zeros(m)
    cd_je = np.zeros(m)
    start = 0
    for j, k in enumerate(anzahl):
        fx, fz = kraft[start:start + k].sum(axis=0)
        cl_je[j] = (fz * kos - fx * sin) / sehne
        cd_je[j] = (fx * kos + fz * sin) / sehne
        start += k

    cp_liste, v_liste = [], []
    start = 0
    for k in anzahl:
        cp_liste.append(cp_alle[start:start + k])
        v_liste.append(v_t[start:start + k])
        start += k

    return Panelloesung(cl_gesamt=float(cl_je.sum()), cl_je_koerper=cl_je,
                        cd_scheinbar=float(cd_je.sum()),
                        cp=cp_liste, zirkulation=gamma,
                        geschwindigkeit=v_liste, bezugssehne=float(sehne))


def aus_profil(profil, sehne: float = 1.0, anstellwinkel: float = 0.0,
               punkte: int = 100, versatz=(0.0, 0.0), name: str = "") -> Koerper:
    """Macht aus einem Profil einen Panelkörper an gewünschter Stelle."""
    p = profil.repanelisiert(punkte).angestellt(anstellwinkel, sehne)
    return Koerper(punkte=p + np.asarray(versatz, dtype=float),
                   name=name or getattr(profil, "name", ""))
