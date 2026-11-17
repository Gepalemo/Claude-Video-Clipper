# Claude Clipping Tool + pipeline de production originale

Ce dépôt contient deux outils :

1. **Pipeline de production originale (`studio/`, outil par défaut)** : vidéos verticales de 65 à 100 s
   avec commentaire original, à partir de sources dont l'utilisateur détient les droits. Pour toute demande de
   production, de montage, de commentaire, de narration ou de suivi des résultats, **utilisez le skill
   `produce-short`** (`.claude/skills/produce-short/SKILL.md`). **La validation humaine (`prod valider`) est
   obligatoire et doit être lancée par l'utilisateur lui-même : ne la lancez jamais à sa place.**
   Ne publiez jamais rien automatiquement. Guide : `docs/PIPELINE_PRODUCTION.md`. Audit : `docs/AUDIT.md`.
2. **Clipper d'origine (`clipper/`)** : découpe de clips bruts. Le skill `clip-video` s'applique seulement
   si l'utilisateur confirme détenir les droits de la vidéo. Montrez-lui alors la sélection de clips et attendez
   son accord avant de couper.

- Run everything through `python run.py <command>` from the repo root. Setup is `python install.py`
  (`python install.py --studio` for the production pipeline only, `--dev` for tests: `python -m pytest tests`).
- Results go to `output/<project>/` (gitignored). Never commit or upload user videos.
- Long steps (transcription, rendering) should run in the background, with a progress update to the user.
