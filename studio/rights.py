"""Import des sources et enregistrement des justificatifs de licence.

Chaque source reçoit un identifiant (src1, src2, ...) et un dossier droits/<id>/ contenant :
  licence.json   : type de licence, titulaire, auteur, URL d'origine, autorisations, attribution
  preuves/       : copies des justificatifs (contrat, courriel, capture de la page de licence, facture...)
Les empreintes SHA-256 de la vidéo et des preuves sont enregistrées : toute modification
ultérieure invalide la validation humaine.
"""
import shutil
from pathlib import Path

from . import config
from .core import StudioError, now, probe, save_json, sha256_file, slug

VIDEO_EXT = {'.mp4', '.mov', '.mkv', '.webm', '.m4v', '.avi', '.mts'}


def normaliser_type(t):
    t = (t or '').strip().lower().replace(' ', '-').replace('_', '-')
    alias = {'own': 'proprietaire', 'propre': 'proprietaire', 'moi': 'proprietaire', 'licensed': 'licence',
             'autorisation': 'licence', 'public-domain': 'domaine-public', 'pd': 'domaine-public'}
    return alias.get(t, t)


def verifier_licence(rec):
    """Retourne (bloquants, avertissements) pour un enregistrement de licence."""
    bloq, avert = [], []
    t = rec['type']
    if t in config.LICENCES_REFUSEES:
        bloq.append(f'licence {t} : la modification (ND) est interdite, la source ne peut pas être montée')
    if t in config.LICENCES_NC and not rec.get('non_commercial_assume'):
        bloq.append(f'licence {t} : usage non commercial seulement. Une publication monétisée ou '
                    'promotionnelle est exclue (relancez avec --non-commercial-assume si vous ne monétisez pas)')
    if t not in config.LICENCES and t not in config.LICENCES_NC and t not in config.LICENCES_REFUSEES:
        bloq.append(f'type de licence inconnu : {t} (choix : {", ".join(config.LICENCES)})')
    if not rec.get('titulaire'):
        bloq.append('titulaire des droits non renseigné (--titulaire)')
    if not rec.get('preuves') and not rec.get('declaration'):
        bloq.append('aucun justificatif (--preuve fichier) ni déclaration (--declaration "...")')
    if t == 'licence':
        if not rec.get('preuves'):
            bloq.append('une licence accordée par un tiers exige un justificatif écrit (--preuve)')
        if rec.get('autorise_modification') is not True:
            bloq.append('la licence doit autoriser la modification / le montage (--modif-autorisee)')
        if rec.get('autorise_commercial') is not True:
            avert.append('usage commercial non confirmé (--commercial-autorise) : pas de monétisation')
        if rec.get('expiration'):
            avert.append(f"licence valable jusqu'au {rec['expiration']} : vérifier avant publication")
    if rec.get('attribution_requise') and not rec.get('attribution'):
        bloq.append('cette licence exige une attribution : fournissez --attribution "Auteur, titre, licence, lien"')
    if t in ('cc-by', 'cc-by-sa', 'cc-by-nc', 'cc-by-nc-sa') and not rec.get('url_origine'):
        avert.append("URL d'origine conseillée pour une licence Creative Commons (--url)")
    if t == 'cc-by-sa' or t == 'cc-by-nc-sa':
        avert.append('BY-SA : la vidéo produite devra être partagée sous la même licence (à mentionner)')
    plat = rec.get('plateformes')
    if plat and plat != ['toutes']:
        manquantes = [p for p in config.PLATEFORMES if p not in plat]
        if manquantes:
            avert.append('plateformes non couvertes par la licence : ' + ', '.join(manquantes))
    return bloq, avert


def importer_source(prod, video, type_licence, titulaire, auteur=None, url=None, preuves=(), declaration=None,
                    attribution=None, modif=None, commercial=None, plateformes=None, expiration=None,
                    notes=None, copier=False, non_commercial_assume=False):
    video = Path(video).expanduser().resolve()
    if not video.exists():
        raise StudioError(f'fichier introuvable : {video}')
    if video.suffix.lower() not in VIDEO_EXT:
        raise StudioError(f'extension non prise en charge : {video.suffix} ({", ".join(sorted(VIDEO_EXT))})')
    info = probe(video)
    if not info['video'] or not info['audio']:
        raise StudioError('la source doit contenir une piste vidéo ET une piste audio')

    t = normaliser_type(type_licence)
    base = config.LICENCES.get(t) or ({'libelle': config.LICENCES_NC[t], 'modif': True, 'commercial': False,
                                       'attribution': True} if t in config.LICENCES_NC else
                                      {'libelle': t, 'modif': False, 'commercial': False, 'attribution': True})
    sid = f"src{len(prod.state['sources']) + 1}"
    ddir = prod.path('droits', sid)
    (ddir / 'preuves').mkdir(parents=True, exist_ok=True)

    proofs = []
    for p in preuves or ():
        p = Path(p).expanduser().resolve()
        if not p.is_file():
            raise StudioError(f'justificatif introuvable : {p}')
        dst = ddir / 'preuves' / f'{slug(p.stem, 60)}{p.suffix.lower()}'
        shutil.copy2(p, dst)
        proofs.append({'fichier': str(dst.relative_to(prod.dir)).replace('\\', '/'), 'origine': p.name,
                       'sha256': sha256_file(dst), 'ajoute_le': now()})

    if copier:
        dst = prod.path('sources', f'{sid}{video.suffix.lower()}')
        print(f'-> copie de la source dans la production ({info["duree"]:.0f} s) ...')
        shutil.copy2(video, dst)
        video_path = dst
    else:
        video_path = video
    print('-> calcul de l\'empreinte SHA-256 de la source ...')
    rec = {
        'id': sid, 'type': t, 'libelle': base['libelle'], 'titulaire': titulaire, 'auteur': auteur or titulaire,
        'url_origine': url, 'preuves': proofs, 'declaration': declaration,
        'autorise_modification': base['modif'] if modif is None else modif,
        'autorise_commercial': base['commercial'] if commercial is None else commercial,
        'attribution_requise': bool(base['attribution']), 'attribution': attribution,
        'plateformes': plateformes or ['toutes'], 'expiration': expiration, 'notes': notes,
        'non_commercial_assume': non_commercial_assume,
        'enregistre_le': now(), 'enregistre_par': prod.state.get('auteur') or None,
    }
    if declaration:
        rec['declaration_horodatee'] = {'texte': declaration, 'le': now()}
    bloq, avert = verifier_licence(rec)
    if bloq:
        shutil.rmtree(ddir, ignore_errors=True)
        if copier:
            Path(video_path).unlink(missing_ok=True)
        raise StudioError('source refusée :\n  - ' + '\n  - '.join(bloq))
    save_json(ddir / 'licence.json', rec)
    src = {'id': sid, 'fichier': str(video_path), 'nom': video.name, 'copie': bool(copier),
           'sha256': sha256_file(video_path), 'taille': Path(video_path).stat().st_size,
           'duree': info['duree'], 'largeur': info.get('largeur'), 'hauteur': info.get('hauteur'),
           'fps': info.get('fps'), 'licence': f'droits/{sid}/licence.json',
           'licence_sha256': sha256_file(ddir / 'licence.json'), 'importe_le': now()}
    prod.state['sources'][sid] = src
    prod.set_statut('sources')
    prod.log('source_importee', source=sid, fichier=video.name, sha256=src['sha256'], licence=t,
             titulaire=titulaire, preuves=[p['sha256'] for p in proofs], avertissements=avert)
    return src, avert


def licence(prod, sid):
    from .core import load_json
    return load_json(prod.path('droits', sid, 'licence.json'))


def controle_integrite(prod, complet=True):
    """Vérifie que les sources et preuves n'ont pas changé depuis l'import. Retourne la liste des problèmes."""
    pb = []
    for sid, src in prod.state['sources'].items():
        p = Path(src['fichier'])
        if not p.exists():
            pb.append(f'{sid} : fichier source introuvable ({p})')
            continue
        if p.stat().st_size != src['taille'] or (complet and sha256_file(p) != src['sha256']):
            pb.append(f'{sid} : la vidéo source a été modifiée depuis son import')
        lic = prod.path(src['licence'])
        if not lic.exists() or sha256_file(lic) != src['licence_sha256']:
            pb.append(f'{sid} : licence.json modifié ou manquant (réimportez la source)')
            continue
        rec = licence(prod, sid)
        for pr in rec.get('preuves', []):
            f = prod.path(pr['fichier'])
            if not f.exists() or sha256_file(f) != pr['sha256']:
                pb.append(f"{sid} : justificatif modifié ou manquant ({pr['fichier']})")
    return pb


def credits(prod):
    """Lignes d'attribution à publier (description / légende)."""
    out = []
    for sid in prod.state['sources']:
        rec = licence(prod, sid)
        if rec.get('attribution'):
            out.append(rec['attribution'])
        elif rec['type'] == 'licence':
            out.append(f"Extraits utilisés avec l'autorisation de {rec['titulaire']}")
    return out
