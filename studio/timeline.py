"""Résolution du montage (montage.json -> timeline exacte) et contrôles avant aperçu/export.

- extraits alignés sur des mots entiers (clipper.cut.snap_range)
- durée de chaque narration = durée réelle du fichier enregistré (sinon estimée)
- durée totale 65-100 s, part de commentaire original, extraits trop longs
- affirmations à vérifier (chiffres, dates, superlatifs, noms propres)
- intégrité des sources et justificatifs, licences
- empreinte (fingerprint) de tout ce qui influence le rendu
"""
import difflib
import re

from . import config
from .core import load_json, sha256_file, sha256_json
from .rights import controle_integrite, licence, verifier_licence
from .script import A_ECRIRE
from .transcribe import mots_source

SUPERLATIFS = re.compile(r"\b(premier|première|seul|seule|record|jamais|toujours|tous|aucun|meilleur|pire|plus grand|"
                         r"plus petit|le plus|la plus|millions?|milliards?|pour ?cent|%|first|only|never|always|best|"
                         r"worst|largest|biggest|most|million|billion|percent|study|étude|selon|according)\b", re.I)


def _narr_visuel(seg, segs, idx, dur, prod):
    """Plan d'illustration d'une narration : séquence qui précède l'extrait suivant (continuité),
    sinon celle qui suit l'extrait précédent."""
    v = seg.get('visuel', 'auto')
    if isinstance(v, dict) and v.get('source'):
        return v['source'], float(v.get('debut', 0))
    nxt = next((s for s in segs[idx + 1:] if s['type'] == 'extrait'), None)
    prv = next((s for s in reversed(segs[:idx]) if s['type'] == 'extrait'), None)
    if nxt:
        return nxt['source'], max(0.0, nxt['debut'] - dur)
    if prv:
        src_dur = prod.state['sources'][prv['source']]['duree']
        return prv['source'], min(prv['fin'], max(0.0, src_dur - dur))
    first = next(iter(prod.state['sources']))
    return first, 0.0


def affirmations(texte):
    phrases = re.split(r'(?<=[.?!])\s+', texte.strip())
    out = []
    for p in phrases:
        noms = re.findall(r'(?<!^)(?<![.?!]\s)\b[A-ZÀ-Ý][\wÀ-ÿ-]{2,}', p)
        if re.search(r'\d', p) or SUPERLATIFS.search(p) or noms or '[FAIT À VÉRIFIER]' in p:
            out.append(p.strip())
    return [p for p in out if p]


def _tok(w):
    return re.sub(r"[^\w%$€]+", '', w.lower())


def aligner_texte(texte, mots):
    """Remplace les mots reconnus par Whisper par ceux du texte écrit, en gardant les temps de la voix.
    Les mots du texte non reconnus sont interpolés entre leurs voisins."""
    cible = texte.split()
    if not mots or not cible:
        return mots
    a, b = [_tok(w['w']) for w in mots], [_tok(w) for w in cible]
    times = [None] * len(cible)
    for blk in difflib.SequenceMatcher(None, a, b, autojunk=False).get_matching_blocks():
        for k in range(blk.size):
            w = mots[blk.a + k]
            times[blk.b + k] = (w['s'], w['e'])
    # extrémités : début du premier mot / fin du dernier mot reconnus
    if times[0] is None:
        times[0] = (mots[0]['s'], mots[0]['s'] + 0.2)
    if times[-1] is None:
        times[-1] = (max(mots[-1]['e'] - 0.2, times[0][1]), mots[-1]['e'])
    k = 0
    while k < len(times):
        if times[k] is None:
            j = k
            while times[j] is None:
                j += 1
            t0, t1 = times[k - 1][1], times[j][0]
            step = max(t1 - t0, 0.05 * (j - k)) / (j - k)
            for n in range(k, j):
                times[n] = (t0 + step * (n - k), t0 + step * (n - k + 1))
            k = j
        k += 1
    out = []
    for w, (s, e) in zip(cible, times):
        if out and s < out[-1]['e']:
            s = out[-1]['e']
        out.append({'w': w, 's': round(s, 3), 'e': round(max(e, s + 0.04), 3), 'p': 1.0})
    return out


def fusionner_elisions(mots):
    """Whisper découpe souvent les élisions françaises (« l » + « 'eau » -> « l'eau ») et la ponctuation."""
    out = []
    for w in mots:
        t = w['w'].strip()
        if out and t[:1] in "'’" and w['s'] - out[-1]['e'] < 0.3:
            out[-1] = {**out[-1], 'w': out[-1]['w'] + "'" + t[1:], 'e': w['e']}
        elif out and t and not _tok(t) and not re.search(r'\d', t):   # ponctuation isolée : « trucs » + « ? »
            out[-1] = {**out[-1], 'w': out[-1]['w'] + t, 'e': max(out[-1]['e'], w['e'])}
        else:
            out.append(dict(w))
    return out


def corriger(mots, corrections):
    """Applique les corrections de sous-titres de montage.json : {"mal reconnu": "correct", ...}.
    Fonctionne sur une suite de mots ; les temps sont répartis sur la nouvelle formulation."""
    if not corrections:
        return mots
    out = list(mots)
    for faux, juste in corrections.items():
        cle = [_tok(x) for x in faux.split() if _tok(x)]
        rep = juste.split()
        if not cle or not rep:
            continue
        i = 0
        while i <= len(out) - len(cle):
            if [_tok(w['w']) for w in out[i:i + len(cle)]] == cle:
                s, e = out[i]['s'], out[i + len(cle) - 1]['e']
                punct = re.sub(r'.*?([.,;:!?…]*)$', r'\1', out[i + len(cle) - 1]['w'])
                step = (e - s) / len(rep)
                new = [{'w': r, 's': round(s + step * k, 3), 'e': round(s + step * (k + 1), 3), 'p': 1.0}
                       for k, r in enumerate(rep)]
                if punct and not new[-1]['w'].endswith(punct):
                    new[-1]['w'] += punct
                out[i:i + len(cle)] = new
                i += len(rep)
            else:
                i += 1
    return out


def resoudre(prod, exiger_narration=False):
    """Retourne la timeline résolue + rapport de contrôles {'bloquants', 'avertissements', ...}."""
    from clipper.cut import boundary_warnings, snap_range
    montage = prod.montage()
    segs = montage['segments']
    bloq, avert, timeline, faits = [], [], [], []
    t = 0.0
    words_cache = {}
    corrections = montage.get('corrections_sous_titres') or {}
    for idx, s in enumerate(segs):
        if s['type'] == 'extrait':
            if s['source'] not in prod.state['sources']:
                bloq.append(f"{s['id']} : source inconnue {s['source']}")
                continue
            words = words_cache.setdefault(s['source'], mots_source(prod, s['source']))
            sn = snap_range(float(s['debut']), float(s['fin']), words)
            if not sn:
                bloq.append(f"{s['id']} : aucun mot entre {s['debut']} et {s['fin']} s")
                continue
            a, b, i0, i1 = sn
            src_dur = prod.state['sources'][s['source']]['duree']
            b = min(b, src_dur)
            for w in boundary_warnings([(s['debut'], s['fin'])], words):
                avert.append(f"{s['id']} : {w}")
            if b - a > config.EXTRAIT_MAX_S:
                avert.append(f"{s['id']} : extrait de {b - a:.0f} s (> {config.EXTRAIT_MAX_S:.0f} s), "
                             'raccourcissez-le pour garder un contenu transformatif')
            texte = ' '.join(w['w'] for w in words[i0:i1 + 1])
            mots = [{**w, 's': round(w['s'] - a + t, 3), 'e': round(w['e'] - a + t, 3)} for w in words[i0:i1 + 1]]
            mots = corriger(fusionner_elisions(mots), corrections)
            texte = ' '.join(w['w'] for w in mots)
            timeline.append({'id': s['id'], 'type': 'extrait', 'source': s['source'], 'debut': round(a, 3),
                             'fin': round(b, 3), 'duree': round(b - a, 3), 't0': round(t, 3), 'mots': mots,
                             'texte': texte})
            faits += [{'segment': s['id'], 'origine': 'extrait (propos de la source)', 'affirmation': p}
                      for p in affirmations(texte)]
            t += b - a
        elif s['type'] == 'narration':
            texte = s.get('texte', '').strip()
            if not texte or A_ECRIRE in texte:
                bloq.append(f"{s['id']} : texte de narration à écrire (trame [À ÉCRIRE ...] dans montage.json)")
            rec = prod.state['narration'].get(s['id'])
            ratio = 1.0
            if rec:
                f = prod.path(rec['fichier'])
                if not f.exists() or sha256_file(f) != rec['sha256']:
                    bloq.append(f"{s['id']} : fichier de narration modifié ou manquant, réimportez-le")
                    rec = None
            if rec:
                dur, mots_n = rec['duree'], load_json(prod.path('narration', f"{s['id']}.mots.json"), [])
                ratio = difflib.SequenceMatcher(None, _norm(texte), _norm(rec['transcription'])).ratio()
                if ratio < 0.6 and A_ECRIRE not in texte:
                    avert.append(f"{s['id']} : l'enregistrement s'écarte du texte écrit (similarité {ratio:.0%}). "
                                 'Les faits sont vérifiés sur le texte : alignez l\'un sur l\'autre')
                if rec.get('synthetique'):
                    avert.append(f"{s['id']} : voix de synthèse (test). À remplacer par votre voix, ou à déclarer "
                                 'comme contenu généré sur chaque plateforme')
                parle = rec['transcription']
                if ratio >= 0.6 and A_ECRIRE not in texte:
                    mots_n = aligner_texte(texte, mots_n)   # sous-titres = votre texte exact, calé sur la voix
            else:
                if exiger_narration:
                    bloq.append(f"{s['id']} : narration non enregistrée (prod narration {prod.id} {s['id']} <fichier>)")
                est = ({'intro': 5.0, 'conclusion': 7.0}.get(s['id'], 11.0) if A_ECRIRE in texte
                       else max(1.5, len(texte.split()) / config.MOTS_PAR_SECONDE))
                dur, mots_n, parle = est, [], None
            vsrc, vdeb = _narr_visuel(s, segs, idx, dur, prod)
            mots = corriger(fusionner_elisions([{**w, 's': round(w['s'] + t, 3), 'e': round(w['e'] + t, 3)}
                                                for w in mots_n]), corrections)
            timeline.append({'id': s['id'], 'type': 'narration', 'duree': round(dur, 3), 't0': round(t, 3),
                             'estimee': rec is None, 'audio': rec['fichier'] if rec else None,
                             'visuel': {'source': vsrc, 'debut': round(vdeb, 3)}, 'mots': mots, 'texte': texte})
            if A_ECRIRE not in texte:
                faits += [{'segment': s['id'], 'origine': 'votre narration', 'affirmation': p}
                          for p in affirmations(texte)]
            if parle and ratio < 0.6 and A_ECRIRE not in texte:
                faits += [{'segment': s['id'], 'origine': 'narration enregistrée (hors texte)', 'affirmation': p}
                          for p in affirmations(parle) if _norm(p) not in _norm(texte)][:3]
            t += dur
        else:
            bloq.append(f"segment {s.get('id')} : type inconnu {s.get('type')}")

    total = round(t, 2)
    narr = sum(x['duree'] for x in timeline if x['type'] == 'narration')
    part = narr / total if total else 0
    if not config.DUREE_MIN <= total <= config.DUREE_MAX:
        (bloq if exiger_narration else avert).append(
            f'durée totale {total:.1f} s hors de la cible {config.DUREE_MIN:.0f}-{config.DUREE_MAX:.0f} s')
    if part < config.PART_NARRATION_MIN:
        avert.append(f'commentaire original = {part:.0%} de la durée (< {config.PART_NARRATION_MIN:.0%}) : '
                     'risque de « contenu réutilisé / non original » sur les plateformes')
    if not any(x['type'] == 'extrait' for x in timeline):
        avert.append('aucun extrait : vidéo 100 % narration')
    for sid in {x['source'] for x in timeline if x['type'] == 'extrait'} | {x['visuel']['source'] for x in timeline if x['type'] == 'narration'}:
        b, a = verifier_licence(licence(prod, sid))
        bloq += [f'{sid} : {m}' for m in b]
        avert += [f'{sid} : {m}' for m in a]
    return {'timeline': timeline, 'duree_totale': total, 'part_narration': round(part, 3),
            'bloquants': bloq, 'avertissements': list(dict.fromkeys(avert)), 'faits': _dedup(faits)}


def _norm(t):
    return re.sub(r'[^\w]+', ' ', t.lower()).strip()


def _dedup(faits):
    seen, out = set(), []
    for f in faits:
        k = _norm(f['affirmation'])
        if k not in seen:
            seen.add(k)
            out.append({**f, 'id': f'f{len(out) + 1}'})
    return out


def empreinte(prod, res=None):
    """Empreinte de tout ce qui détermine le rendu : montage, sources, licences, preuves, narrations."""
    res = res or resoudre(prod)
    data = {
        'montage': prod.montage(),
        'sources': {k: {'sha256': v['sha256'], 'licence_sha256': v['licence_sha256']}
                    for k, v in prod.state['sources'].items()},
        'preuves': {k: [p['sha256'] for p in licence(prod, k).get('preuves', [])] for k in prod.state['sources']},
        'narration': {k: v['sha256'] for k, v in prod.state['narration'].items()},
        'timeline': [{k: v for k, v in x.items() if k != 'mots'} for x in res['timeline']],
        'reglages': {'W': config.W, 'H': config.H, 'FPS': config.FPS, 'sous_titres': config.SOUS_TITRES},
    }
    return sha256_json(data)


def verifier(prod, exiger_narration=False, complet=False):
    res = resoudre(prod, exiger_narration)
    res['bloquants'] = controle_integrite(prod, complet=complet) + res['bloquants']
    return res


def resume(res):
    lines = [f"{'segment':12} {'type':10} {'début':>7} {'durée':>6}  détail"]
    for x in res['timeline']:
        det = (f"{x['source']} {x['debut']:.1f}-{x['fin']:.1f} s" if x['type'] == 'extrait'
               else ('durée estimée (pas encore enregistrée)' if x['estimee'] else x['audio']))
        lines.append(f"{x['id']:12} {x['type']:10} {x['t0']:7.1f} {x['duree']:6.1f}  {det}")
    lines.append(f"TOTAL {res['duree_totale']:.1f} s  (cible {config.DUREE_MIN:.0f}-{config.DUREE_MAX:.0f} s), "
                 f"commentaire original {res['part_narration']:.0%}")
    return '\n'.join(lines)

