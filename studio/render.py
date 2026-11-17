"""Rendu 1080x1920 : chaque segment est recadré en 9:16 autour du visage (clipper.reframe),
les narrations sont posées sur un plan de la source (muet), puis tout est assemblé avec
sous-titres mot à mot (clipper.plan + clipper.edit.write_ass) et audio normalisé (-14 LUFS).

mode='apercu' : incruste « APERÇU — NON VALIDÉ » (empêche de publier un montage non validé).
mode='final'  : aucun filigrane, métadonnées du fichier supprimées.
"""
import shutil
import time
from pathlib import Path

from . import config
from .core import StudioError, ffmpeg, probe

W, H, FPS = config.W, config.H, config.FPS


def _video_chain(src, start, dur, label_in, label_out):
    """Chaîne de filtres : recadrage 9:16 plan par plan (visage), complétée si la source est trop courte."""
    from clipper.reframe import analyse_range, plan_shots, shot_filter
    shots = plan_shots(analyse_range(src['fichier'], start, dur, src['largeur'], src['hauteur']),
                       src['largeur'], src['hauteur'])
    chains = []
    if len(shots) == 1:
        chains.append(shot_filter(label_in, shots[0], src['largeur'], src['hauteur'], 'vr', FPS))
    else:
        sub = ''.join(f'[s{j}]' for j in range(len(shots)))
        chains.append(f'[{label_in}]split={len(shots)}{sub}')
        for j, sh in enumerate(shots):
            chains.append(shot_filter(f's{j}', sh, src['largeur'], src['hauteur'], f'v{j}', FPS))
        chains.append(''.join(f'[v{j}]' for j in range(len(shots))) + f'concat=n={len(shots)}:v=1:a=0[vr]')
    chains.append(f'[vr]tpad=stop_mode=clone:stop_duration={dur:.3f},trim=duration={dur:.3f},'
                  f'setpts=PTS-STARTPTS,fps={FPS},format=yuv420p[{label_out}]')
    return chains, shots


def _segment(prod, seg, out, preset):
    srcs = prod.state['sources']
    norm = f'loudnorm=I={config.LUFS_SEGMENT}:TP=-2:LRA=7,aresample=48000,aformat=sample_fmts=fltp:channel_layouts=stereo'
    if seg['type'] == 'extrait':
        src = srcs[seg['source']]
        start, dur = seg['debut'], seg['duree']
        inputs = ['-ss', f'{start:.3f}', '-t', f'{dur:.3f}', '-i', src['fichier']]
        chains, shots = _video_chain(src, start, dur, '0:v', 'v')
        chains.append(f'[0:a]aresample=48000,afade=t=in:d=0.02,afade=t=out:st={max(0, dur - 0.08):.3f}:d=0.08,'
                      f'{norm},apad,atrim=duration={dur:.3f}[a]')
    else:
        src = srcs[seg['visuel']['source']]
        start, dur = seg['visuel']['debut'], seg['duree']
        inputs = ['-ss', f'{start:.3f}', '-t', f'{dur:.3f}', '-i', src['fichier']]
        chains, shots = _video_chain(src, start, dur, '0:v', 'v')
        if seg['audio']:
            inputs += ['-i', str(prod.path(seg['audio']))]
            chains.append(f'[1:a]highpass=f=80,afade=t=in:d=0.02,afade=t=out:st={max(0, dur - 0.05):.3f}:d=0.05,'
                          f'{norm},apad,atrim=duration={dur:.3f}[a]')
        else:   # aperçu de structure sans narration : silence
            inputs += ['-f', 'lavfi', '-t', f'{dur:.3f}', '-i', 'anullsrc=r=48000:cl=stereo']
            chains.append(f'[1:a]atrim=duration={dur:.3f}[a]')
    ffmpeg(*inputs, '-filter_complex', ';'.join(chains), '-map', '[v]', '-map', '[a]',
           '-c:v', 'libx264', '-preset', preset, '-crf', '17', '-pix_fmt', 'yuv420p', '-r', str(FPS),
           '-c:a', 'aac', '-b:a', '192k', '-ar', '48000', '-ac', '2', '-t', f'{dur:.3f}', out)
    return shots


def _ass(prod, res, montage, path, apercu):
    """Sous-titres mot à mot (réutilise clipper.plan.caption_groups et clipper.edit.write_ass)."""
    from clipper import plan as planlib
    from clipper.edit import write_ass
    st = {**config.SOUS_TITRES, **{k: v for k, v in (montage.get('sous_titres') or {}).items()
                                    if k in ('accent', 'y', 'taille', 'majuscules')}}
    words = []
    for seg in res['timeline']:
        for w in seg['mots']:
            # ASS : neutralise les séquences de contrôle (\N, \h, {...})
            words.append({**w, 'w': w['w'].replace('\\', '/').replace('{', '(').replace('}', ')')})
    splices = [seg['t0'] for seg in res['timeline'][1:]]
    meta = {'words': words, 'duration': res['duree_totale'], 'splices': splices,
            'emphasis': montage.get('mots_cles', [])}
    caps = planlib.caption_groups(meta, upper=st['majuscules'])
    plan = {'fps': FPS, 'captions': caps,
            'caption_style': {'font': st['police'], 'font_file': st['fichier_police'], 'size': st['taille'],
                              'y': st['y'], 'outline': st['contour'], 'uppercase': st['majuscules']},
            'brand': {'text': st['texte'], 'accent': st['accent'], 'outline': st['contour_couleur']}}
    write_ass(plan, path)
    extra = []

    def ts(sec):
        cs = int(round(sec * 100))
        h, cs = divmod(cs, 360000)
        m, cs = divmod(cs, 6000)
        s, cs = divmod(cs, 100)
        return f'{h}:{m:02d}:{s:02d}.{cs:02d}'
    if (montage.get('sous_titres') or {}).get('credit_a_l_ecran', True):
        from .rights import licence
        for seg in res['timeline']:
            if seg['type'] != 'extrait':
                continue
            rec = licence(prod, seg['source'])
            txt = rec.get('attribution') or (f"Source : {rec['auteur']}" if rec['type'] != 'proprietaire' else '')
            if txt:
                txt = txt.replace('\\', '/').replace('{', '(').replace('}', ')')[:90]
                extra.append(f"Dialogue: 1,{ts(seg['t0'])},{ts(seg['t0'] + seg['duree'])},Cap,,0,0,0,,"
                             f"{{\\an8\\pos({W // 2},150)\\fs34\\bord3\\shad0}}{txt}")
    if apercu:
        extra.append(f"Dialogue: 2,{ts(0)},{ts(res['duree_totale'] + 1)},Cap,,0,0,0,,"
                     f"{{\\an5\\pos({W // 2},{H // 2 - 300})\\fs70\\bord4\\alpha&H70&\\frz20}}APERÇU — NON VALIDÉ")
    if extra:
        with open(path, 'a', encoding='utf-8') as f:
            f.write('\n'.join(extra) + '\n')
    return caps


def rendre(prod, res, out, mode='apercu'):
    if res['bloquants'] and mode == 'final':
        raise StudioError('rendu final impossible :\n  - ' + '\n  - '.join(res['bloquants']))
    montage = prod.montage()
    work = prod.path('.travail', f'rendu_{mode}')
    shutil.rmtree(work, ignore_errors=True)
    (work / 'fonts').mkdir(parents=True)
    # polices copiées dans le dossier de travail : chemins relatifs = pas de souci de « C: » sous Windows
    for f in config.FONTS.glob('*.ttf'):
        shutil.copy2(f, work / 'fonts' / f.name)
    preset = 'veryfast' if mode == 'apercu' else 'medium'
    t0 = time.time()
    lst = []
    for k, seg in enumerate(res['timeline']):
        name = f'seg{k:02d}.mp4'
        print(f"   segment {k + 1}/{len(res['timeline'])} : {seg['id']} ({seg['type']}, {seg['duree']:.1f} s)")
        _segment(prod, seg, work / name, preset)
        lst.append(f"file '{name}'")
    (work / 'liste.txt').write_text('\n'.join(lst) + '\n', encoding='utf-8')
    caps = _ass(prod, res, montage, work / 'sous_titres.ass', apercu=(mode == 'apercu'))
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_name(out.stem + '.part.mp4')
    ffmpeg('-f', 'concat', '-safe', '0', '-i', 'liste.txt',
           '-vf', 'ass=sous_titres.ass:fontsdir=fonts',
           '-af', f'loudnorm=I={config.LUFS_FINAL}:TP={config.TRUE_PEAK}:LRA=11,aresample=48000',
           '-c:v', 'libx264', '-preset', preset, '-crf', '18' if mode == 'final' else '21',
           '-profile:v', 'high', '-level', '4.1', '-maxrate', '12M', '-bufsize', '24M',
           '-pix_fmt', 'yuv420p', '-r', str(FPS), '-c:a', 'aac', '-b:a', '192k', '-ar', '48000', '-ac', '2',
           '-map_metadata', '-1', '-map_chapters', '-1', '-metadata', 'encoder=', '-movflags', '+faststart',
           str(tmp.resolve()), cwd=work)
    tmp.replace(out)
    _srt(caps, out.with_suffix('.srt'))
    info = probe(out)
    if mode == 'final':
        shutil.rmtree(work, ignore_errors=True)
    return info, round(time.time() - t0, 1)


def _srt(caps, path):
    def ts(t):
        ms = int(round(t * 1000))
        h, ms = divmod(ms, 3600000)
        m, ms = divmod(ms, 60000)
        s, ms = divmod(ms, 1000)
        return f'{h:02d}:{m:02d}:{s:02d},{ms:03d}'
    lines = []
    for i, g in enumerate(caps, 1):
        lines += [str(i), f"{ts(g['start'])} --> {ts(g['end'])}", ' '.join(w['text'] for w in g['words']), '']
    Path(path).write_text('\n'.join(lines), encoding='utf-8')


def controle_sortie(info, duree_attendue):
    """Contrôle technique du fichier exporté."""
    pb = []
    if (info.get('largeur'), info.get('hauteur')) != (W, H):
        pb.append(f"résolution {info.get('largeur')}x{info.get('hauteur')} au lieu de {W}x{H}")
    if not config.DUREE_MIN - 0.5 <= info['duree'] <= config.DUREE_MAX + 0.5:
        pb.append(f"durée {info['duree']:.1f} s hors cible")
    if abs(info['duree'] - duree_attendue) > 1.0:
        pb.append(f"durée {info['duree']:.1f} s différente du montage ({duree_attendue:.1f} s)")
    if info.get('codec_video') != 'h264' or info.get('pix_fmt') != 'yuv420p':
        pb.append(f"vidéo {info.get('codec_video')}/{info.get('pix_fmt')} au lieu de h264/yuv420p")
    if info.get('codec_audio') != 'aac':
        pb.append('piste audio AAC absente')
    if abs(info.get('fps', 0) - FPS) > 0.1:
        pb.append(f"cadence {info.get('fps')} i/s au lieu de {FPS}")
    return pb
