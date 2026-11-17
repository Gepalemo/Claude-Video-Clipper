"""Repérage local des passages utiles (sans API) : fenêtres de phrases entières notées sur
la densité d'information, les termes saillants, les questions/chiffres, la netteté des bornes
et la confiance de la transcription. Le choix final reste humain (montage.json)."""
import math
import re
from collections import Counter

from .core import save_json
from .transcribe import mots_source

STOP = set("""
a à au aux avec ce ces cet cette c ça d dans de des du elle elles en et est été être eu il ils je j la le les
leur leurs l lui ma mais me même mes moi mon n ne nos notre nous on ou où par pas pour qu que qui sa se ses si
son sont sur ta te tes toi ton tu un une vos votre vous y était étaient fait faire plus très bien alors donc
voilà comme tout tous toute toutes aussi encore puis car ni sans sous chez entre vers cela ceci quoi dont
avoir ai as avons avez ont suis es sommes êtes c'est j'ai qu'il qu'on n'est d'un d'une l'on s'il
the a an and or but of to in on for with at by from is are was were be been it its this that these those i
you he she we they them his her our your my me so if then than as not no do does did have has had just
like really very can will would could should there here what which who whom when where why how all any
""".split())
FILLERS = {'euh', 'heu', 'bah', 'ben', 'hum', 'um', 'uh', 'erm', 'hmm', 'genre', 'voilà'}
ACCROCHES = {'pourquoi', 'comment', 'secret', 'erreur', 'jamais', 'toujours', 'personne', 'vrai', 'faux',
             'problème', 'solution', 'surprenant', 'incroyable', 'important', 'clé', 'mais', 'pourtant',
             'why', 'how', 'secret', 'mistake', 'never', 'always', 'nobody', 'truth', 'wrong', 'problem',
             'actually', 'however', 'key', 'important'}
TOKEN = re.compile(r"[\wÀ-ÿ'’-]+", re.UNICODE)


def tokens(text):
    return [t.lower().strip("'’-") for t in TOKEN.findall(text)]


def score_fenetre(lines, words, df, n_lines_total, mots_cles):
    text = ' '.join(l['text'] for l in lines)
    toks = tokens(text)
    if not toks:
        return 0, {}
    dur = lines[-1]['e'] - lines[0]['s']
    contenu = [t for t in toks if t not in STOP and len(t) > 2]
    # saillance : tf-idf moyen des mots de contenu (mots fréquents ici mais rares ailleurs)
    tf = Counter(contenu)
    sal = sum(c * math.log((1 + n_lines_total) / (1 + df.get(t, 0))) for t, c in tf.items()) / max(1, len(toks))
    densite = len(toks) / max(dur, 1e-3)
    dens_score = 1.0 - min(1.0, abs(densite - 2.8) / 2.0)
    ws = words[lines[0]['i0']:lines[-1]['i1'] + 1]
    conf = sum(w.get('p', 1) for w in ws) / max(1, len(ws))
    fillers = sum(1 for t in toks if t in FILLERS) / len(toks)
    accroche = sum(1 for t in tokens(lines[0]['text']) if t in ACCROCHES) + ('?' in lines[0]['text'])
    chiffres = len(re.findall(r'\d', text)) > 0
    fin_nette = lines[-1]['text'].rstrip()[-1:] in '.?!'
    cles = sum(tf.get(k, 0) for k in mots_cles)
    score = (sal * 4.0 + dens_score * 1.5 + conf * 1.5 - fillers * 8 + min(accroche, 2) * 0.6
             + chiffres * 0.4 + fin_nette * 0.8 + min(cles, 4) * 0.8)
    raisons = {'saillance': round(sal, 2), 'debit_mots_s': round(densite, 2), 'confiance': round(conf, 2),
               'hesitations_pct': round(fillers * 100, 1), 'accroche': accroche, 'chiffres': chiffres,
               'fin_nette': fin_nette, 'mots_cles': cles}
    return round(score, 3), raisons


def suggerer(prod, n=8, duree_min=8.0, duree_max=30.0, mots_cles=()):
    mots_cles = [m.lower() for m in mots_cles]
    candidats = []
    for sid in prod.state['sources']:
        words = mots_source(prod, sid)
        from clipper.fetch import sentences
        lines = sentences(words)
        df = Counter()
        for l in lines:
            df.update(set(tokens(l['text'])))
        for i in range(len(lines)):
            # une fenêtre commence en début de phrase
            if i > 0 and lines[i - 1]['text'].rstrip()[-1:] not in '.?!' and lines[i]['s'] - lines[i - 1]['e'] < 0.6:
                continue
            for j in range(i, len(lines)):
                dur = lines[j]['e'] - lines[i]['s']
                if dur > duree_max:
                    break
                if dur < duree_min:
                    continue
                sc, why = score_fenetre(lines[i:j + 1], words, df, len(lines), mots_cles)
                candidats.append({'source': sid, 'debut': round(lines[i]['s'], 2), 'fin': round(lines[j]['e'], 2),
                                  'duree': round(dur, 2), 'score': sc, 'raisons': why,
                                  'texte': ' '.join(l['text'] for l in lines[i:j + 1])})
    candidats.sort(key=lambda c: -c['score'])
    retenus = []
    for c in candidats:   # pas de chevauchement
        if all(c['source'] != r['source'] or c['fin'] <= r['debut'] or c['debut'] >= r['fin'] for r in retenus):
            retenus.append(c)
        if len(retenus) >= n:
            break
    retenus.sort(key=lambda c: (c['source'], c['debut']))
    for k, c in enumerate(retenus, 1):
        c['id'] = f'p{k}'
    save_json(prod.path('passages.json'), {'parametres': {'n': n, 'duree_min': duree_min, 'duree_max': duree_max,
                                                          'mots_cles': mots_cles}, 'passages': retenus})
    prod.log('passages_suggeres', nombre=len(retenus))
    return retenus
