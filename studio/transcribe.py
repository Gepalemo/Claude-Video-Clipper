"""Transcription locale avec faster-whisper (réutilise clipper.fetch : audio 16 kHz, horodatage par mot)."""
import time
from pathlib import Path

from . import config
from .core import StudioError, ffmpeg, load_json, save_json


def _wav16k(src, dst):
    if not Path(dst).exists():
        ffmpeg('-i', src, '-vn', '-ac', '1', '-ar', '16000', '-c:a', 'pcm_s16le', dst)
    return Path(dst)


def whisper_mots(audio_path, wav_path, modele, langue, device='cpu'):
    """Transcrit un fichier audio/vidéo. Retourne (mots, langue). mots = [{'w','s','e','p'}]."""
    try:
        from clipper.fetch import transcribe
    except ImportError as e:  # faster-whisper absent
        raise StudioError(f'faster-whisper non installé ({e}). Lancez : python install.py')
    wav = _wav16k(audio_path, wav_path)
    try:
        return transcribe(wav, modele, langue, device)
    except Exception as e:  # réseau (1er téléchargement du modèle), mémoire, etc.
        raise StudioError(f'transcription impossible : {e}\n'
                          "Le premier passage télécharge le modèle Whisper depuis huggingface.co (une seule fois).")


_MODELES = {}


def whisper_narration(audio_path, wav_path, texte, modele, langue, device='cpu'):
    """Transcription d'une narration courte : sans traitement par lots ni filtre VAD (qui peuvent
    « halluciner » sur un bloc court), avec le texte écrit en contexte pour fiabiliser le vocabulaire."""
    import os
    import soundfile as sf
    try:
        from faster_whisper import WhisperModel
    except ImportError as e:
        raise StudioError(f'faster-whisper non installé ({e}). Lancez : python install.py')
    wav = _wav16k(audio_path, wav_path)
    audio, _ = sf.read(str(wav), dtype='float32')
    key = (modele, device)
    try:
        if key not in _MODELES:
            _MODELES[key] = WhisperModel(modele, device=device, compute_type='int8' if device == 'cpu' else 'float16',
                                         cpu_threads=max(1, (os.cpu_count() or 4) - 1))
        segs, info = _MODELES[key].transcribe(audio, language=None if langue in (None, 'auto') else langue,
                                              beam_size=5, word_timestamps=True, vad_filter=False,
                                              condition_on_previous_text=False,
                                              initial_prompt=(texte or '')[:800] or None)
        words = [{'w': w.word.strip(), 's': round(w.start, 3), 'e': round(w.end, 3), 'p': round(w.probability, 3)}
                 for seg in segs for w in (seg.words or []) if w.word.strip()]
    except Exception as e:
        raise StudioError(f'transcription de la narration impossible : {e}')
    return words, info.language


def transcrire_sources(prod, modele=None, langue=None, device='cpu', refaire=False):
    from clipper.fetch import sentences
    modele = modele or config.WHISPER_MODELE
    langue = langue or prod.state.get('langue') or config.WHISPER_LANGUE
    faits = []
    for sid, src in prod.state['sources'].items():
        tdir = prod.path('transcriptions', sid)
        words_f = tdir / 'mots.json'
        meta = load_json(tdir / 'meta.json', {})
        if words_f.exists() and meta.get('sha256') == src['sha256'] and not refaire:
            print(f'-> {sid} : transcription déjà faite')
            continue
        t0 = time.time()
        print(f'-> {sid} : transcription de {src["nom"]} ({src["duree"]:.0f} s) ...')
        words, lang = whisper_mots(src['fichier'], prod.path('.travail', f'{sid}_16k.wav'), modele, langue, device)
        if not words:
            raise StudioError(f'{sid} : aucune parole détectée')
        lines = sentences(words)
        save_json(words_f, words)
        save_json(tdir / 'phrases.json', lines)
        txt = [f"[{l['s']:.2f}-{l['e']:.2f}] {l['text']}" for l in lines]
        (tdir / 'transcription.txt').write_text('\n'.join(txt) + '\n', encoding='utf-8')
        save_json(tdir / 'meta.json', {'sha256': src['sha256'], 'modele': modele, 'langue': lang,
                                       'mots': len(words), 'duree_calcul_s': round(time.time() - t0)})
        prod.state['langue'] = lang
        prod.save()
        prod.log('transcription', source=sid, modele=modele, langue=lang, mots=len(words))
        print(f'   ok : {len(words)} mots, langue {lang}, {time.time() - t0:.0f} s')
        faits.append(sid)
    prod.set_statut('transcrit')
    return faits


def mots_source(prod, sid):
    w = load_json(prod.path('transcriptions', sid, 'mots.json'))
    if w is None:
        raise StudioError(f'{sid} non transcrit : lancez  prod transcrire {prod.id}')
    return w
