"""Métadonnées de publication par plateforme (à copier-coller : la publication reste manuelle)."""
import re

from . import config
from .core import save_json, slug
from .rights import credits, licence


def _hashtag(word):
    w = re.sub(r'[^\w]', '', slug(word).replace('-', ' ').title().replace(' ', ''))
    return f'#{w}' if w and not w.isdigit() else None


def _cut(text, n):
    return text if len(text) <= n else text[:n - 1].rsplit(' ', 1)[0] + '…'


def generer(prod, res, fichier=None):
    m = prod.montage()
    titre = (m.get('titre') or prod.state['nom']).strip()
    accroche = (m.get('accroche') or next((s['texte'] for s in m['segments'] if s['type'] == 'narration'), '')).strip()
    tags = [t if t.startswith('#') else _hashtag(t) for t in (m.get('hashtags') or [])]
    if not tags:   # à défaut de hashtags choisis, suggestion à partir des mots-clés
        tags = [_hashtag(t) for t in m.get('mots_cles', [])]
    tags = list(dict.fromkeys(t for t in tags if t))
    cred = credits(prod)
    synth = any(v.get('synthetique') for v in prod.state['narration'].values())
    lic_sa = any(licence(prod, s)['type'] in ('cc-by-sa', 'cc-by-nc-sa') for s in prod.state['sources'])
    credit_txt = ('\n\nCrédits : ' + ' | '.join(cred)) if cred else ''
    if lic_sa:
        credit_txt += '\nCette vidéo est partagée sous licence CC BY-SA 4.0.'
    a_faire = ['Publier manuellement (aucune publication automatique).',
               'Vérifier l\'aperçu de la miniature / couverture dans l\'application.']
    if synth:
        a_faire.insert(0, 'Activer l\'étiquette « contenu généré par IA / modifié » (voix de synthèse).')

    def lim(p):
        return config.LIMITES_PLATEFORMES[p]
    yt_tags = tags[:lim('youtube_shorts')['hashtags'] - 1] + ['#Shorts']
    meta = {
        'production': prod.id, 'fichier': fichier, 'duree_s': res['duree_totale'], 'langue': prod.state.get('langue'),
        'voix_synthetique': synth, 'credits': cred, 'a_faire_avant_publication': a_faire,
        'youtube_shorts': {
            'titre': _cut(titre, lim('youtube_shorts')['titre']),
            'description': _cut(f"{accroche}{credit_txt}\n\n{' '.join(yt_tags)}", lim('youtube_shorts')['description']),
            'tags': [t.lstrip('#') for t in yt_tags], 'contenu_modifie_ou_synthetique': synth,
            'categorie_suggeree': 'Éducation', 'visibilite_initiale': 'privée (à passer en public après contrôle)'},
        'tiktok': {'legende': _cut(f"{titre} — {accroche}{credit_txt}\n{' '.join(tags[:lim('tiktok')['hashtags']])}",
                                   lim('tiktok')['legende']),
                   'etiquette_contenu_ia': synth},
        'instagram_reels': {'legende': _cut(f"{titre}\n\n{accroche}{credit_txt}\n\n"
                                            f"{' '.join(tags[:min(5, lim('instagram_reels')['hashtags'])])}",
                                            lim('instagram_reels')['legende']),
                            'etiquette_ia': synth},
        'facebook_reels': {'legende': _cut(f"{titre}\n{accroche}{credit_txt}\n{' '.join(tags[:5])}",
                                           lim('facebook_reels')['legende']),
                           'etiquette_ia': synth},
    }
    out = prod.path('export', 'metadonnees.json')
    save_json(out, meta)
    md = [f"# Publication : {titre}", '', f"Fichier : `{fichier}`  ·  durée {res['duree_totale']:.1f} s", '',
          '## À faire avant de publier', *[f'- [ ] {x}' for x in a_faire], '']
    for p in config.PLATEFORMES:
        md += [f'## {p}', '']
        for k, v in meta[p].items():
            md += [f'**{k}**', '', '```', str(v), '```', '']
    prod.path('export', 'metadonnees.md').write_text('\n'.join(md), encoding='utf-8')
    return meta
