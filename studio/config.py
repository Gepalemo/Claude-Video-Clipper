"""Constantes et réglages du pipeline. Modifiables ici, en un seul endroit."""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUTPUT = Path(os.environ.get('STUDIO_OUTPUT', ROOT / 'output'))
REGISTRE = Path(os.environ.get('STUDIO_REGISTRE', OUTPUT / '_registre'))
JOURNAL = REGISTRE / 'journal_productions.jsonl'
SUIVI_CSV = REGISTRE / 'suivi_resultats.csv'
FONTS = ROOT / 'assets' / 'fonts'

# format de sortie
W, H, FPS = 1080, 1920, 30
DUREE_MIN, DUREE_MAX = 65.0, 100.0

# originalité : part minimale de commentaire original (narration) dans la durée finale.
# Les plateformes déclassent ou démonétisent le contenu « réutilisé » sans apport.
PART_NARRATION_MIN = 0.35
EXTRAIT_MAX_S = 30.0          # un extrait plus long déclenche un avertissement

# débit de parole pour estimer la durée d'un texte non encore enregistré (mots / seconde)
MOTS_PAR_SECONDE = 2.6

# whisper (local, gratuit)
WHISPER_MODELE = 'small'
WHISPER_LANGUE = 'auto'

# sous-titres
SOUS_TITRES = {'police': 'Montserrat ExtraBold', 'fichier_police': 'Montserrat-ExtraBold.ttf',
               'taille': 88, 'y': 1250, 'contour': 8, 'majuscules': True,
               'texte': '#FFFFFF', 'accent': '#FFD60A', 'contour_couleur': '#000000'}

# audio
LUFS_SEGMENT, LUFS_FINAL, TRUE_PEAK = -16, -14, -1.5

# types de licence acceptés et leurs propriétés par défaut
LICENCES = {
    'proprietaire':  {'libelle': 'Contenu dont je suis l\'auteur / le propriétaire', 'modif': True, 'commercial': True, 'attribution': False},
    'licence':       {'libelle': 'Licence ou autorisation écrite d\'un ayant droit', 'modif': None, 'commercial': None, 'attribution': None},
    'cc0':           {'libelle': 'Creative Commons CC0', 'modif': True, 'commercial': True, 'attribution': False},
    'domaine-public': {'libelle': 'Domaine public', 'modif': True, 'commercial': True, 'attribution': False},
    'cc-by':         {'libelle': 'Creative Commons BY', 'modif': True, 'commercial': True, 'attribution': True},
    'cc-by-sa':      {'libelle': 'Creative Commons BY-SA', 'modif': True, 'commercial': True, 'attribution': True},
}
# refusées : interdisent la modification (ND) ; NC accepté seulement si --non-commercial-assume
LICENCES_REFUSEES = {'cc-by-nd', 'cc-by-nc-nd'}
LICENCES_NC = {'cc-by-nc': 'Creative Commons BY-NC', 'cc-by-nc-sa': 'Creative Commons BY-NC-SA'}

PLATEFORMES = ('youtube_shorts', 'tiktok', 'instagram_reels', 'facebook_reels')
LIMITES_PLATEFORMES = {
    'youtube_shorts': {'titre': 100, 'description': 5000, 'hashtags': 15},
    'tiktok': {'legende': 2200, 'hashtags': 8},
    'instagram_reels': {'legende': 2200, 'hashtags': 30},
    'facebook_reels': {'legende': 2200, 'hashtags': 10},
}

CSV_COLONNES = ['production_id', 'titre', 'fichier', 'sha256', 'duree_s', 'date_export', 'plateforme',
                'statut', 'date_publication', 'url', 'vues', 'likes', 'commentaires', 'partages',
                'enregistrements', 'duree_moyenne_visionnage_s', 'taux_completion_pct',
                'abonnes_gagnes', 'date_releve', 'notes']
CSV_SEPARATEUR = ';'           # Excel en français ouvre directement ce format
