"""Validation humaine OBLIGATOIRE avant l'export final.

Quatre volets : sources, faits, montage, droits. Chaque point exige une réponse explicite
(o/n) ; chaque affirmation factuelle exige la référence qui la vérifie. La validation est liée à
l'empreinte de l'aperçu visionné : toute modification ultérieure (montage, narration, source,
licence, justificatif) l'annule et l'export est refusé.

Cette commande doit être lancée par un humain dans un vrai terminal. Elle refuse une entrée
non interactive (sauf STUDIO_TESTS=1, réservé aux tests automatisés).
"""
import os
import sys

from .core import StudioError, now, save_json, sha256_file, load_json
from .rights import licence
from .timeline import empreinte, verifier


def _input(prompt):
    try:
        return input(prompt)
    except EOFError:
        raise StudioError('validation interrompue (fin de saisie) : rien n\'a été enregistré')


def _ask(q, aide=None):
    while True:
        r = _input(f'  {q}\n    {"(" + aide + ") " if aide else ""}[o/n] > ').strip().lower()
        if r in ('o', 'oui', 'y', 'yes'):
            return True
        if r in ('n', 'non', 'no'):
            return False
        print('    répondez o ou n')


def _texte(q, obligatoire=True):
    while True:
        r = _input(f'    {q} > ').strip()
        if r or not obligatoire:
            return r
        print('    réponse obligatoire')


def questions(prod, res):
    srcs = sorted({x['source'] for x in res['timeline'] if x['type'] == 'extrait'} |
                  {x['visuel']['source'] for x in res['timeline'] if x['type'] == 'narration'})
    q = {'sources': [], 'montage': [], 'droits': []}
    for sid in srcs:
        rec = licence(prod, sid)
        preuves = ', '.join(p['fichier'] for p in rec.get('preuves', [])) or 'déclaration : ' + str(rec.get('declaration'))
        q['sources'].append((f'src_{sid}', f"{sid} « {prod.state['sources'][sid]['nom']} » : licence {rec['libelle']}, "
                                           f"titulaire {rec['titulaire']}. J'ai relu le justificatif ({preuves}) et il "
                                           'couvre bien CE fichier, ce montage et ces plateformes.'))
    q['sources'].append(('src_originaux', "Les extraits sont tirés des fichiers originaux (pas d'une copie re-téléchargée "
                                          "depuis une plateforme tierce)."))
    q['montage'] += [
        ('mt_visionne', f"J'ai visionné l'aperçu EN ENTIER ({prod.path('apercu', 'apercu.mp4')})."),
        ('mt_sens', "Aucun extrait n'est sorti de son contexte ni coupé de façon à changer le sens des propos."),
        ('mt_sous_titres', 'Les sous-titres sont fidèles (noms propres, chiffres, orthographe) et lisibles.'),
        ('mt_cadrage', 'Le recadrage 9:16 garde les visages et textes importants dans le cadre.'),
        ('mt_original', "Le commentaire est original, écrit ou relu par moi, et apporte une analyse (pas une paraphrase)."),
        ('mt_personnes', "Aucune personne n'est présentée de façon diffamatoire ou portant atteinte à sa vie privée."),
    ]
    synth = any(v.get('synthetique') for v in prod.state['narration'].values())
    q['droits'] += [
        ('dr_narration', 'La narration est ma voix (ou une voix dont je détiens les droits).' if not synth else
         "La narration contient une VOIX DE SYNTHÈSE : je la déclarerai comme contenu généré/modifié (étiquette IA) "
         'sur chaque plateforme, ou je la remplace avant export.'),
        ('dr_musique', "Aucune musique, image, logo ou œuvre de tiers non couverts par une licence n'apparaît."),
        ('dr_personnes', 'Les personnes identifiables ont consenti à être filmées/diffusées (ou la licence le couvre).'),
        ('dr_credits', 'Les crédits / attributions exigés par les licences figureront dans la publication.'),
        ('dr_plateformes', 'La publication respecte les règles de chaque plateforme (contenu original, transparence).'),
    ]
    return q


def valider(prod, relecteur=None):
    if not sys.stdin.isatty() and os.environ.get('STUDIO_TESTS') != '1':
        raise StudioError('la validation doit être faite par un humain dans un terminal interactif '
                          f'(ouvrez un terminal et lancez : python run.py prod valider {prod.id})')
    ap = load_json(prod.path('apercu', 'apercu.json'))
    if not ap or not prod.path('apercu', 'apercu.mp4').exists():
        raise StudioError(f'aucun aperçu : lancez  prod apercu {prod.id}  puis visionnez-le')
    res = verifier(prod, exiger_narration=True, complet=True)
    if res['bloquants']:
        raise StudioError('corrigez d\'abord :\n  - ' + '\n  - '.join(res['bloquants']))
    fp = empreinte(prod, res)
    if ap['empreinte'] != fp:
        raise StudioError('le montage a changé depuis l\'aperçu : relancez  prod apercu ' + prod.id)
    if sha256_file(prod.path('apercu', 'apercu.mp4')) != ap['sha256']:
        raise StudioError('le fichier d\'aperçu a été modifié : relancez  prod apercu ' + prod.id)

    print(f"\n=== VALIDATION HUMAINE : {prod.id} ===")
    print(f"Durée {res['duree_totale']:.1f} s, commentaire original {res['part_narration']:.0%}.")
    if res['avertissements']:
        print('Avertissements à considérer :')
        for a in res['avertissements']:
            print('  ! ' + a)
    relecteur = relecteur or _texte('Votre nom (relecteur responsable)')
    reponses, refus = {}, []
    qs = questions(prod, res)
    for volet, titre in (('sources', 'SOURCES'), ('faits', 'FAITS'), ('montage', 'MONTAGE'), ('droits', 'DROITS')):
        print(f'\n--- {titre} ---')
        if volet == 'faits':
            if not res['faits']:
                print('  (aucune affirmation factuelle détectée automatiquement)')
            for f in res['faits']:
                ok = _ask(f"[{f['segment']} / {f['origine']}] « {f['affirmation']} »  est-ce exact ?")
                ref = _texte('Référence qui le vérifie (lien, document, « opinion personnelle »...)') if ok else ''
                reponses[f"fait_{f['id']}"] = {'question': f['affirmation'], 'ok': ok, 'reference': ref}
                if not ok:
                    refus.append(f"fait non vérifié : {f['affirmation']}")
            ok = _ask("Je confirme qu'aucune autre affirmation factuelle non vérifiée ne figure dans la vidéo.")
            reponses['fait_autres'] = {'question': 'aucune autre affirmation non vérifiée', 'ok': ok}
            if not ok:
                refus.append('autres affirmations non vérifiées')
            continue
        for key, question in qs[volet]:
            ok = _ask(question)
            reponses[key] = {'question': question, 'ok': ok}
            if not ok:
                refus.append(question)
    note = _texte('Remarque libre (facultatif)', obligatoire=False)
    approuve = not refus
    rec = {'production': prod.id, 'relecteur': relecteur, 'le': now(), 'approuve': approuve,
           'empreinte': fp, 'apercu_sha256': ap['sha256'], 'duree': res['duree_totale'],
           'part_narration': res['part_narration'], 'avertissements': res['avertissements'],
           'reponses': reponses, 'refus': refus, 'remarque': note}
    n = len(list(prod.path().glob('validation*.json')))
    save_json(prod.path(f'validation_{n + 1:02d}.json'), rec)
    save_json(prod.path('validation.json'), rec)
    if approuve:
        prod.set_statut('valide')
    prod.log('validation', approuve=approuve, relecteur=relecteur, empreinte=fp, refus=refus)
    print('\nVALIDÉ : l\'export final est autorisé.' if approuve else
          '\nNON VALIDÉ :\n  - ' + '\n  - '.join(refus) + '\nCorrigez puis relancez aperçu + validation.')
    return rec


def validation_courante(prod, fp):
    """Retourne la validation si elle est approuvée ET correspond à l'état actuel, sinon lève une erreur."""
    v = load_json(prod.path('validation.json'))
    if not v:
        raise StudioError(f'export refusé : aucune validation humaine. Lancez  prod valider {prod.id}')
    if not v.get('approuve'):
        raise StudioError('export refusé : la dernière validation n\'est pas approuvée')
    if v.get('empreinte') != fp:
        raise StudioError('export refusé : le montage, une source, une licence ou une narration a changé depuis '
                          f'la validation du {v["le"]}. Relancez  prod apercu  puis  prod valider')
    return v
