"""Proposition de script de commentaire original -> montage.json (source unique de vérité du montage).

Le brouillon alterne narration (votre commentaire) et extraits. Sans outil externe, les blocs de
narration sont des trames à compléter marquées [À ÉCRIRE ...] : l'export est bloqué tant qu'il en
reste. Option --ollama <modèle> : brouillon rédigé par un LLM local et gratuit (Ollama), à relire.
Dans Claude Code, Claude peut aussi rédiger ces blocs (voir .claude/skills/produce-short).
"""
import json
import re
import urllib.request

from . import config
from .core import StudioError, load_json, save_json
from .passages import STOP, tokens

A_ECRIRE = '[À ÉCRIRE'


VERBES_COURANTS = set('''peut peuvent faut doit doivent veut sais savoir dire dit fait font faire avoir être était
sont vont aller allez passe passer reste rester commence voici voila pourquoi comment quand alors aussi encore
toujours jamais beaucoup chose choses parce cette celui celle ceux elles there their would could should about
which where because really thing things going'''.split())


def termes_cles(text, k=5):
    from collections import Counter
    toks = [re.sub(r"^(?:[ldnsjmtc]|qu)['’]", '', t) for t in tokens(text)]
    c = Counter(t for t in toks if t not in STOP and t not in VERBES_COURANTS and len(t) > 4
                and not t.isdigit() and '-' not in t)
    return [t for t, _ in c.most_common(k)]


def premiere_phrase(text, maxlen=140):
    m = re.split(r'(?<=[.?!])\s', text.strip(), maxsplit=1)
    s = m[0] if m else text
    return s if len(s) <= maxlen else s[:maxlen].rsplit(' ', 1)[0] + '…'


def trames(passages, auteur):
    blocs = {'intro': f"{A_ECRIRE} — ACCROCHE (3-6 s) : une phrase qui pose la question ou l'enjeu. "
                      f"Piste : pourquoi « {premiere_phrase(passages[0]['texte'], 80)} » compte pour votre public ?]"}
    for k, p in enumerate(passages, 1):
        cles = ', '.join(termes_cles(p['texte']))
        blocs[f'analyse{k}'] = (f"{A_ECRIRE} — VOTRE ANALYSE de l'extrait {k} (8-15 s) : ce qu'il montre, ce qu'il "
                                f"ne dit pas, votre expérience ou un fait vérifié. Mots-clés : {cles}.]")
    blocs['conclusion'] = (f"{A_ECRIRE} — CONCLUSION (5-8 s) : votre avis en une phrase + une question au public. "
                           f"Mentionnez la source ({auteur}) si la licence l'exige.]")
    return blocs


def ollama_brouillon(modele, passages, langue, url='http://127.0.0.1:11434/api/generate'):
    """Brouillon par LLM local (Ollama). Uniquement localhost ; aucune donnée ne sort de la machine."""
    extraits = '\n'.join(f"EXTRAIT {k}: {p['texte']}" for k, p in enumerate(passages, 1))
    ids = ['intro'] + [f'analyse{k}' for k in range(1, len(passages) + 1)] + ['conclusion']
    prompt = (f"Langue : {langue or 'fr'}. Tu aides un créateur à écrire un COMMENTAIRE ORIGINAL pour une vidéo "
              f"verticale de 65 à 100 secondes qui intercale ces extraits.\n{extraits}\n\n"
              "Écris des blocs de narration courts, à la première personne, qui ANALYSENT ou CRITIQUENT les extraits "
              "(pas de paraphrase). N'invente aucun chiffre ni fait ; si un fait est nécessaire écris [FAIT À VÉRIFIER]. "
              f"Réponds UNIQUEMENT en JSON avec les clés {ids}. intro : 1-2 phrases d'accroche. "
              "analyseN : 2-3 phrases. conclusion : 1-2 phrases + une question au public.")
    body = json.dumps({'model': modele, 'prompt': prompt, 'stream': False, 'format': 'json'}).encode()
    req = urllib.request.Request(url, data=body, headers={'Content-Type': 'application/json'})
    try:
        with urllib.request.urlopen(req, timeout=300) as r:
            data = json.loads(json.loads(r.read().decode())['response'])
    except Exception as e:
        raise StudioError(f'Ollama indisponible ({e}). Installez https://ollama.com puis : ollama pull {modele}')
    return {k: str(data.get(k, '')).strip() for k in ids if str(data.get(k, '')).strip()}


def creer_montage(prod, ids_passages, titre=None, ollama=None, ecraser=False):
    if prod.montage_path.exists() and not ecraser:
        raise StudioError('montage.json existe déjà (ajoutez --ecraser pour repartir de zéro)')
    pas = load_json(prod.path('passages.json'))
    if not pas:
        raise StudioError('lancez d\'abord  prod passages ' + prod.id)
    by_id = {p['id']: p for p in pas['passages']}
    manquants = [i for i in ids_passages if i not in by_id]
    if manquants:
        raise StudioError(f"passages inconnus : {manquants} (disponibles : {', '.join(by_id)})")
    chosen = [by_id[i] for i in ids_passages]
    from .rights import licence
    auteur = licence(prod, chosen[0]['source'])['auteur']
    blocs = trames(chosen, auteur)
    origine = 'trame'
    if ollama:
        blocs.update(ollama_brouillon(ollama, chosen, prod.state.get('langue')))
        origine = f'ollama:{ollama}'
    segs = [{'id': 'intro', 'type': 'narration', 'texte': blocs['intro'], 'visuel': 'auto'}]
    for k, p in enumerate(chosen, 1):
        segs.append({'id': f'extrait{k}', 'type': 'extrait', 'source': p['source'], 'debut': p['debut'],
                     'fin': p['fin'], 'passage': p['id'], 'texte_source': p['texte']})
        if k < len(chosen):
            segs.append({'id': f'analyse{k}', 'type': 'narration', 'texte': blocs[f'analyse{k}'], 'visuel': 'auto'})
    # l'analyse du dernier extrait est fusionnée avec la conclusion pour tenir la durée
    last = blocs.get(f'analyse{len(chosen)}', '')
    concl = blocs['conclusion'] if A_ECRIRE in blocs['conclusion'] or A_ECRIRE in last else f"{last} {blocs['conclusion']}"
    segs.append({'id': 'conclusion', 'type': 'narration', 'texte': concl, 'visuel': 'auto'})
    montage = {
        'version': 1, 'titre': titre or prod.state['nom'], 'accroche': '', 'mots_cles': termes_cles(
            ' '.join(p['texte'] for p in chosen), 6),
        'hashtags': [], 'origine_brouillon': origine,
        'corrections_sous_titres': {},
        'sous_titres': {'accent': config.SOUS_TITRES['accent'], 'y': config.SOUS_TITRES['y'],
                        'majuscules': True, 'credit_a_l_ecran': True},
        'segments': segs,
    }
    save_json(prod.montage_path, montage)
    exporter_texte(prod, montage)
    prod.set_statut('script')
    prod.log('script_propose', passages=ids_passages, origine=origine)
    return montage


def exporter_texte(prod, montage):
    """script_narration.txt : texte à lire pendant l'enregistrement (un bloc par fichier audio)."""
    lines = [f"# {montage['titre']}", '# Enregistrez un fichier audio par bloc, puis :',
             f'#   python run.py prod narration {prod.id} <bloc> <fichier.wav>', '']
    for s in montage['segments']:
        if s['type'] == 'narration':
            n = len(s['texte'].split())
            lines += [f"== {s['id']}  (~{n / config.MOTS_PAR_SECONDE:.0f} s)", s['texte'], '']
        else:
            lines += [f"-- [{s['id']} : extrait {s['source']} {s['debut']:.1f}-{s['fin']:.1f} s] "
                      f"« {premiere_phrase(s.get('texte_source', ''), 90)} »", '']
    prod.path('script_narration.txt').write_text('\n'.join(lines), encoding='utf-8')
