"""
Web-Modus: Spec herunter- und hochladen, Exporte als ZIP, Schreiben in eine
eigene Ablage, kein Creo.

Der Modus wird beim Import festgelegt (Umgebungsvariable AEROSTUDIO_WEB). Die
Tests dafuer laufen deshalb in einem eigenen Python-Prozess.
"""

import base64
import io
import json
import os
import subprocess
import sys
import zipfile
from pathlib import Path

import yaml

from aerostudio.spec.projekt import AeroSpec
from aerostudio.ui import app as UI

AERO = Path(__file__).resolve().parents[1]
HECK = UI.PROJEKT / "specs/beispiele/heckfluegel.yaml"


def test_lokal_ist_die_ablage_der_programmordner():
    assert not UI.WEB
    assert UI.ablage() == UI.PROJEKT


def test_herunterladen_und_wieder_hochladen_gibt_denselben_entwurf():
    spec = AeroSpec.laden(HECK)
    datei = UI._spec_herunterladen(1, spec.model_dump(mode="json"))
    assert datei["filename"].endswith(f"{spec.hash()}.yaml")
    assert AeroSpec.model_validate(yaml.safe_load(datei["content"])).hash() == spec.hash()

    inhalt = "data:application/x-yaml;base64," + base64.b64encode(
        datei["content"].encode("utf-8")).decode("ascii")
    *felder, basis, meldung = UI._hochladen(inhalt, datei["filename"])
    assert UI._baue_spec(*felder, basis).hash() == spec.hash()
    assert "Hochgeladen" in str(meldung.to_plotly_json())


def test_kaputter_upload_gibt_eine_fehlerkarte():
    inhalt = "data:application/x-yaml;base64," + base64.b64encode(b"meta: 5").decode()
    *felder, meldung = UI._hochladen(inhalt, "x.yaml")
    from dash import no_update
    assert all(f is no_update for f in felder)
    assert meldung is not no_update


def test_exporte_als_zip(tmp_path, monkeypatch):
    monkeypatch.setattr(UI, "PROJEKT", tmp_path)
    assert UI._exporte_als_zip(1)[1] == "Noch keine Exporte vorhanden."
    (tmp_path / "export" / "dxf").mkdir(parents=True)
    (tmp_path / "export" / "a.ibl").write_text("ibl")
    (tmp_path / "export" / "dxf" / "b.dxf").write_text("dxf")
    daten, status = UI._exporte_als_zip(1)
    z = zipfile.ZipFile(io.BytesIO(base64.b64decode(daten["content"])))
    assert sorted(z.namelist()) == ["a.ibl", "dxf/b.dxf"]
    assert "2 Dateien" in status


def _im_webmodus(code: str, ablage: Path) -> dict:
    umgebung = dict(os.environ, AEROSTUDIO_WEB="1", AEROSTUDIO_ABLAGE=str(ablage),
                    PYTHONPATH=str(AERO))
    aus = subprocess.run([sys.executable, "-c", code], cwd=AERO, env=umgebung,
                         capture_output=True, text=True, timeout=300)
    assert aus.returncode == 0, aus.stderr[-2000:]
    return json.loads(aus.stdout.strip().splitlines()[-1])


def test_webmodus_schreibt_in_die_ablage_und_versteckt_creo(tmp_path):
    code = r'''
import json
from aerostudio.ui import app as UI
from aerostudio.spec.projekt import AeroSpec
baum = UI.layout()
layout = json.dumps(baum.to_plotly_json(), default=str)
def suche(k, kennung):
    if getattr(k, "id", None) == kennung:
        return k
    kinder = getattr(k, "children", None)
    for c in (kinder if isinstance(kinder, (list, tuple)) else [kinder]):
        if c is not None and not isinstance(c, (str, int, float)):
            t = suche(c, kennung)
            if t is not None:
                return t
creo = suche(baum, "btn-creo")
spec = AeroSpec.laden(UI._finde("specs/beispiele/heckfluegel.yaml"))
UI.AeroSpec.model_validate(spec.model_dump(mode="json")).speichern(UI.SPEC_VORGABE)
import wsgi
print(json.dumps({
    "web": UI.WEB, "ablage": str(UI.ablage()), "vorgabe": str(UI.SPEC_VORGABE),
    "banner": "Web-Version" in layout,
    "creo_versteckt": (getattr(creo, "style", None) or {}).get("display") == "none",
    "beispiele": [o["value"] for o in UI._alle_specs()],
    "wsgi": type(wsgi.server).__name__,
}))
'''
    r = _im_webmodus(code, tmp_path)
    assert r["web"] is True
    assert r["ablage"] == str(tmp_path)
    assert r["vorgabe"].startswith(str(tmp_path))
    assert (tmp_path / "specs" / "aktuell.yaml").is_file()
    assert r["banner"] and r["creo_versteckt"]
    # Beispiele aus dem Programmordner UND das gespeicherte aus der Ablage.
    assert "specs/beispiele/heckfluegel.yaml" in r["beispiele"]
    assert r["wsgi"] == "Flask"
    # Der Programmordner bleibt unberuehrt.
    assert not (AERO / "specs" / "aktuell.yaml").exists() or \
        (AERO / "specs" / "aktuell.yaml").stat().st_mtime < (tmp_path / "specs" / "aktuell.yaml").stat().st_mtime
