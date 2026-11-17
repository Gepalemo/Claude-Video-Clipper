# Audit du projet d'origine : licence, dépendances, sécurité

Projet examiné : *Claude Clipping Tool* (`Plextrang/Claude-Video-Clipper`, copie dans ce dépôt).
Audité le 17/11/2026 avant de construire le pipeline `studio/`.

## 1. Licence

| Élément | Licence | Utilisable ? |
|---|---|---|
| Code Python (`clipper/`, `run.py`, `install.py`) | MIT | **Oui.** Il faut conserver l'avis de copyright (`LICENSE`). |
| Police Montserrat (`assets/fonts/`) | SIL OFL 1.1 | **Oui** (incrustation dans les vidéos autorisée). |
| Détecteur de visages YuNet (`assets/models/`) | MIT (OpenCV Zoo) | **Oui.** |
| Effets sonores (`assets/sfx/*.mp3`, `click.wav`) | **Non documentée** : ni origine ni licence dans `assets/sfx/README.md` | **Non.** Exclus du pipeline : on ne peut pas prouver les droits. |
| Moteur Remotion (`remotion/`) | Licence Remotion : gratuite pour les particuliers et petites structures, payante au-delà | **Non.** Exclu (licence conditionnelle, voir aussi §3). |
| faster-whisper / CTranslate2 | MIT | Oui |
| Modèles Whisper (téléchargés depuis Hugging Face) | MIT (OpenAI) | Oui |
| OpenCV | Apache 2.0 | Oui |
| FFmpeg (binaire installé à part) | LGPL/GPL selon la compilation | Oui pour l'usage (on l'appelle en ligne de commande, sans le redistribuer) |
| yt-dlp | Unlicense | Pas utilisé par `studio/` (voir §4) |

## 2. Dépendances

`requirements.txt` d'origine : `yt-dlp[default]>=2025.10.0`, `faster-whisper>=1.1.0`, `soundfile>=0.12`,
`numpy>=1.26`, `opencv-python>=4.10`. Ce sont des bornes inférieures seulement, sans borne supérieure ni épinglage.

- `pip-audit` sur l'environnement installé (versions du 17/11/2026) : **aucune vulnérabilité connue**.
- `npm audit` sur `remotion/package-lock.json` : **11 vulnérabilités (10 élevées, 1 modérée)**, dans
  `zod` (épuisement mémoire), `fast-uri` (usurpation de schéma d'URI) et la chaîne `@remotion/*` qui en dépend.
- Au premier usage, le modèle Whisper est téléchargé depuis `huggingface.co`. Ensuite tout fonctionne hors ligne.

## 3. Sécurité du code

| Constat | Gravité | Traitement dans `studio/` |
|---|---|---|
| `subprocess.run(..., shell=True)` sous Windows pour `npx remotion` et `npm install` | Moyenne (l'interpréteur de commandes analyse les arguments) | Remotion n'est pas utilisé. `studio/` n'appelle jamais `shell=True` : toutes les commandes passent par des listes d'arguments. |
| `install.py` lance `pip install -U yt-dlp` à chaque installation (dernière version, non vérifiée) | Faible à moyenne (chaîne d'approvisionnement) | `requirements-studio.txt` sans yt-dlp, avec des bornes supérieures. Faites `pip-audit` régulièrement (`requirements-dev.txt`). |
| `--cookies-from-browser` lit les cookies du navigateur | Moyenne (données de session) | Pas de téléchargement dans `studio/` : sources locales uniquement. |
| Sous-titres ASS : seules `{` et `}` sont neutralisées, pas `\` (une séquence `\N` ou `\h` passe) | Faible | Le texte des sous-titres est assaini avant `write_ass` (`\` remplacé, accolades neutralisées). |
| Les fichiers MP4 produits gardent les métadonnées de la source | Faible (vie privée) | Export avec `-map_metadata -1 -map_chapters -1`. |
| Lecture/écriture JSON sans `pickle` ni `eval` | Aucune | Écritures atomiques (fichier temporaire puis renommage). |
| Le skill `clip-video` demande d'enchaîner les étapes « sans attendre de validation » | Contraire à l'exigence de validation humaine | Le nouveau skill `produce-short` impose les points de validation, et `CLAUDE.md` est mis à jour en conséquence. |

## 4. Ce qui est réutilisé, et ce qui ne l'est pas

Réutilisé tel quel, via des imports :
- `clipper.fetch.transcribe` / `sentences` : transcription faster-whisper avec un horodatage par mot ;
- `clipper.reframe` : détection des plans, visage YuNet, recadrage 9:16 fixe par plan, mise en page « fit » sur fond flou ;
- `clipper.cut.snap_range` / `boundary_warnings` : coupes sur des mots entiers, alertes en cas de coupe au milieu d'une phrase ;
- `clipper.plan.caption_groups` + `clipper.edit.write_ass` : sous-titres mot à mot.

Non réutilisé :
- **yt-dlp et le téléchargement d'URL**. Le pipeline importe uniquement des fichiers locaux dont vous détenez les droits. Retélécharger depuis une plateforme pose deux problèmes : les conditions d'utilisation des plateformes, et l'absence de garantie sur l'original.
- **Remotion** (licence et vulnérabilités, voir plus haut) et les **effets sonores** (licence inconnue).
- Les zooms automatiques de `clipper.plan`, inutiles pour un format commentaire/analyse.
