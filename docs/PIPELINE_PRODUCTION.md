# Pipeline de production de vidéos verticales originales

Vidéos de **65 à 100 s**, en **1080x1920**, sans filigrane, pour TikTok, YouTube Shorts, Instagram Reels et
Facebook Reels. Le format : un **commentaire original** (votre voix) intercalé avec de **courts extraits**
de sources dont vous détenez les droits.

Tout tourne en local et gratuitement (Whisper, FFmpeg, OpenCV), sans aucune API payante. **La publication
reste manuelle.**

## Installation sous Windows (une fois)

```powershell
winget install -e --id Python.Python.3.12        # cochez « Add Python to PATH » si on vous le demande
winget install -e --id Gyan.FFmpeg
# fermez puis rouvrez le terminal
git clone https://github.com/gepalemo/claude-video-clipper.git
cd claude-video-clipper
python install.py --studio        # ou --dev pour avoir aussi les tests
```

Au premier lancement de la transcription, le modèle Whisper `small` (~500 Mo) est téléchargé une fois.
Avec une carte NVIDIA, ajoutez `--device cuda` à `prod transcrire`.

## Le flux, étape par étape

```text
nouveau ─► source (+ justificatifs) ─► transcrire ─► passages ─► script ─► [vous écrivez]
   ─► narration (votre voix) ─► verifier ─► apercu ─► [VOUS visionnez] ─► valider (humain)
   ─► exporter ─► [VOUS publiez] ─► resultats
```

| # | Commande | Ce qu'elle fait |
|---|---|---|
| 1 | `python run.py prod nouveau "Mon sujet"` | Crée `output/AAAAMMJJ-mon-sujet/` |
| 2 | `python run.py prod source <prod> C:\videos\src.mp4 --licence proprietaire --titulaire "Moi" --preuve C:\droits\contrat.pdf` | Enregistre la source, sa licence, les justificatifs (copiés) et les empreintes SHA-256 |
| 3 | `python run.py prod transcrire <prod> --langue fr` | Transcription Whisper locale, avec un horodatage par mot |
| 4 | `python run.py prod passages <prod> --mots-cles "pluie,océan"` | Propose les passages utiles (8 à 25 s), notés et sans chevauchement |
| 5 | `python run.py prod script <prod> --passages p1,p3,p5 --titre "..."` | Crée `montage.json` et `script_narration.txt` : une trame de commentaire à compléter |
| 6 | *vous* | Remplacez chaque `[À ÉCRIRE ...]` de `montage.json` par **votre** commentaire |
| 7 | `python run.py prod narration <prod> intro C:\audio\intro.wav` (une fois par bloc) | Importe votre voix : nettoyage des silences, transcription, calage des sous-titres sur votre texte |
| 8 | `python run.py prod verifier <prod>` | Contrôle durée, originalité, droits, intégrité ; liste les affirmations à vérifier |
| 9 | `python run.py prod apercu <prod>` | Rend l'aperçu avec le filigrane « APERÇU — NON VALIDÉ » |
| 10 | `python run.py prod valider <prod>` | **Validation humaine obligatoire** (sources, faits, montage, droits) |
| 11 | `python run.py prod exporter <prod>` | Export final sans filigrane, contrôle technique, métadonnées, lignes ajoutées au suivi CSV |
| 12 | `python run.py prod resultats <prod> --plateforme tiktok --url ... --vues 1520 --likes 96` | Met à jour le suivi des résultats |

Autres commandes : `prod statut [<prod>]`, `prod journal [<prod>]`, `prod suivi`, `prod apercu <prod> --structure`
(aperçu sans narration pour caler le montage), `prod script ... --ollama llama3.1` (brouillon rédigé par un LLM
local gratuit via [Ollama](https://ollama.com), à relire).

### Types de licence acceptés (`--licence`)

| Type | Exigences |
|---|---|
| `proprietaire` | `--preuve` (rushes, projet, facture...) ou `--declaration "J'ai filmé..."` |
| `licence` (accord d'un tiers) | `--preuve` **obligatoire** + `--modif-autorisee`, et `--commercial-autorise` si vous monétisez. Facultatif : `--plateformes`, `--expiration` |
| `cc-by`, `cc-by-sa` | `--attribution "« Titre » par Auteur, CC BY 4.0, lien"` obligatoire, `--url` conseillé |
| `cc0`, `domaine-public` | `--preuve` (capture de la page de licence) |
| `cc-by-nc*` | Refusé, sauf `--non-commercial-assume` (aucune monétisation) |
| `cc-by-nd*` | **Refusé** : la modification est interdite |

### `montage.json` : la seule source de vérité du montage

```json
{
  "titre": "Pourquoi la pluie n'est pas salée ?",
  "accroche": "La réponse en 90 secondes.",
  "hashtags": ["#Science", "#Vulgarisation"],
  "mots_cles": ["évaporation", "océans"],
  "corrections_sous_titres": {"des bouchers": "des océans"},
  "sous_titres": {"accent": "#FFD60A", "y": 1250, "majuscules": true, "credit_a_l_ecran": true},
  "segments": [
    {"id": "intro", "type": "narration", "texte": "Votre accroche...", "visuel": "auto"},
    {"id": "extrait1", "type": "extrait", "source": "src1", "debut": 11.7, "fin": 29.5},
    {"id": "analyse1", "type": "narration", "texte": "...", "visuel": {"source": "src1", "debut": 40}},
    {"id": "conclusion", "type": "narration", "texte": "...", "visuel": "auto"}
  ]
}
```

- Pendant une narration, l'image montre un plan muet de la source. Avec `"auto"`, c'est le passage qui
  précède l'extrait suivant (pour la continuité) ; sinon, indiquez `{"source", "debut"}`.
- `corrections_sous_titres` corrige les erreurs de Whisper dans les extraits, groupes de mots compris.
- Pour les narrations, les sous-titres affichent **votre texte écrit**, calé sur les temps de votre voix.
  Si vous vous écartez du texte (similarité < 60 %), la transcription réelle est utilisée et un avertissement s'affiche.

## Contrôles automatiques

| Contrôle | Effet |
|---|---|
| Durée totale hors de 65-100 s | **Bloque** l'aperçu et l'export |
| Texte `[À ÉCRIRE ...]` restant, ou narration non enregistrée | **Bloque** |
| Licence incomplète (preuve, attribution, modification non autorisée, ND) | **Bloque** |
| Source, justificatif, `licence.json` ou narration modifiés depuis l'import (SHA-256) | **Bloque** |
| Commentaire original < 35 % de la durée | Avertissement (risque de « contenu réutilisé ») |
| Extrait > 30 s, ou coupe en milieu de phrase | Avertissement |
| Voix de synthèse | Avertissement + étiquette IA dans les métadonnées + question à la validation |
| Fichier exporté : 1080x1920, h264/yuv420p, AAC, 30 i/s, durée | **Bloque** si non conforme (fichier renommé `.REJETE.mp4`) |

## Validation humaine (obligatoire)

`prod valider` refuse de fonctionner hors d'un terminal interactif. Il demande :

- **Sources** : pour chaque source, le justificatif a été relu et couvre ce fichier, ce montage et ces plateformes ; les extraits viennent des originaux.
- **Faits** : chaque affirmation détectée (chiffres, dates, superlatifs, noms propres, « selon... ») est
  confirmée avec sa **référence**, puis vous attestez qu'aucune autre affirmation non vérifiée ne figure.
- **Montage** : aperçu visionné en entier, rien sorti de son contexte, sous-titres fidèles, cadrage, commentaire original, pas d'atteinte aux personnes.
- **Droits** : votre voix (ou voix de synthèse déclarée), pas de musique ni de logo non couverts, consentement des personnes, crédits, règles des plateformes.

La validation est **liée à l'empreinte** du montage, des sources, des licences, des justificatifs, des narrations et de l'aperçu.
Si l'un d'eux change ensuite, l'export est refusé et il faut refaire l'aperçu puis la validation.
Chaque validation est archivée (`validation_NN.json`).

## Où sont les fichiers

```text
output/<prod>/
  production.json            état, sources, narrations (empreintes)
  droits/srcN/licence.json   licence + preuves/ (copies des justificatifs)
  transcriptions/srcN/       mots.json, phrases.json, transcription.txt
  passages.json  montage.json  script_narration.txt
  narration/<bloc>.wav       votre voix normalisée (+ .mots.json)
  apercu/apercu.mp4 (+ .srt, apercu.json)
  validation.json            dernière validation (+ validation_NN.json, l'historique)
  export/<prod>_<titre>_1080x1920.mp4 (+ .srt), metadonnees.md/.json, export.json
output/_registre/
  journal_productions.jsonl  journal de toutes les actions (horodatage, utilisateur, empreintes)
  suivi_resultats.csv        une ligne par vidéo et par plateforme (« ; », UTF-8, s'ouvre dans Excel)
```

`output/` n'est jamais versionné (`.gitignore`). Sauvegardez `output/_registre/` et les dossiers `droits/`.

## Tests

```powershell
python install.py --dev
.venv\Scripts\python -m pytest tests                     # 21 tests automatisés (~2 min)
.venv\Scripts\python tests\fabriquer_video_test.py output\_test   # vidéo de test libre de droits
```

`fabriquer_video_test.py` crée une fausse conférence de 2 minutes (texte écrit pour le dépôt, voix
synthétique locale, visuels FFmpeg), avec son `attestation.txt`, pour dérouler le flux complet sans aucun droit de tiers.

## Avant une production en série

1. Faites **une** production complète avec une vraie source et **votre** voix. Vérifiez la qualité de
   transcription : le modèle `small` suffit en général, `medium` est plus précis mais plus lent.
2. Réglez dans `studio/config.py` : position et taille des sous-titres (zones d'interface des
   plateformes), part minimale de commentaire, durées.
3. Publiez à la main, saisissez les résultats après 48 h et 7 jours (`prod resultats`), et comparez dans le CSV.
4. Seulement ensuite, envisagez d'automatiser davantage. La validation humaine reste obligatoire.
