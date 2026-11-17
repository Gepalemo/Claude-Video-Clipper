"""Ajout de VOTRE narration : un fichier audio par bloc de narration du montage.

Le fichier est converti en WAV 48 kHz mono, débarrassé des silences de début/fin, puis transcrit
(Whisper) pour caler les sous-titres mot à mot. Une voix de synthèse (--tts-test) est réservée
aux essais : elle est marquée « synthétique » et l'export l'exige déclaré à la validation.
"""
import os
import shutil
import subprocess
from pathlib import Path

from . import config
from .core import StudioError, ffmpeg, now, probe, save_json, sha256_file
from .transcribe import whisper_narration

AUDIO_EXT = {'.wav', '.mp3', '.m4a', '.aac', '.flac', '.ogg', '.opus', '.wma', '.mp4', '.mov', '.webm'}


def _narr_ids(montage):
    return [s['id'] for s in montage['segments'] if s['type'] == 'narration']


def ajouter(prod, bloc, fichier, synthetique=False, modele=None, garder_silences=False):
    montage = prod.montage()
    if bloc not in _narr_ids(montage):
        raise StudioError(f"bloc inconnu : {bloc} (blocs de narration : {', '.join(_narr_ids(montage))})")
    src = Path(fichier).expanduser().resolve()
    if not src.is_file() or src.suffix.lower() not in AUDIO_EXT:
        raise StudioError(f'fichier audio introuvable ou format non pris en charge : {src}')
    if not probe(src)['audio']:
        raise StudioError('ce fichier ne contient pas de piste audio')
    dst = prod.path('narration', f'{bloc}.wav')
    trim = [] if garder_silences else [
        '-af', 'silenceremove=start_periods=1:start_threshold=-45dB:start_silence=0.08,'
               'areverse,silenceremove=start_periods=1:start_threshold=-45dB:start_silence=0.15,areverse']
    ffmpeg('-i', src, '-vn', '-ac', '1', '-ar', '48000', *trim, '-c:a', 'pcm_s16le', dst)
    dur = probe(dst)['duree']
    if dur < 0.5:
        raise StudioError('narration vide ou quasi silencieuse après nettoyage')
    texte = next(s['texte'] for s in montage['segments'] if s['id'] == bloc)
    tmpwav = prod.path('.travail', f'narr_{bloc}_16k.wav')
    tmpwav.unlink(missing_ok=True)
    words, lang = whisper_narration(dst, tmpwav, texte, modele or config.WHISPER_MODELE,
                                    prod.state.get('langue') or 'auto')
    Path(prod.path('.travail', f'narr_{bloc}_16k.wav')).unlink(missing_ok=True)
    save_json(prod.path('narration', f'{bloc}.mots.json'), words)
    rec = {'bloc': bloc, 'fichier': f'narration/{bloc}.wav', 'origine': src.name, 'duree': round(dur, 3),
           'sha256': sha256_file(dst), 'synthetique': bool(synthetique), 'ajoute_le': now(),
           'transcription': ' '.join(w['w'] for w in words)}
    prod.state['narration'][bloc] = rec
    prod.save()
    if all(b in prod.state['narration'] for b in _narr_ids(montage)):
        prod.set_statut('narration')
    prod.log('narration_ajoutee', bloc=bloc, duree=rec['duree'], sha256=rec['sha256'], synthetique=rec['synthetique'])
    return rec


def synthese_locale(texte, dst, langue='fr', vitesse=165):
    """Voix de synthèse LOCALE (tests uniquement) : espeak-ng, sinon la synthèse vocale de Windows."""
    exe = shutil.which('espeak-ng') or shutil.which('espeak')
    if exe:
        subprocess.run([exe, '-v', langue[:2], '-s', str(vitesse), '-w', str(dst), texte], check=True,
                       capture_output=True)
    elif os.name == 'nt':
        # le texte passe par une variable d'environnement : aucune injection dans la commande PowerShell
        ps = ("Add-Type -AssemblyName System.Speech; $s = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
              "try { $s.SelectVoiceByHints('NotSet', 'NotSet', 0, [Globalization.CultureInfo]$env:STUDIO_TTS_LANG) } "
              "catch {}; $s.SetOutputToWaveFile($env:STUDIO_TTS_OUT); $s.Speak($env:STUDIO_TTS_TEXT); $s.Dispose()")
        env = dict(os.environ, STUDIO_TTS_TEXT=texte, STUDIO_TTS_OUT=str(dst),
                   STUDIO_TTS_LANG={'fr': 'fr-FR', 'en': 'en-US'}.get(langue[:2], 'fr-FR'))
        subprocess.run(['powershell', '-NoProfile', '-NonInteractive', '-Command', ps], check=True, env=env,
                       capture_output=True)
    else:
        raise StudioError('aucune synthèse vocale locale trouvée (installez espeak-ng)')
    return dst


def tts_test_tous(prod):
    montage = prod.montage()
    for s in montage['segments']:
        if s['type'] != 'narration':
            continue
        if '[À ÉCRIRE' in s['texte']:
            raise StudioError(f"le bloc {s['id']} contient encore une trame [À ÉCRIRE ...] : écrivez le texte d'abord")
        wav = prod.path('.travail', f"tts_{s['id']}.wav")
        synthese_locale(s['texte'], wav, prod.state.get('langue') or 'fr')
        ajouter(prod, s['id'], wav, synthetique=True)
        print(f"   ok {s['id']} (voix de synthèse de test)")
