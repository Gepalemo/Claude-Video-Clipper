"""Outils partagés : état de production, empreintes SHA-256, journal, ffmpeg."""
import datetime as dt
import getpass
import hashlib
import json
import re
import shutil
import subprocess
import unicodedata
from pathlib import Path

from . import config


class StudioError(Exception):
    """Erreur affichable à l'utilisateur (sans trace Python)."""


def now():
    return dt.datetime.now().astimezone().isoformat(timespec='seconds')


def slug(text, maxlen=50):
    text = unicodedata.normalize('NFKD', str(text)).encode('ascii', 'ignore').decode()
    text = re.sub(r'[^\w\s-]', '', text).strip().lower()
    text = re.sub(r'[\s_-]+', '-', text)
    return text[:maxlen].strip('-') or 'production'


def load_json(path, default=None):
    path = Path(path)
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding='utf-8'))


def save_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + '.tmp')
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding='utf-8')
    tmp.replace(path)


def sha256_file(path, chunk=1 << 20):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        while True:
            b = f.read(chunk)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


def sha256_json(data):
    return hashlib.sha256(json.dumps(data, sort_keys=True, ensure_ascii=False).encode('utf-8')).hexdigest()


def utilisateur():
    try:
        return getpass.getuser()
    except Exception:
        return 'inconnu'


# ---------------- journal ----------------

def journal(action, production=None, **details):
    """Ajoute une ligne au journal des productions (JSON Lines, une action par ligne)."""
    config.REGISTRE.mkdir(parents=True, exist_ok=True)
    entry = {'horodatage': now(), 'utilisateur': utilisateur(), 'production': production,
             'action': action, **details}
    with open(config.JOURNAL, 'a', encoding='utf-8') as f:
        f.write(json.dumps(entry, ensure_ascii=False) + '\n')
    return entry


def lire_journal(production=None):
    if not config.JOURNAL.exists():
        return []
    out = []
    for line in config.JOURNAL.read_text(encoding='utf-8').splitlines():
        if line.strip():
            e = json.loads(line)
            if production is None or e.get('production') == production:
                out.append(e)
    return out


# ---------------- production ----------------

STATUTS = ['brouillon', 'sources', 'transcrit', 'script', 'narration', 'apercu', 'valide', 'exporte']


class Production:
    """Un dossier output/<id>/ avec production.json (état) et ses sous-dossiers."""

    def __init__(self, pid):
        self.id = pid
        self.dir = config.OUTPUT / pid
        if not (self.dir / 'production.json').exists():
            raise StudioError(f'production introuvable : {pid} (dossier {config.OUTPUT})')
        self.state = load_json(self.dir / 'production.json')

    @classmethod
    def create(cls, nom):
        pid = f"{dt.date.today():%Y%m%d}-{slug(nom, 40)}"
        d = config.OUTPUT / pid
        if (d / 'production.json').exists():
            raise StudioError(f'la production {pid} existe déjà')
        for sub in ('sources', 'droits', 'transcriptions', 'narration', 'apercu', 'export', '.travail'):
            (d / sub).mkdir(parents=True, exist_ok=True)
        save_json(d / 'production.json', {'id': pid, 'nom': nom, 'cree_le': now(), 'statut': 'brouillon',
                                         'sources': {}, 'narration': {}, 'historique_statut': []})
        return cls(pid)

    # --- chemins
    def path(self, *parts):
        return self.dir.joinpath(*parts)

    @property
    def montage_path(self):
        return self.path('montage.json')

    def montage(self, required=True):
        m = load_json(self.montage_path)
        if m is None and required:
            raise StudioError('pas encore de montage.json : lancez  prod script ' + self.id)
        return m

    def save(self):
        save_json(self.path('production.json'), self.state)

    def set_statut(self, statut):
        if STATUTS.index(statut) >= STATUTS.index(self.state.get('statut', 'brouillon')) or statut in ('apercu', 'script'):
            self.state['statut'] = statut
        self.state.setdefault('historique_statut', []).append({'statut': statut, 'le': now()})
        self.save()

    def log(self, action, **details):
        return journal(action, self.id, **details)


# ---------------- ffmpeg ----------------

def need(tool):
    if not shutil.which(tool):
        raise StudioError(f'{tool} introuvable. Windows : winget install -e --id Gyan.FFmpeg '
                          '(puis ouvrez un NOUVEAU terminal)')


def run(cmd, cwd=None):
    r = subprocess.run([str(c) for c in cmd], capture_output=True, text=True, encoding='utf-8',
                       errors='replace', cwd=cwd)
    if r.returncode != 0:
        tail = '\n'.join((r.stderr or r.stdout).strip().splitlines()[-20:])
        raise StudioError(f'échec de {Path(str(cmd[0])).name} :\n{tail}')
    return r


def ffmpeg(*args, cwd=None):
    need('ffmpeg')
    return run(['ffmpeg', '-hide_banner', '-loglevel', 'error', '-y', *args], cwd=cwd)


def probe(path):
    need('ffprobe')
    r = run(['ffprobe', '-v', 'error', '-print_format', 'json', '-show_format', '-show_streams', str(path)])
    info = json.loads(r.stdout)
    v = next((s for s in info['streams'] if s['codec_type'] == 'video'), None)
    a = next((s for s in info['streams'] if s['codec_type'] == 'audio'), None)
    out = {'duree': float(info['format'].get('duration', 0) or 0), 'video': v is not None, 'audio': a is not None,
           'format': info['format'].get('format_name')}
    if v:
        num, den = (v.get('avg_frame_rate') or '30/1').split('/')
        rot = 0
        for sd in v.get('side_data_list', []) or []:
            rot = int(sd.get('rotation', 0) or 0)
        w, h = int(v['width']), int(v['height'])
        if abs(rot) in (90, 270):
            w, h = h, w
        out.update(largeur=w, hauteur=h, fps=float(num) / float(den) if float(den or 0) else 30.0,
                   codec_video=v.get('codec_name'), pix_fmt=v.get('pix_fmt'))
    if a:
        out.update(codec_audio=a.get('codec_name'), frequence=int(a.get('sample_rate', 0) or 0),
                   canaux=a.get('channels'))
    return out


def fmt_ts(t):
    m, s = divmod(max(0.0, float(t)), 60)
    return f'{int(m)}:{s:04.1f}'
