"""Fichier CSV de suivi des résultats (une ligne par vidéo et par plateforme).

Séparateur « ; » et encodage UTF-8 avec BOM : s'ouvre directement dans Excel en français.
"""
import csv

from . import config
from .core import StudioError, now

NUM = {'vues', 'likes', 'commentaires', 'partages', 'enregistrements', 'duree_moyenne_visionnage_s',
       'taux_completion_pct', 'abonnes_gagnes'}


def lire():
    if not config.SUIVI_CSV.exists():
        return []
    with open(config.SUIVI_CSV, encoding='utf-8-sig', newline='') as f:
        return list(csv.DictReader(f, delimiter=config.CSV_SEPARATEUR))


def ecrire(rows):
    config.REGISTRE.mkdir(parents=True, exist_ok=True)
    tmp = config.SUIVI_CSV.with_suffix('.tmp')
    with open(tmp, 'w', encoding='utf-8-sig', newline='') as f:
        w = csv.DictWriter(f, fieldnames=config.CSV_COLONNES, delimiter=config.CSV_SEPARATEUR, extrasaction='ignore')
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, '') for k in config.CSV_COLONNES})
    tmp.replace(config.SUIVI_CSV)


def ajouter_export(pid, titre, fichier, sha, duree, plateformes=config.PLATEFORMES):
    rows = lire()
    for p in plateformes:
        exist = next((r for r in rows if r['production_id'] == pid and r['plateforme'] == p), None)
        base = {'production_id': pid, 'titre': titre, 'fichier': fichier, 'sha256': sha, 'duree_s': f'{duree:.1f}',
                'date_export': now(), 'plateforme': p}
        if exist:   # ré-export : on met à jour le fichier mais on garde les résultats saisis
            exist.update(base)
        else:
            rows.append({**base, 'statut': 'à publier'})
    ecrire(rows)


def maj(pid, plateforme, **champs):
    if plateforme not in config.PLATEFORMES:
        raise StudioError(f"plateforme inconnue : {plateforme} ({', '.join(config.PLATEFORMES)})")
    rows = lire()
    row = next((r for r in rows if r['production_id'] == pid and r['plateforme'] == plateforme), None)
    if row is None:
        raise StudioError(f'{pid} / {plateforme} absent du suivi (la vidéo a-t-elle été exportée ?)')
    for k, v in champs.items():
        if v is None:
            continue
        if k not in config.CSV_COLONNES:
            raise StudioError(f'colonne inconnue : {k}')
        if k in NUM:
            try:
                float(str(v).replace(',', '.'))
            except ValueError:
                raise StudioError(f'{k} doit être un nombre (reçu {v!r})')
        row[k] = str(v)
    if champs.get('url') and row.get('statut') == 'à publier':
        row['statut'] = 'publié'
    if any(champs.get(k) is not None for k in NUM):
        row['date_releve'] = now()
    ecrire(rows)
    return row
