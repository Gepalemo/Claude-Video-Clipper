---
name: produce-short
description: Produire une vidéo verticale ORIGINALE de 65-100 s (1080x1920) pour TikTok, YouTube Shorts, Instagram et Facebook à partir de sources dont l'utilisateur détient les droits, avec commentaire original, narration de l'utilisateur, sous-titres, validation humaine obligatoire, export, métadonnées et suivi CSV. À utiliser dès que l'utilisateur veut « produire », « monter », « commenter » une vidéo, ou parle de droits / licence / narration / suivi des résultats.
---

# Produire une vidéo originale

Guide complet : `docs/PIPELINE_PRODUCTION.md`. Toutes les commandes : `python run.py prod <commande>`.

## Règles absolues
1. **Ne lance JAMAIS `prod valider` à la place de l'utilisateur**, ne lui fournis jamais de réponses
   pré-remplies et ne définis jamais `STUDIO_TESTS`. La validation est un acte humain : demande-lui de la
   faire lui-même dans son terminal, après avoir visionné l'aperçu.
2. N'importe une source qu'avec une licence et un justificatif fournis par l'utilisateur. N'invente
   jamais un titulaire, une licence ou une attestation. Ne télécharge pas de vidéos depuis des plateformes.
3. Ne publie rien. Les métadonnées sont à copier-coller par l'utilisateur.
4. Le commentaire doit être une analyse originale. Si tu rédiges un brouillon de narration, présente-le comme
   un brouillon à réécrire ou valider par l'utilisateur, n'invente aucun fait et signale chaque chiffre à vérifier.
5. N'utilise une voix de synthèse (`--tts-test`) que pour tester, et dis-le clairement.

## Étapes
1. `prod nouveau "<sujet>"`, puis `prod source <prod> <fichier> --licence ... --titulaire ... --preuve ...`
   (demande à l'utilisateur les informations de licence qui manquent).
2. `prod transcrire <prod>` (en arrière-plan si la source est longue).
3. `prod passages <prod>` : présente les passages dans un tableau (id, durée, score, début du texte) et
   recommande 2 à 4 extraits courts qui laissent au moins 35 % de la durée au commentaire.
4. `prod script <prod> --passages ... --titre "..."`. Propose des textes de narration (accroche,
   analyses, conclusion) si l'utilisateur le souhaite, puis **attends qu'il les relise ou les réécrive** dans `montage.json`.
5. L'utilisateur enregistre sa voix (un fichier par bloc, texte dans `script_narration.txt`), puis
   `prod narration <prod> <bloc> <fichier>` pour chaque bloc.
6. `prod verifier <prod>`, corrige les points bloquants, puis `prod apercu <prod>`.
7. Demande à l'utilisateur de visionner l'aperçu puis de lancer **lui-même** `python run.py prod valider <prod>`.
8. Après validation approuvée : `prod exporter <prod>`. Donne le chemin du fichier et de `metadonnees.md`.
9. Plus tard : `prod resultats <prod> --plateforme ... --url ... --vues ...`.
