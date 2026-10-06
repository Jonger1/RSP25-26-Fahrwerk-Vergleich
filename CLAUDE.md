# Hinweise für Claude

## Reglement

- Es gilt **ausschließlich FS Rules 2027 v1.0**. Das Original-PDF liegt im Repo unter
  `Aero/FS_Rules_2027_v1.0.pdf`. Bei jeder Frage zu Regeln, Grenzwerten oder
  Regelnummern dort nachlesen (Text extrahieren, z. B. mit `pypdf`) und nicht aus dem
  Gedächtnis antworten.
- Die maschinenlesbaren Werte stehen in `Aero/aerostudio/regeln/rules_2027.yaml`, mit
  Wortlaut und Seitenangabe. Der Prüfer (`Aero/aerostudio/regeln/pruefung.py`) liest
  nur diese Datei. Welcher Stand gilt, legt `regeln.AKTUELL` fest.
- FS Rules 2026 v1.1 und der Academy-Entwurf 2027 sind entfernt (06.10.2026). Nicht
  wieder einführen, nicht dagegen prüfen und nicht mit ihnen argumentieren.
- Kommt ein neuer Regelstand: das PDF ins Repo legen, eine neue YAML aus dem
  Originaltext anlegen und `AKTUELL` umstellen. Den alten Stand entfernen, wenn das
  Team es so will.

## Projekt

- Das Werkzeug Aero Studio liegt in `Aero/`. Tests laufen mit
  `cd Aero && python -m pytest -q`. Den Plan beschreibt `Aero/MEILENSTEINE.md`.
