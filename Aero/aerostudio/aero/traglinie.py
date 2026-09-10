"""
Vom Profil zum Flügel — Traglinienrechnung mit Bodeneinfluss.

Warum das überhaupt nötig ist: Ein Profilbeiwert von CL = 2,0 heißt nicht,
dass der Flügel CL = 2,0 hat. Ein endlicher Flügel erzeugt an den Enden
Wirbel, die über die ganze Spannweite eine Zusatzströmung induzieren. Der
Flügel sieht dadurch einen kleineren Anstellwinkel als eingestellt. Bei einem
Formula-Student-Frontflügel mit Streckung um 5 geht dabei rund ein Drittel
des Profilauftriebs verloren.

**Verfahren:** Hufeisenwirbel nach Weissinger — gebundener Wirbel auf der
Viertelsehne, Kontrollpunkt auf der Dreiviertelsehne. Das Gleichungssystem
wird GELÖST, nicht iteriert. Ein erster Versuch, die Zirkulation direkt
iterativ nachzuführen, schaukelte sich auf: Die Selbstinduktion eines
Streifens wächst mit 1/Streifenbreite, und schmale Streifen an den
Flügelenden trieben die induzierten Winkel auf über 80 Grad. Beim Lösen des
Systems ist genau diese starke Kopplung kein Problem, sondern die Hauptsache.

Die Zähigkeit kommt als KORREKTUR obendrauf: Nach jedem Lösen wird verglichen,
welchen Beiwert die reibungsfreie Rechnung liefert und welchen das echte
Profil bei diesem wirksamen Winkel hätte. Die Differenz wird als kleiner
Zusatzwinkel eingespeist und erneut gelöst. Damit bleibt der Abriss im
Modell - ein Flügel, dessen Wurzel schon abgerissen ist, bekommt dort keinen
Auftrieb mehr zugeschrieben.

**Bodeneinfluss** über das Spiegelbild an der Bodenebene: Zu jedem
Hufeisenwirbel gehört einer bei negativer Höhe mit umgekehrter Zirkulation.
Das erzwingt, dass durch die Bodenebene keine Strömung hindurchgeht.

**Was dieses Modell NICHT kann, und das ist die wichtigste Stelle hier:**

Der Bodeneffekt eines Abtriebsflügels hat zwei Anteile. Der eine ist die
veränderte induzierte Strömung - den bildet die Spiegelung ab. Der andere ist
die Beschleunigung im Kanal zwischen Flügelunterseite und Boden. Die steckt
hier nicht drin. Das Modell UNTERSCHÄTZT den Abtrieb bei kleinem Bodenabstand
deshalb, und es kennt den Einbruch bei sehr kleinem Abstand nicht, wenn die
Strömung im Kanal abreisst.

Ebenfalls nicht enthalten: Endplatten, Räder, die Wirkung mehrerer Elemente
aufeinander, der Aufstau vor dem Fahrzeug. Endplatten wirken wie eine
Verlängerung der Spannweite und heben den Abtrieb zusätzlich.

Kurz: Die Zahl ist eine ABSCHÄTZUNG für den Vergleich von Entwürfen
untereinander, kein Ersatz für CFD und erst recht nicht für den Prüfstand.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from .profilpolare import DICHTE, Polare, polare, reynolds

# Anströmrichtung im Werkzeug-Koordinatensystem: x zeigt nach hinten, die Luft
# strömt relativ zum Fahrzeug also in +x.
STROMRICHTUNG = np.array([1.0, 0.0, 0.0])

# Auftriebsanstieg der ebenen Platte, je GRAD. Wird gebraucht, um eine
# Beiwertdifferenz in einen Korrekturwinkel umzurechnen.
CL_ALPHA_GRAD = 2.0 * np.pi * np.pi / 180.0


@dataclass
class Streifen:
    """Ein Spannweitenabschnitt des Flügels. Längen in mm, Winkel in Grad."""

    y: float
    breite: float
    sehne: float
    winkel: float       # geometrischer Anstellwinkel
    hoehe: float        # Höhe der Viertelsehne über Boden
    x_viertel: float


@dataclass
class Fluegelkraefte:
    """Ergebnis einer Traglinienrechnung. Kräfte in Newton, Abtrieb positiv."""

    abtrieb: float
    widerstand: float
    widerstand_induziert: float
    widerstand_profil: float
    flaeche: float                 # m2, Grundriss der GANZEN Spannweite
    geschwindigkeit: float         # m/s
    cl: float                      # auf die Grundrissfläche bezogen, negativ = Abtrieb
    cd: float
    streifen: list[Streifen] = field(default_factory=list)
    cl_lokal: np.ndarray = field(default_factory=lambda: np.array([]))
    alpha_induziert: np.ndarray = field(default_factory=lambda: np.array([]))
    alpha_wirksam: np.ndarray = field(default_factory=lambda: np.array([]))
    auftrieb_lokal: np.ndarray = field(default_factory=lambda: np.array([]))
    vertrauen: float = 1.0         # flächengewichtet, nicht der schlechteste Streifen
    abgerissen: float = 0.0        # Flächenanteil jenseits des Abrisses
    schritte: int = 0
    konvergiert: bool = True

    @property
    def wirkungsgrad(self) -> float:
        """Abtrieb je Widerstand. Am Rennwagen die Zahl, die zählt."""
        return abs(self.abtrieb) / max(self.widerstand, 1e-9)

    @property
    def streckung(self) -> float:
        if not self.streifen:
            return 0.0
        y = np.array([s.y for s in self.streifen])
        breite = np.array([s.breite for s in self.streifen])
        spannweite = (y + breite / 2).max() - (y - breite / 2).min()
        return float((spannweite / 1000.0) ** 2 / max(self.flaeche, 1e-9))

    def __str__(self) -> str:
        return (f"{self.abtrieb:7.1f} N Abtrieb, {self.widerstand:6.1f} N Widerstand "
                f"bei {self.geschwindigkeit:.1f} m/s   "
                f"CL {self.cl:+.3f}  CD {self.cd:.4f}  L/D {self.wirkungsgrad:.1f}")


# ------------------------------------------------------------ Wirbelrechnung

def _strecke(punkte, a, b, kern: float = 1e-9):
    """Biot-Savart für ein gerades Wirbelstück von a nach b, Zirkulation 1."""
    r1 = punkte - a
    r2 = punkte - b
    r0 = b - a

    kreuz = np.cross(r1, r2)
    nenner = np.sum(kreuz * kreuz, axis=-1)
    l1 = np.linalg.norm(r1, axis=-1)
    l2 = np.linalg.norm(r2, axis=-1)

    # Direkt auf dem Wirbelfaden ist die Formel singulär. Ein realer Wirbel
    # hat einen Kern endlicher Dicke; hier wird der Beitrag dort auf null
    # gesetzt, was numerisch dasselbe leistet.
    gueltig = (nenner > kern) & (l1 > kern) & (l2 > kern)
    zaehler = np.sum(r0 * (r1 / np.maximum(l1, kern)[..., None]
                           - r2 / np.maximum(l2, kern)[..., None]), axis=-1)
    faktor = np.where(gueltig, zaehler / np.maximum(nenner, kern), 0.0)
    return kreuz * faktor[..., None] / (4.0 * np.pi)


def _halbgerade(punkte, a, richtung, kern: float = 1e-9):
    """Biot-Savart für einen Wirbelfaden von a bis ins Unendliche.

    Grenzwert der Streckenformel für unendliche Länge:
        v = 1/(4 pi) * (u x r) / |u x r|^2 * (1 + (u.r)/|r|)
    """
    r = punkte - a
    u = np.asarray(richtung, dtype=float)
    u = u / np.linalg.norm(u)

    kreuz = np.cross(np.broadcast_to(u, r.shape), r)
    nenner = np.sum(kreuz * kreuz, axis=-1)
    laenge = np.linalg.norm(r, axis=-1)

    gueltig = (nenner > kern) & (laenge > kern)
    zaehler = 1.0 + np.sum(u * r, axis=-1) / np.maximum(laenge, kern)
    faktor = np.where(gueltig, zaehler / np.maximum(nenner, kern), 0.0)
    return kreuz * faktor[..., None] / (4.0 * np.pi)


def _hufeisen(punkte, a, b, nur_nachlauf: bool = False):
    """Ein Hufeisenwirbel, Zirkulation 1.

    Der Faden kommt von stromab aus dem Unendlichen nach a, läuft gebunden
    von a nach b und geht von b wieder ins Unendliche.

    `nur_nachlauf` lässt das gebundene Stück weg. Das wird für den
    induzierten Winkel gebraucht: Der Abwind, der den Flügel schräg anströmt,
    stammt aus der Wirbelschleppe. Die Wirkung des gebundenen Wirbels ist
    dagegen der ebene Auftrieb selbst und darf nicht doppelt gezählt werden.
    """
    v = (-_halbgerade(punkte, a, STROMRICHTUNG)
         + _halbgerade(punkte, b, STROMRICHTUNG))
    if not nur_nachlauf:
        v = v + _strecke(punkte, a, b)
    return v


def einflussmatrix(kontrollpunkte: np.ndarray, kanten: np.ndarray,
                   mit_boden: bool = True,
                   nur_nachlauf: bool = False) -> np.ndarray:
    """Vertikale Geschwindigkeit je Kontrollpunkt und Hufeisenwirbel.

    `kanten` sind die N+1 Eckpunkte der gebundenen Wirbel auf der
    Viertelsehne; daraus entstehen N Hufeisen.

    Mit `mit_boden` bekommt jeder Wirbel sein Spiegelbild an der Ebene z = 0
    mit umgekehrter Zirkulation. Dass die Ebene dadurch undurchlässig wird,
    misst der Test test_boden_ist_undurchlaessig direkt nach.
    """
    kontrollpunkte = np.atleast_2d(np.asarray(kontrollpunkte, dtype=float))
    kanten = np.asarray(kanten, dtype=float)
    n = len(kanten) - 1
    A = np.zeros((len(kontrollpunkte), n))
    spiegelung = np.array([1.0, 1.0, -1.0])

    for j in range(n):
        v = _hufeisen(kontrollpunkte, kanten[j], kanten[j + 1], nur_nachlauf)
        if mit_boden:
            v = v - _hufeisen(kontrollpunkte, kanten[j] * spiegelung,
                              kanten[j + 1] * spiegelung, nur_nachlauf)
        A[:, j] = v[:, 2]
    return A


# ----------------------------------------------------------------- Streifen

def _viertelpunkt(schnitt) -> np.ndarray:
    """Der Punkt auf der Viertelsehne eines Schnitts.

    Nase ist der von der Hinterkante am weitesten entfernte Punkt - dieselbe
    Definition, mit der das Profilmodul normiert. So bleiben beide Rechnungen
    konsistent.
    """
    p = schnitt.punkte
    hinten = p[0]
    nase = p[int(np.argmax(np.linalg.norm(p - hinten, axis=1)))]
    return nase + 0.25 * (hinten - nase)


def _kantenverteilung(innen: float, aussen: float, panels: int) -> np.ndarray:
    """Streifenkanten für eine Flügelhälfte.

    Kosinusverdichtung an den Enden, weil sich die Zirkulation dort am
    schnellsten ändert. Reicht der Flügel bis zur Fahrzeugmitte, wird nur
    AUSSEN verdichtet: Innen setzt sich die andere Hälfte fort, dort passiert
    nichts Besonderes, und unnötig schmale Streifen kosten nur Kondition.
    """
    if innen < 1e-6:
        t = np.linspace(0.0, np.pi / 2.0, panels + 1)
        return aussen * np.sin(t)
    t = np.linspace(0.0, np.pi, panels + 1)
    return innen + (aussen - innen) * (1.0 - np.cos(t)) / 2.0


def streifen_aus_stapel(stapel, panels_je_seite: int = 20) -> list[Streifen]:
    """Macht aus dem Schnittstapel Rechenstreifen für beide Fahrzeugseiten.

    Der Stapel beschreibt nur die rechte Hälfte. Für die Traglinienrechnung
    muss der GANZE Flügel stehen: Der Abwind an der Wurzel stammt zum großen
    Teil von der anderen Seite. Wer nur eine Hälfte rechnet, bekommt dort
    einen deutlich zu großen wirksamen Anstellwinkel.
    """
    y_roh = np.array([s.y for s in stapel], dtype=float)
    innen, aussen = float(np.abs(y_roh).min()), float(np.abs(y_roh).max())
    if aussen - innen < 1e-6:
        raise ValueError("Der Flügel hat keine Spannweite.")

    ordnung = np.argsort(np.abs(y_roh))
    y_sortiert = np.abs(y_roh)[ordnung]
    sehnen = np.array([s.sehne for s in stapel])[ordnung]
    winkel = np.array([s.anstellwinkel for s in stapel])[ordnung]
    viertel = np.array([_viertelpunkt(s) for s in stapel])[ordnung]

    def auf(werte):
        return lambda y: np.interp(np.abs(y), y_sortiert, werte)

    f_sehne, f_winkel = auf(sehnen), auf(winkel)
    f_x, f_z = auf(viertel[:, 0]), auf(viertel[:, 2])

    halb = _kantenverteilung(innen, aussen, panels_je_seite)
    if innen < 1e-6:
        kanten = np.concatenate([-halb[::-1][:-1], halb])
    else:
        kanten = np.concatenate([-halb[::-1], halb])

    streifen = []
    for links, rechts in zip(kanten[:-1], kanten[1:]):
        mitte = 0.5 * (links + rechts)
        if innen > 1e-6 and abs(mitte) < innen:
            continue                     # Schlitz in der Mitte: kein Flügel
        streifen.append(Streifen(
            y=float(mitte), breite=float(rechts - links),
            sehne=float(f_sehne(mitte)), winkel=float(f_winkel(mitte)),
            hoehe=float(f_z(mitte)), x_viertel=float(f_x(mitte))))
    return streifen


# ----------------------------------------------------------------- Rechnung

def rechne(stapel, profil=None, geschwindigkeit: float = 15.0,
           panels_je_seite: int = 20, mit_boden: bool = True,
           polaren: list[Polare] | Polare | None = None,
           schritte_max: int = 100, daempfung: float = 0.5,
           genauigkeit: float = 1e-4) -> Fluegelkraefte:
    """Rechnet Abtrieb und Widerstand eines Flügels.

    `stapel`  Schnittliste aus geometrie.spannweite.schnitte()
    `profil`  das zugrunde liegende Profil, für die Polare
    `polaren` überschreibt die Polarenrechnung - eine Polare für alle
              Streifen oder eine je Streifen. Dient den Tests, die gegen die
              analytische Lösung der ebenen Platte prüfen und dafür einen
              linearen Beiwertverlauf brauchen.
    """
    streifen = streifen_aus_stapel(stapel, panels_je_seite)
    n = len(streifen)
    V = float(geschwindigkeit)

    # Alles in Meter - die Kräfte sollen in Newton herauskommen.
    y = np.array([s.y for s in streifen]) / 1000.0
    sehne = np.array([s.sehne for s in streifen]) / 1000.0
    breite = np.array([s.breite for s in streifen]) / 1000.0
    winkel = np.array([s.winkel for s in streifen])
    hoehe = np.array([s.hoehe for s in streifen]) / 1000.0
    x_viertel = np.array([s.x_viertel for s in streifen]) / 1000.0

    kanten_y = np.concatenate([y - breite / 2.0, [y[-1] + breite[-1] / 2.0]])
    kanten = np.column_stack([np.interp(kanten_y, y, x_viertel), kanten_y,
                              np.interp(kanten_y, y, hoehe)])

    # Kontrollpunkt auf der Dreiviertelsehne. Das ist der Kniff von
    # Weissinger: Genau dort trifft ein einzelner Hufeisenwirbel den
    # Auftriebsanstieg des ebenen Profils exakt.
    kontroll = np.column_stack([x_viertel + 0.5 * sehne, y, hoehe])

    A = einflussmatrix(kontroll, kanten, mit_boden=mit_boden)
    # Für den induzierten Winkel zählt nur die Wirbelschleppe, ausgewertet auf
    # der Traglinie selbst.
    traglinie = np.column_stack([x_viertel, y, hoehe])
    A_nachlauf = einflussmatrix(traglinie, kanten, mit_boden=mit_boden,
                                nur_nachlauf=True)

    pol = _polaren_zuordnen(polaren, profil, V, sehne, n)

    korrektur = np.zeros(n)
    kraft_vorher = 0.0
    schritt, konvergiert = 0, False
    zirkulation = np.zeros(n)
    alpha_ind = np.zeros(n)

    for schritt in range(1, schritte_max + 1):
        # Randbedingung: Die Strömung muss der Sehne folgen.
        #   V sin(a) + w cos(a) = 0   ->   w = -V tan(a)
        rechte_seite = -V * np.tan(np.radians(winkel + korrektur))
        zirkulation = np.linalg.solve(A, rechte_seite)

        alpha_ind = np.degrees(np.arctan2(A_nachlauf @ zirkulation, V))
        alpha_eff = winkel + alpha_ind

        cl_reibungsfrei = 2.0 * zirkulation / (V * sehne)
        cl_wirklich = np.array([pol[i].cl_bei(alpha_eff[i]) for i in range(n)])

        fehler = cl_wirklich - cl_reibungsfrei

        # Gemessen wird an der GESAMTKRAFT, nicht am groessten oertlichen
        # Fehler. Grund: Am aeussersten Streifen laeuft der induzierte Winkel
        # in der Traglinientheorie gegen unendlich. Er landet dort ausserhalb
        # des gerechneten Polarenbereichs, wird auf den Randwert geklemmt und
        # kann den reibungsfreien Beiwert nie treffen - der oertliche Fehler
        # bleibt dort stehen, egal wie lange man iteriert. Der Streifen ist
        # aber hauchduenn. Die Kraft, auf die es ankommt, konvergiert sauber.
        kraft = float(np.sum(cl_wirklich * sehne * breite))
        if schritt > 1 and abs(kraft - kraft_vorher) <= genauigkeit * max(abs(kraft), 1e-9):
            konvergiert = True
            break
        kraft_vorher = kraft

        korrektur = korrektur + daempfung * fehler / CL_ALPHA_GRAD

    alpha_eff = winkel + alpha_ind
    cl = np.array([pol[i].cl_bei(alpha_eff[i]) for i in range(n)])
    cd = np.array([pol[i].cd_bei(alpha_eff[i]) for i in range(n)])
    vertrauen = np.array([pol[i].vertrauen_bei(alpha_eff[i]) for i in range(n)])

    staudruck = 0.5 * DICHTE * V * V
    flaeche_i = sehne * breite
    flaeche = float(flaeche_i.sum())

    auftrieb_i = staudruck * cl * flaeche_i
    auftrieb = float(auftrieb_i.sum())

    # Induzierter Widerstand nach Kutta-Joukowski: Der Auftrieb steht
    # senkrecht auf der ÖRTLICHEN Anströmung, die durch den Abwind gekippt
    # ist. Seine Komponente in Strömungsrichtung ist der induzierte
    # Widerstand.
    w_induziert = A_nachlauf @ zirkulation
    d_induziert = float(-DICHTE * np.sum(zirkulation * w_induziert * breite))
    d_profil = float(staudruck * np.sum(cd * flaeche_i))

    abgerissen = 0.0
    for i in range(n):
        grenze = pol[i].abriss_winkel
        if (grenze < 0 and alpha_eff[i] < grenze) or (grenze > 0 and alpha_eff[i] > grenze):
            abgerissen += flaeche_i[i]

    return Fluegelkraefte(
        abtrieb=-auftrieb,
        widerstand=abs(d_induziert) + d_profil,
        widerstand_induziert=abs(d_induziert), widerstand_profil=d_profil,
        flaeche=flaeche, geschwindigkeit=V,
        cl=float(auftrieb / (staudruck * flaeche)) if flaeche > 0 else 0.0,
        cd=float((abs(d_induziert) + d_profil) / (staudruck * flaeche))
        if flaeche > 0 else 0.0,
        streifen=streifen, cl_lokal=cl, alpha_induziert=alpha_ind,
        alpha_wirksam=alpha_eff, auftrieb_lokal=auftrieb_i,
        vertrauen=float(np.sum(vertrauen * flaeche_i) / flaeche),
        abgerissen=float(abgerissen / flaeche) if flaeche > 0 else 0.0,
        schritte=schritt, konvergiert=konvergiert)


def _polaren_zuordnen(polaren, profil, geschwindigkeit, sehnen_m, n):
    """Eine Polare je Streifen, nach Reynoldsband gruppiert.

    Eine eigene Polare je Streifen wäre eine je Reynoldszahl. Da sich die
    Sehne über die Spannweite ändert, wird auf drei Bänder gerundet: Der
    Unterschied zwischen Re 240 000 und 250 000 liegt weit unter der
    Unsicherheit des Verfahrens, und drei Polaren statt vierzig sparen Zeit.
    """
    if isinstance(polaren, Polare):
        return [polaren] * n
    if polaren is not None:
        if len(polaren) != n:
            raise ValueError(f"{len(polaren)} Polaren fuer {n} Streifen.")
        return list(polaren)
    if profil is None:
        raise ValueError("Ohne Profil oder Polare laesst sich nicht rechnen.")

    re = np.array([reynolds(geschwindigkeit, c * 1000.0) for c in sehnen_m])
    if re.max() / max(re.min(), 1.0) < 1.15:
        return [polare(profil, float(re.mean()))] * n

    grenzen = np.exp(np.linspace(np.log(re.min()), np.log(re.max()), 4))
    band = np.clip(np.digitize(re, grenzen[1:-1]), 0, 2)
    vertreter = {b: polare(profil, float(np.exp(np.mean(np.log(re[band == b])))))
                 for b in np.unique(band)}
    return [vertreter[b] for b in band]


def bodenkennlinie(stapel, profil, hoehen_mm, geschwindigkeit: float = 15.0,
                   **kwargs) -> list[tuple[float, Fluegelkraefte]]:
    """Abtrieb über dem Bodenabstand.

    Eigene Funktion, weil der Frontflügel sich im Fahrbetrieb ständig auf und
    ab bewegt - Einfedern, Nicken beim Bremsen. Ein Abtriebswert bei EINER
    Höhe sagt nichts darüber, wie sich die Aerobalance über eine Runde
    verhält. Genau dieser Punktentwurf ist in der Literatur als Fehler
    beschrieben.
    """
    from dataclasses import replace

    bezug = _wurzelhoehe(stapel)
    ergebnisse = []
    for h in hoehen_mm:
        versatz = np.array([0.0, 0.0, float(h) - bezug])
        versetzt = [replace(s, punkte=s.punkte + versatz) for s in stapel]
        ergebnisse.append((float(h),
                           rechne(versetzt, profil, geschwindigkeit, **kwargs)))
    return ergebnisse


def _wurzelhoehe(stapel) -> float:
    """Höhe der Viertelsehne am innersten Schnitt - Bezug für die Kennlinie."""
    innen = min(stapel, key=lambda s: abs(s.y))
    return float(_viertelpunkt(innen)[2])
