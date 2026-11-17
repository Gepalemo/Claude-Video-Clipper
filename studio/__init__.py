"""Studio : pipeline local de production de vidéos verticales originales (65-100 s, 1080x1920).

Flux : nouveau -> source (+ justificatifs de licence) -> transcrire -> passages -> script
-> narration -> verifier -> apercu -> valider (humain, obligatoire) -> exporter -> resultats.

Réutilise du projet d'origine (MIT) : la transcription faster-whisper (clipper.fetch), le
recadrage 9:16 par plan et par visage (clipper.reframe), l'alignement des coupes sur les mots
(clipper.cut.snap_range) et les sous-titres mot à mot (clipper.plan / clipper.edit.write_ass).
N'utilise pas : yt-dlp (sources locales uniquement), Remotion (licence + vulnérabilités npm),
les effets sonores fournis (licence non documentée).
"""
