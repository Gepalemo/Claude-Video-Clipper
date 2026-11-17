"""Pipeline de production de vidéos verticales originales (65-100 s, 1080x1920).

    python run.py prod nouveau "Nom de la production"
    python run.py prod source   <prod> <video> --licence proprietaire --titulaire "Moi" --preuve contrat.pdf
    python run.py prod transcrire <prod> [--modele small] [--langue fr]
    python run.py prod passages <prod> [--n 8] [--mots-cles "a,b"]
    python run.py prod script   <prod> --passages p2,p5,p7 [--titre "..."] [--ollama llama3.1]
      -> éditez montage.json (textes de narration, titre, accroche, hashtags)
    python run.py prod narration <prod> <bloc> <fichier_audio>      (votre voix, un fichier par bloc)
    python run.py prod verifier <prod>
    python run.py prod apercu   <prod>          aperçu filigrané « APERÇU — NON VALIDÉ »
    python run.py prod valider  <prod>          validation HUMAINE obligatoire (terminal interactif)
    python run.py prod exporter <prod>          export final sans filigrane + métadonnées + suivi CSV
    python run.py prod resultats <prod> --plateforme tiktok --url ... --vues 1200 ...
    python run.py prod statut   [<prod>]   |   prod journal [<prod>]   |   prod suivi

Aucune publication automatique : les fichiers et les textes sont prêts, vous publiez vous-même.
"""
import argparse
import sys

from . import config
from .core import Production, StudioError, lire_journal, load_json, now, save_json, sha256_file


def cmd_nouveau(a):
    p = Production.create(a.nom)
    if a.auteur:
        p.state['auteur'] = a.auteur
        p.save()
    p.log('production_creee', nom=a.nom)
    print(f'production créée : {p.id}\ndossier : {p.dir}\n'
          f'suite : python run.py prod source {p.id} <video> --licence ... --titulaire ... --preuve ...')


def cmd_source(a):
    from .rights import importer_source
    p = Production(a.prod)
    plats = [x.strip() for x in a.plateformes.split(',')] if a.plateformes else None
    src, avert = importer_source(p, a.video, a.licence, a.titulaire, auteur=a.auteur, url=a.url, preuves=a.preuve,
                                 declaration=a.declaration, attribution=a.attribution,
                                 modif=True if a.modif_autorisee else None,
                                 commercial=True if a.commercial_autorise else None, plateformes=plats,
                                 expiration=a.expiration, notes=a.notes, copier=a.copier,
                                 non_commercial_assume=a.non_commercial_assume)
    print(f"source {src['id']} enregistrée : {src['nom']} ({src['duree']:.0f} s, {src['largeur']}x{src['hauteur']})")
    print(f"  sha256 {src['sha256'][:16]}…  licence : {p.path(src['licence'])}")
    for w in avert:
        print('  ! ' + w)


def cmd_transcrire(a):
    from .transcribe import transcrire_sources
    p = Production(a.prod)
    if not p.state['sources']:
        raise StudioError('aucune source : ajoutez-en une avec  prod source')
    if a.langue:
        p.state['langue'] = a.langue
        p.save()
    transcrire_sources(p, a.modele, a.langue, a.device, a.refaire)
    print(f'transcriptions : {p.path("transcriptions")}\nsuite : python run.py prod passages {p.id}')


def cmd_passages(a):
    from .passages import suggerer
    p = Production(a.prod)
    cles = [x.strip() for x in a.mots_cles.split(',')] if a.mots_cles else []
    res = suggerer(p, a.n, a.min, a.max, cles)
    for c in res:
        print(f"{c['id']:4} {c['source']} {c['debut']:7.1f}-{c['fin']:7.1f} ({c['duree']:4.1f} s) score {c['score']:5.2f}"
              f"  « {c['texte'][:110]}{'…' if len(c['texte']) > 110 else ''} »")
    print(f"\ndétail : {p.path('passages.json')}\n"
          f'suite : python run.py prod script {p.id} --passages p1,p3   (2 à 4 extraits courts)')


def cmd_script(a):
    from .script import creer_montage
    from .timeline import resoudre, resume
    p = Production(a.prod)
    ids = [x.strip() for x in a.passages.split(',') if x.strip()]
    creer_montage(p, ids, a.titre, a.ollama, a.ecraser)
    res = resoudre(p)
    print(resume(res))
    print(f"\nmontage : {p.montage_path}\ntexte à lire : {p.path('script_narration.txt')}")
    print('Écrivez votre commentaire dans montage.json (remplacez chaque [À ÉCRIRE ...]), puis enregistrez-le.')


def cmd_narration(a):
    from . import narration
    p = Production(a.prod)
    if a.tts_test:
        print('-> voix de SYNTHÈSE pour test (à remplacer par votre voix avant publication)')
        narration.tts_test_tous(p)
    else:
        if not a.bloc or not a.fichier:
            raise StudioError('usage : prod narration <prod> <bloc> <fichier_audio>   (ou --tts-test)')
        rec = narration.ajouter(p, a.bloc, a.fichier, synthetique=a.synthetique)
        print(f"narration {rec['bloc']} : {rec['duree']:.1f} s  « {rec['transcription'][:100]} »")
    from .timeline import resoudre, resume
    print(resume(resoudre(p)))


def _afficher(res):
    from .timeline import resume
    print(resume(res))
    for b in res['bloquants']:
        print('  X ' + b)
    for w in res['avertissements']:
        print('  ! ' + w)
    if res['faits']:
        print(f"\n{len(res['faits'])} affirmation(s) à vérifier à la validation :")
        for f in res['faits']:
            print(f"  - [{f['segment']}] {f['affirmation'][:120]}")


def cmd_verifier(a):
    from .timeline import verifier
    p = Production(a.prod)
    res = verifier(p, exiger_narration=True, complet=a.complet)
    _afficher(res)
    print('\nOK : prêt pour l\'aperçu' if not res['bloquants'] else '\nÀ corriger avant l\'aperçu final.')
    return 0 if not res['bloquants'] else 2


def cmd_apercu(a):
    from .render import rendre
    from .timeline import empreinte, verifier
    p = Production(a.prod)
    res = verifier(p, exiger_narration=not a.structure)
    _afficher(res)
    if res['bloquants'] and not a.structure:
        raise StudioError('aperçu impossible tant que les points X ne sont pas corrigés '
                          '(ou --structure pour un aperçu de structure sans narration)')
    out = p.path('apercu', 'apercu.mp4')
    print(f'\n-> rendu de l\'aperçu ({res["duree_totale"]:.0f} s de vidéo) ...')
    info, secs = rendre(p, res, out, mode='apercu')
    rec = {'le': now(), 'empreinte': empreinte(p, res), 'sha256': sha256_file(out), 'duree': info['duree'],
           'structure_seulement': bool(a.structure), 'bloquants': res['bloquants']}
    save_json(p.path('apercu', 'apercu.json'), rec)
    if not res['bloquants']:
        p.set_statut('apercu')
    p.log('apercu', duree=info['duree'], sha256=rec['sha256'], empreinte=rec['empreinte'], calcul_s=secs)
    print(f'aperçu : {out}  ({info["duree"]:.1f} s, {info["largeur"]}x{info["hauteur"]}, rendu {secs:.0f} s)')
    print(f'Visionnez-le en entier, puis lancez vous-même :  python run.py prod valider {p.id}')


def cmd_valider(a):
    from .review import valider
    p = Production(a.prod)
    rec = valider(p, a.relecteur)
    return 0 if rec['approuve'] else 3


def cmd_exporter(a):
    from . import metadata, results
    from .render import controle_sortie, rendre
    from .review import validation_courante
    from .timeline import empreinte, verifier
    p = Production(a.prod)
    res = verifier(p, exiger_narration=True, complet=True)
    if res['bloquants']:
        raise StudioError('export refusé :\n  - ' + '\n  - '.join(res['bloquants']))
    fp = empreinte(p, res)
    v = validation_courante(p, fp)
    from .core import slug
    m = p.montage()
    out = p.path('export', f"{p.id}_{slug(m.get('titre') or p.state['nom'], 40)}_1080x1920.mp4")
    print(f"-> export final (validé par {v['relecteur']} le {v['le']}) ...")
    info, secs = rendre(p, res, out, mode='final')
    pb = controle_sortie(info, res['duree_totale'])
    if pb:
        out.rename(out.with_suffix('.REJETE.mp4'))
        raise StudioError('contrôle technique du fichier exporté en échec :\n  - ' + '\n  - '.join(pb))
    sha = sha256_file(out)
    meta = metadata.generer(p, res, out.name)
    rec = {'le': now(), 'fichier': out.name, 'sha256': sha, 'duree': info['duree'], 'validation': v['le'],
           'relecteur': v['relecteur'], 'empreinte': fp, 'controle': info}
    save_json(p.path('export', 'export.json'), rec)
    results.ajouter_export(p.id, m.get('titre') or p.state['nom'], out.name, sha, info['duree'])
    p.set_statut('exporte')
    p.log('export', fichier=out.name, sha256=sha, duree=info['duree'], relecteur=v['relecteur'], calcul_s=secs)
    print(f"export : {out}\n  {info['largeur']}x{info['hauteur']}, {info['duree']:.1f} s, {info['codec_video']}/"
          f"{info['codec_audio']}, sans filigrane, sha256 {sha[:16]}…")
    print(f"métadonnées : {p.path('export', 'metadonnees.md')}\nsuivi : {config.SUIVI_CSV}")
    for x in meta['a_faire_avant_publication']:
        print('  [ ] ' + x)


def cmd_resultats(a):
    from . import results
    champs = {k: getattr(a, k) for k in ('url', 'date_publication', 'vues', 'likes', 'commentaires', 'partages',
                                         'enregistrements', 'duree_moyenne_visionnage_s', 'taux_completion_pct',
                                         'abonnes_gagnes', 'statut', 'notes')}
    Production(a.prod)
    row = results.maj(a.prod, a.plateforme, **champs)
    Production(a.prod).log('resultats', plateforme=a.plateforme, **{k: v for k, v in champs.items() if v is not None})
    print('; '.join(f'{k}={row[k]}' for k in config.CSV_COLONNES if row.get(k)))


def cmd_suivi(a):
    from . import results
    rows = results.lire()
    if not rows:
        print(f'suivi vide ({config.SUIVI_CSV})')
    for r in rows:
        print(f"{r['production_id']:40} {r['plateforme']:16} {r['statut']:10} vues={r['vues'] or '-':>7} "
              f"likes={r['likes'] or '-':>5} {r['url']}")
    print(f'\nfichier : {config.SUIVI_CSV}')


def cmd_statut(a):
    if not a.prod:
        for d in sorted(config.OUTPUT.glob('*/production.json')):
            s = load_json(d)
            print(f"{s['id']:45} {s['statut']:10} sources={len(s['sources'])} narrations={len(s['narration'])}")
        return
    p = Production(a.prod)
    s = p.state
    print(f"{s['id']} : {s['statut']}  (créée le {s['cree_le']})")
    for sid, src in s['sources'].items():
        print(f"  {sid} {src['nom']} {src['duree']:.0f} s  licence {load_json(p.path(src['licence']))['type']}")
    for b, r in s['narration'].items():
        print(f"  narration {b}: {r['duree']:.1f} s{' (synthèse)' if r.get('synthetique') else ''}")
    v = load_json(p.path('validation.json'))
    if v:
        print(f"  validation : {'approuvée' if v['approuve'] else 'REFUSÉE'} par {v['relecteur']} le {v['le']}")
    e = load_json(p.path('export', 'export.json'))
    if e:
        print(f"  export : {e['fichier']} ({e['duree']:.1f} s) le {e['le']}")


def cmd_journal(a):
    for e in lire_journal(a.prod):
        det = {k: v for k, v in e.items() if k not in ('horodatage', 'utilisateur', 'production', 'action')}
        print(f"{e['horodatage']}  {e['production'] or '-':40} {e['action']:20} {det}")


def parser():
    ap = argparse.ArgumentParser(prog='run.py prod', description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sp = ap.add_subparsers(dest='cmd', required=True)
    s = sp.add_parser('nouveau', help='créer une production')
    s.add_argument('nom')
    s.add_argument('--auteur')
    s.set_defaults(f=cmd_nouveau)

    s = sp.add_parser('source', help='importer une source + justificatifs de licence')
    s.add_argument('prod')
    s.add_argument('video')
    s.add_argument('--licence', required=True, help=f"{', '.join(config.LICENCES)}, cc-by-nc, cc-by-nc-sa")
    s.add_argument('--titulaire', required=True, help='titulaire des droits')
    s.add_argument('--auteur')
    s.add_argument('--url', help="URL d'origine de l'œuvre / de la licence")
    s.add_argument('--preuve', action='append', default=[], help='justificatif (répétable) : contrat, courriel, capture...')
    s.add_argument('--declaration', help='attestation sur l\'honneur (contenu dont vous êtes l\'auteur)')
    s.add_argument('--attribution', help='texte de crédit exigé par la licence')
    s.add_argument('--modif-autorisee', action='store_true')
    s.add_argument('--commercial-autorise', action='store_true')
    s.add_argument('--non-commercial-assume', action='store_true')
    s.add_argument('--plateformes', help='plateformes couvertes, ex. tiktok,youtube_shorts (défaut : toutes)')
    s.add_argument('--expiration', help='date de fin de licence AAAA-MM-JJ')
    s.add_argument('--notes')
    s.add_argument('--copier', action='store_true', help='copier la vidéo dans la production')
    s.set_defaults(f=cmd_source)

    s = sp.add_parser('transcrire', help='transcrire les sources (Whisper local)')
    s.add_argument('prod')
    s.add_argument('--modele', default=None, help=f'tiny, base, small (défaut {config.WHISPER_MODELE}), medium')
    s.add_argument('--langue', default=None, help='fr, en... ou auto')
    s.add_argument('--device', default='cpu', help='cpu ou cuda')
    s.add_argument('--refaire', action='store_true')
    s.set_defaults(f=cmd_transcrire)

    s = sp.add_parser('passages', help='suggérer les passages utiles')
    s.add_argument('prod')
    s.add_argument('--n', type=int, default=8)
    s.add_argument('--min', type=float, default=8.0, help='durée min d\'un extrait (s)')
    s.add_argument('--max', type=float, default=25.0, help='durée max d\'un extrait (s)')
    s.add_argument('--mots-cles', default=None)
    s.set_defaults(f=cmd_passages)

    s = sp.add_parser('script', help='proposer le script de commentaire (montage.json)')
    s.add_argument('prod')
    s.add_argument('--passages', required=True)
    s.add_argument('--titre')
    s.add_argument('--ollama', default=None, help='modèle Ollama local pour un brouillon (facultatif)')
    s.add_argument('--ecraser', action='store_true')
    s.set_defaults(f=cmd_script)

    s = sp.add_parser('narration', help='ajouter votre narration (un fichier par bloc)')
    s.add_argument('prod')
    s.add_argument('bloc', nargs='?')
    s.add_argument('fichier', nargs='?')
    s.add_argument('--synthetique', action='store_true', help='déclarer une voix de synthèse')
    s.add_argument('--tts-test', action='store_true', help='voix de synthèse locale pour TESTER le pipeline')
    s.set_defaults(f=cmd_narration)

    s = sp.add_parser('verifier', help='contrôler le montage')
    s.add_argument('prod')
    s.add_argument('--complet', action='store_true', help='recalculer aussi les SHA-256 des sources')
    s.set_defaults(f=cmd_verifier)

    s = sp.add_parser('apercu', help='rendre l\'aperçu filigrané')
    s.add_argument('prod')
    s.add_argument('--structure', action='store_true', help='aperçu sans narration (silence), pour caler le montage')
    s.set_defaults(f=cmd_apercu)

    s = sp.add_parser('valider', help='validation humaine obligatoire')
    s.add_argument('prod')
    s.add_argument('--relecteur')
    s.set_defaults(f=cmd_valider)

    s = sp.add_parser('exporter', help='export final 1080x1920 sans filigrane')
    s.add_argument('prod')
    s.set_defaults(f=cmd_exporter)

    s = sp.add_parser('resultats', help='saisir les résultats d\'une publication')
    s.add_argument('prod')
    s.add_argument('--plateforme', required=True, choices=config.PLATEFORMES)
    for k in ('url', 'date_publication', 'vues', 'likes', 'commentaires', 'partages', 'enregistrements',
              'duree_moyenne_visionnage_s', 'taux_completion_pct', 'abonnes_gagnes', 'statut', 'notes'):
        s.add_argument('--' + k.replace('_', '-'), dest=k)
    s.set_defaults(f=cmd_resultats)

    s = sp.add_parser('suivi', help='afficher le suivi des résultats')
    s.set_defaults(f=cmd_suivi)
    s = sp.add_parser('statut', help='état d\'une production (ou de toutes)')
    s.add_argument('prod', nargs='?')
    s.set_defaults(f=cmd_statut)
    s = sp.add_parser('journal', help='journal des productions')
    s.add_argument('prod', nargs='?')
    s.set_defaults(f=cmd_journal)
    return ap


def main(argv=None):
    a = parser().parse_args(argv)
    try:
        rc = a.f(a)
    except StudioError as e:
        print(f'ERREUR : {e}', file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print('\ninterrompu', file=sys.stderr)
        return 130
    return rc or 0


if __name__ == '__main__':
    sys.exit(main())
