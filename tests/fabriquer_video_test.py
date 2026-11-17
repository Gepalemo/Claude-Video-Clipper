"""Fabrique une vidéo de test 16:9 dont nous détenons TOUS les droits (texte original écrit pour
ce dépôt, voix de synthèse locale espeak-ng, visuels générés par FFmpeg, police OFL).

    python tests/fabriquer_video_test.py <dossier_sortie>

Produit conference_test.mp4 (~2 min 30, 1920x1080, parole française) + attestation.txt.
"""
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FONT = ROOT / 'assets' / 'fonts' / 'Montserrat-ExtraBold.ttf'

DIAPOS = [
    ('Le cycle de l\'eau', '#1d3557',
     "Bonjour et bienvenue. Aujourd'hui, je vais vous parler du cycle de l'eau. C'est un sujet que tout le monde "
     "croit connaître. Pourtant, il cache plusieurs idées reçues. Pourquoi l'eau de pluie n'est-elle pas salée, "
     "alors qu'elle vient en grande partie des océans ?"),
    ('L\'évaporation', '#457b9d',
     "Tout commence par l'évaporation. Le soleil chauffe la surface des océans. L'eau passe à l'état de vapeur, "
     "mais le sel, lui, reste dans la mer. Voilà pourquoi la pluie est douce. Environ quatre-vingt-six pour cent "
     "de l'évaporation mondiale vient des océans."),
    ('Les nuages', '#2a9d8f',
     "Ensuite, la vapeur monte et se refroidit. Elle se condense autour de minuscules poussières. C'est ainsi que "
     "naissent les nuages. Un nuage ordinaire peut peser plusieurs centaines de tonnes. Il flotte pourtant, "
     "parce que ses gouttelettes sont très petites et très dispersées."),
    ('Les précipitations', '#e9c46a',
     "Quand les gouttelettes grossissent, elles tombent. C'est la pluie, la neige ou la grêle. Une grande partie "
     "retombe directement dans les océans. Le reste arrose les continents, remplit les rivières, et s'infiltre "
     "dans le sol."),
    ('Les nappes souterraines', '#f4a261',
     "Voici le point le plus méconnu. L'eau qui s'infiltre peut rester sous terre pendant des siècles. Les nappes "
     "souterraines contiennent bien plus d'eau douce liquide que tous les lacs et rivières réunis. C'est une "
     "réserve immense, mais fragile, car elle se renouvelle lentement."),
    ('Ce qu\'il faut retenir', '#e76f51',
     "Pour résumer, le cycle de l'eau est une grande machine solaire. Le soleil évapore, l'air transporte, le "
     "froid condense, et la gravité ramène l'eau vers le sol. La prochaine fois qu'il pleut, pensez au long "
     "voyage de chaque goutte. Merci de m'avoir écouté."),
]


def dur(path):
    r = subprocess.run(['ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of', 'csv=p=0', str(path)],
                       capture_output=True, text=True, check=True)
    return float(r.stdout.strip())


def main(out_dir):
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    sys.path.insert(0, str(ROOT))
    from studio.narration import synthese_locale
    work = out / 'fabrication'
    work.mkdir(exist_ok=True)
    shutil.copy2(FONT, work / 'font.ttf')
    parts = []
    for k, (titre, couleur, texte) in enumerate(DIAPOS):
        wav = work / f'p{k}.wav'
        synthese_locale(texte, wav, 'fr', vitesse=150)
        d = dur(wav) + 0.8
        (work / f't{k}.txt').write_text(titre, encoding='utf-8')
        mp4 = work / f'p{k}.mp4'
        vf = (f"drawtext=fontfile=font.ttf:textfile=t{k}.txt:fontsize=96:fontcolor=white:x=(w-tw)/2:y=(h-th)/2-80,"
              f"drawtext=fontfile=font.ttf:text='Conférence de test':fontsize=40:fontcolor=white@0.8:"
              f"x=(w-tw)/2:y=h*0.62,drawbox=x=0:y=ih-24:w=iw*t/{d:.2f}:h=24:color=white@0.6:t=fill")
        subprocess.run(['ffmpeg', '-y', '-v', 'error', '-f', 'lavfi', '-i',
                        f'color=c={couleur}:s=1920x1080:r=30:d={d:.2f}', '-i', wav.name, '-vf', vf, '-af', 'apad',
                        '-t', f'{d:.2f}', '-c:v', 'libx264', '-preset', 'veryfast', '-pix_fmt', 'yuv420p',
                        '-c:a', 'aac', '-ar', '48000', '-ac', '2', mp4.name], check=True, cwd=work)
        parts.append(mp4.name)
    (work / 'liste.txt').write_text(''.join(f"file '{p}'\n" for p in parts), encoding='utf-8')
    final = out / 'conference_test.mp4'
    subprocess.run(['ffmpeg', '-y', '-v', 'error', '-f', 'concat', '-safe', '0', '-i', 'liste.txt', '-c', 'copy',
                    str(final.resolve())], check=True, cwd=work)
    (out / 'attestation.txt').write_text(
        "ATTESTATION DE DROITS - vidéo de test\n"
        "Fichier : conference_test.mp4\n"
        "Texte : écrit spécialement pour ce dépôt (tests/fabriquer_video_test.py), aucun tiers.\n"
        "Voix : synthèse vocale locale (espeak-ng ou Windows SAPI), générée sur la machine.\n"
        "Visuels : générés par FFmpeg (aplats de couleur + texte). Police Montserrat (SIL OFL 1.1).\n"
        "Droits : le propriétaire du dépôt détient tous les droits d'utilisation, de modification et de diffusion.\n",
        encoding='utf-8')
    shutil.rmtree(work, ignore_errors=True)
    print(f'{final}  ({dur(final):.1f} s)')


if __name__ == '__main__':
    main(sys.argv[1] if len(sys.argv) > 1 else 'output/_test')
