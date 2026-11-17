"""Tests automatisés du pipeline studio (sans Whisper ni réseau : transcriptions simulées).

    .venv/Scripts/python -m pytest tests      (Windows)
    .venv/bin/python -m pytest tests          (macOS / Linux)
"""
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from studio import config, core, metadata, results, review, rights, timeline  # noqa: E402
from studio.core import Production, StudioError, save_json  # noqa: E402


@pytest.fixture(autouse=True)
def isole(tmp_path, monkeypatch):
    monkeypatch.setattr(config, 'OUTPUT', tmp_path / 'output')
    monkeypatch.setattr(config, 'REGISTRE', tmp_path / 'output' / '_registre')
    monkeypatch.setattr(config, 'JOURNAL', tmp_path / 'output' / '_registre' / 'journal.jsonl')
    monkeypatch.setattr(config, 'SUIVI_CSV', tmp_path / 'output' / '_registre' / 'suivi.csv')
    monkeypatch.setenv('STUDIO_TESTS', '1')
    yield


@pytest.fixture(scope='session')
def video(tmp_path_factory):
    """Vidéo 16:9 de 60 s avec audio (générée : aucun droit de tiers)."""
    p = tmp_path_factory.mktemp('src') / 'source.mp4'
    subprocess.run(['ffmpeg', '-v', 'error', '-y', '-f', 'lavfi', '-i', 'testsrc2=s=640x360:r=30:d=60',
                    '-f', 'lavfi', '-i', 'sine=f=440:d=60', '-c:v', 'libx264', '-preset', 'ultrafast',
                    '-pix_fmt', 'yuv420p', '-c:a', 'aac', '-shortest', str(p)], check=True)
    return p


@pytest.fixture
def preuve(tmp_path):
    p = tmp_path / 'contrat.txt'
    p.write_text('Autorisation écrite de montage et diffusion.', encoding='utf-8')
    return p


def faux_mots(debut=0.0, fin=60.0):
    """Une phrase de 8 mots toutes les 4 s, ponctuée."""
    mots, t, k = [], debut, 0
    while t + 4 <= fin:
        for i in range(8):
            w = f'mot{k}' + ('.' if i == 7 else '')
            mots.append({'w': w, 's': round(t + i * 0.45, 2), 'e': round(t + i * 0.45 + 0.4, 2), 'p': 0.95})
            k += 1
        t += 4
    return mots


def production(video, preuve, narr=True, duree_narr=(10, 12, 10)):
    p = Production.create('Test')
    rights.importer_source(p, video, 'proprietaire', 'Moi', preuves=[preuve])
    save_json(p.path('transcriptions', 'src1', 'mots.json'), faux_mots())
    segs = [{'id': 'intro', 'type': 'narration', 'texte': 'Voici une introduction originale et claire.', 'visuel': 'auto'},
            {'id': 'extrait1', 'type': 'extrait', 'source': 'src1', 'debut': 4.0, 'fin': 23.5},
            {'id': 'analyse1', 'type': 'narration', 'texte': 'Mon analyse personnelle de cet extrait.', 'visuel': 'auto'},
            {'id': 'extrait2', 'type': 'extrait', 'source': 'src1', 'debut': 32.0, 'fin': 51.5},
            {'id': 'conclusion', 'type': 'narration', 'texte': 'Ma conclusion. Et vous ?', 'visuel': 'auto'}]
    save_json(p.montage_path, {'titre': 'Titre test', 'segments': segs, 'mots_cles': ['analyse'],
                               'hashtags': ['#test']})
    if narr:
        for bloc, d in zip(('intro', 'analyse1', 'conclusion'), duree_narr):
            set_narration(p, bloc, d)
    return p


def set_narration(p, bloc, duree, freq=220):
    f = p.path('narration', f'{bloc}.wav')
    subprocess.run(['ffmpeg', '-v', 'error', '-y', '-f', 'lavfi', '-i', f'sine=f={freq}:d={duree}', '-ar', '48000',
                    '-ac', '1', str(f)], check=True)
    texte = next(s['texte'] for s in p.montage()['segments'] if s['id'] == bloc)
    n = len(texte.split())
    save_json(p.path('narration', f'{bloc}.mots.json'),
              [{'w': w, 's': i * duree / n, 'e': (i + 0.9) * duree / n, 'p': 1} for i, w in enumerate(texte.split())])
    p.state['narration'][bloc] = {'bloc': bloc, 'fichier': f'narration/{bloc}.wav', 'duree': float(duree),
                                  'sha256': core.sha256_file(f), 'synthetique': False, 'transcription': texte}
    p.save()


# ---------------- droits ----------------

def test_source_sans_preuve_refusee(video):
    p = Production.create('A')
    with pytest.raises(StudioError, match='justificatif'):
        rights.importer_source(p, video, 'proprietaire', 'Moi')


def test_licence_nd_refusee(video, preuve):
    p = Production.create('B')
    with pytest.raises(StudioError, match='ND'):
        rights.importer_source(p, video, 'cc-by-nd', 'X', preuves=[preuve], attribution='X')


def test_licence_tiers_exige_modif(video, preuve):
    p = Production.create('C')
    with pytest.raises(StudioError, match='modification'):
        rights.importer_source(p, video, 'licence', 'Studio X', preuves=[preuve])
    src, avert = rights.importer_source(p, video, 'licence', 'Studio X', preuves=[preuve], modif=True)
    assert any('commercial' in a for a in avert)


def test_cc_by_exige_attribution(video, preuve):
    p = Production.create('D')
    with pytest.raises(StudioError, match='attribution'):
        rights.importer_source(p, video, 'cc-by', 'Auteur', preuves=[preuve])
    rights.importer_source(p, video, 'cc-by', 'Auteur', preuves=[preuve], url='https://exemple.org',
                           attribution='« Titre » par Auteur, CC BY 4.0')
    assert rights.credits(p) == ['« Titre » par Auteur, CC BY 4.0']


def test_declaration_seule_acceptee_pour_contenu_propre(video):
    p = Production.create('E')
    src, _ = rights.importer_source(p, video, 'own', 'Moi', declaration="J'ai filmé cette vidéo.")
    rec = rights.licence(p, src['id'])
    assert rec['type'] == 'proprietaire' and rec['declaration_horodatee']['texte']


def test_integrite_preuve_modifiee(video, preuve):
    p = Production.create('F')
    rights.importer_source(p, video, 'proprietaire', 'Moi', preuves=[preuve])
    assert rights.controle_integrite(p) == []
    proof = next(p.path('droits', 'src1', 'preuves').iterdir())
    proof.write_text('falsifié', encoding='utf-8')
    assert any('justificatif' in x for x in rights.controle_integrite(p))


# ---------------- montage ----------------

def test_duree_et_originalite(video, preuve):
    p = production(video, preuve)
    res = timeline.verifier(p, exiger_narration=True)
    assert res['bloquants'] == []
    assert config.DUREE_MIN <= res['duree_totale'] <= config.DUREE_MAX
    assert 0.3 < res['part_narration'] < 0.5


def test_duree_trop_courte_bloque(video, preuve):
    p = production(video, preuve, duree_narr=(2, 2, 2))
    res = timeline.verifier(p, exiger_narration=True)
    assert any('durée totale' in b for b in res['bloquants'])


def test_trame_non_ecrite_bloque(video, preuve):
    p = production(video, preuve)
    m = p.montage()
    m['segments'][0]['texte'] = '[À ÉCRIRE — accroche]'
    save_json(p.montage_path, m)
    assert any('à écrire' in b for b in timeline.verifier(p, True)['bloquants'])


def test_alignement_texte_ecrit():
    mots = [{'w': 'Voisi', 's': 0.0, 'e': 0.3}, {'w': 'mon', 's': 0.35, 'e': 0.5},
            {'w': 'analise', 's': 0.55, 'e': 1.0}, {'w': 'perso.', 's': 1.1, 'e': 1.5}]
    out = timeline.aligner_texte('Voici mon analyse personnelle.', mots)
    assert [w['w'] for w in out] == ['Voici', 'mon', 'analyse', 'personnelle.']
    assert out[0]['s'] == 0.0 and out[-1]['e'] == 1.5
    assert all(a['e'] <= b['s'] + 1e-6 for a, b in zip(out, out[1:]))


def test_corrections_et_elisions():
    mots = [{'w': 'l', 's': 0, 'e': 0.1}, {'w': "'eau", 's': 0.1, 'e': 0.4}, {'w': 'de', 's': 0.5, 'e': 0.6},
            {'w': 'pli.', 's': 0.6, 'e': 0.9}]
    m = timeline.corriger(timeline.fusionner_elisions(mots), {'de pli': 'de pluie'})
    assert [w['w'] for w in m] == ["l'eau", 'de', 'pluie.']


def test_ponctuation_isolee_et_chiffres():
    mots = [{'w': 'Les', 's': 0, 'e': 0.2}, {'w': 'trucs', 's': 0.2, 'e': 0.5}, {'w': '?', 's': 0.5, 'e': 0.5},
            {'w': 'Parce', 's': 0.6, 'e': 0.8}, {'w': 'ces', 's': 1.0, 'e': 1.1}, {'w': '3', 's': 1.1, 'e': 1.2},
            {'w': ',1', 's': 1.2, 'e': 1.3}, {'w': 'millions', 's': 1.3, 'e': 1.6}]
    m = timeline.corriger(timeline.fusionner_elisions(mots), {'Les trucs ? Parce': "Le truc, c'est",
                                                             '3 ,1 millions': '3,8 millions'})
    assert ' '.join(w['w'] for w in m) == "Le truc, c'est ces 3,8 millions"


def test_affirmations():
    f = timeline.affirmations("Selon une étude, 86 % de l'évaporation vient des océans. J'aime la pluie.")
    assert len(f) == 1 and '86' in f[0]


# ---------------- validation humaine ----------------

def reponses(monkeypatch, refus_index=None):
    seq = iter(['Relecteur'] + (['n'] if refus_index == 0 else []) + ['o', 'Réf.'] * 200)
    it = []

    def fake(prompt=''):
        if '[o/n]' in prompt:
            it.append(1)
            return 'n' if refus_index is not None and len(it) == refus_index else 'o'
        return next(seq) if 'nom' in prompt.lower() else 'Référence de vérification'
    monkeypatch.setattr('builtins.input', fake)


def faux_apercu(p):
    res = timeline.verifier(p, exiger_narration=True)
    f = p.path('apercu', 'apercu.mp4')
    f.write_bytes(b'apercu')
    save_json(p.path('apercu', 'apercu.json'), {'empreinte': timeline.empreinte(p, res), 'sha256': core.sha256_file(f)})


def test_export_refuse_sans_validation(video, preuve):
    p = production(video, preuve)
    fp = timeline.empreinte(p)
    with pytest.raises(StudioError, match='aucune validation'):
        review.validation_courante(p, fp)


def test_validation_puis_modification_invalide(video, preuve, monkeypatch):
    p = production(video, preuve)
    faux_apercu(p)
    reponses(monkeypatch)
    rec = review.valider(p)
    assert rec['approuve']
    fp = timeline.empreinte(p)
    assert review.validation_courante(p, fp)['relecteur'] == 'Relecteur'
    set_narration(p, 'analyse1', 12, freq=330)         # nouvelle prise de narration
    with pytest.raises(StudioError, match='changé'):
        review.validation_courante(p, timeline.empreinte(p))


def test_validation_refusee(video, preuve, monkeypatch):
    p = production(video, preuve)
    faux_apercu(p)
    reponses(monkeypatch, refus_index=2)
    rec = review.valider(p)
    assert not rec['approuve'] and rec['refus']
    with pytest.raises(StudioError, match='pas approuvée'):
        review.validation_courante(p, timeline.empreinte(p))


def test_validation_exige_apercu_a_jour(video, preuve, monkeypatch):
    p = production(video, preuve)
    faux_apercu(p)
    m = p.montage()
    m['titre'] = 'Autre titre'
    save_json(p.montage_path, m)
    reponses(monkeypatch)
    with pytest.raises(StudioError, match='aperçu'):
        review.valider(p)


def test_validation_refuse_entree_non_interactive(video, preuve, monkeypatch):
    p = production(video, preuve)
    faux_apercu(p)
    monkeypatch.delenv('STUDIO_TESTS')
    monkeypatch.setattr(sys.stdin, 'isatty', lambda: False, raising=False)
    with pytest.raises(StudioError, match='humain'):
        review.valider(p)


# ---------------- suivi, journal, métadonnées ----------------

def test_csv_suivi():
    results.ajouter_export('p1', 'Titre', 'f.mp4', 'abc', 80.0)
    assert len(results.lire()) == len(config.PLATEFORMES)
    row = results.maj('p1', 'tiktok', url='https://t/1', vues='1200', likes='80')
    assert row['statut'] == 'publié' and row['date_releve']
    with pytest.raises(StudioError):
        results.maj('p1', 'tiktok', vues='beaucoup')
    results.ajouter_export('p1', 'Titre', 'f2.mp4', 'def', 81.0)       # ré-export : résultats conservés
    r = next(x for x in results.lire() if x['plateforme'] == 'tiktok')
    assert r['vues'] == '1200' and r['fichier'] == 'f2.mp4'
    raw = config.SUIVI_CSV.read_bytes()
    assert raw.startswith(b'\xef\xbb\xbf') and b';' in raw.splitlines()[0]


def test_journal(video, preuve):
    p = production(video, preuve)
    actions = [e['action'] for e in core.lire_journal(p.id)]
    assert 'source_importee' in actions


def test_metadonnees_limites(video, preuve):
    p = production(video, preuve)
    m = p.montage()
    m['titre'] = 'T' * 300
    save_json(p.montage_path, m)
    meta = metadata.generer(p, timeline.verifier(p, True), 'x.mp4')
    assert len(meta['youtube_shorts']['titre']) <= 100
    assert '#Shorts' in meta['youtube_shorts']['description']
    for k in ('tiktok', 'instagram_reels', 'facebook_reels'):
        assert len(meta[k]['legende']) <= 2200
    assert json.loads(p.path('export', 'metadonnees.json').read_text(encoding='utf-8'))['fichier'] == 'x.mp4'


# ---------------- rendu ----------------

def test_rendu_complet_et_recadrage_visage(video, preuve, monkeypatch, tmp_path):
    """Rendu réel (ffmpeg) avec un visage simulé : vérifie le chemin « crop » du recadrage 9:16."""
    from clipper import reframe
    from studio import render
    monkeypatch.setattr(reframe, 'analyse_range',
                        lambda v, s, d, w, h: [{'a': 0, 'b': d / 2, 'face': (0.7, 0.4, 0.3)},
                                               {'a': d / 2, 'b': d, 'face': None}])
    p = production(video, preuve)
    res = timeline.verifier(p, exiger_narration=True)
    out = tmp_path / 'final.mp4'
    info, _ = render.rendre(p, res, out, mode='final')
    assert render.controle_sortie(info, res['duree_totale']) == []
    assert out.with_suffix('.srt').exists()
