"""
Configuration du microservice de traduction médicale Wolof ⇄ Français
Projet: Assistant Médical YAMA - Pipeline NMT
"""

import os
from typing import Final

# CONFIGURATION MODÈLE HUGGING FACE
MODEL_NAME: Final[str] = "bilalfaye/nllb-200-distilled-600M-wo-fr-en"

# Codes de langue NLLB-200
LANG_WOLOF: Final[str] = "wol_Latn"
LANG_FRENCH: Final[str] = "fra_Latn"

# BASE DE DONNÉES MÉDICAMENTEUSE
# Chemin vers le fichier JSON contenant les médicaments
MEDICATION_DATABASE_PATH: Final[str] = "medications_database.json"

# CONFIGURATION GPU/CPU
# Le modèle détectera automatiquement CUDA si disponible
DEVICE: Final[str] = "auto"  # "cuda" si GPU disponible, sinon "cpu"

# PARAMÈTRES DE TRADUCTION
MAX_LENGTH: Final[int] = 512  # Longueur maximale des tokens
NUM_BEAMS: Final[int] = 5  # Beam search pour meilleure qualité
NO_REPEAT_NGRAM_SIZE: Final[int] = 3  # Éviter répétitions

# SEUILS DE SÉCURITÉ MÉDICALE (CRITIQUES)

# Seuil de similarité minimale pour les nombres/posologies
# Si la distance d'édition normalisée dépasse ce seuil → REJECT
NUMERIC_SIMILARITY_THRESHOLD: Final[float] = 0.05  # 5% de tolérance max

# Mots de négation critique en français (détection obligatoire)
CRITICAL_NEGATIONS_FR: Final[list[str]] = [
    "ne pas",
    "n'a pas",
    "ne jamais",
    "jamais",
    "aucun",
    "aucune",
    "interdit",
    "interdite",
    "contre-indiqué",
    "contre-indication",
    "éviter",
    "à éviter",
    "sans",
    "sauf",
    "excepté"
]

# Mots de négation critique en wolof (détection obligatoire)
CRITICAL_NEGATIONS_WO: Final[list[str]] = [
    "bul",  
    "du",   
    "dara",  
    "amul",  
    
]

# PATTERNS MÉDICAUX À PROTÉGER (NE DOIVENT PAS ÊTRE TRADUITS)

# Ces patterns seront extraits AVANT traduction et réinjectés APRÈS
# pour éviter toute corruption par le modèle NMT

# NOTE: Les médicaments sont maintenant gérés par medication_database.py
# Les patterns ci-dessous sont conservés comme backup/fallback

# Pattern pour les posologies (chiffres + unités médicales)
DOSAGE_PATTERNS: Final[list[str]] = [
    # Avec ou sans espace entre nombre et unité
    r'\b\d+\s*(?:mg|g|ml|l|mL|L|Mg|MG)\b',
    r'\b\d+(?:[.,]\d+)?\s*(?:mg|g|ml|l|mL|L|Mg|MG)\b',
    r'\b\d+\s*(?:cp|comprimés?|comprimé|gélules?|gélule|gouttes?|goutte)\b',
    r'\b\d+\s*(?:fois|x)\s*(?:par|/)\s*(?:jour|semaine|mois|jours|semaines)\b',
    r'\b(?:matin|midi|soir|nuit|matin et soir)\b',  # Moments de prise
    # Formats wolof
    r'\b\d+\s*(?:yoon)\b',  # "yoon" = fois en wolof
]

# Pattern pour les valeurs biologiques/médicales
MEDICAL_VALUES_PATTERNS: Final[list[str]] = [
    r'\b\d+(?:[.,]\d+)?°[CF]?\b',  # Température
    r'\b\d+/\d+\s*(?:mmHg)?\b',     # Tension artérielle
    r'\b\d+(?:[.,]\d+)?\s*(?:g/dl|mmol/l|UI/l)\b',  # Valeurs bio
]

# CONFIGURATION API
API_TITLE: Final[str] = "YAMA Medical Translation API"
API_VERSION: Final[str] = "1.0.0"
API_DESCRIPTION: Final[str] = """
Microservice de traduction médicale sécurisé Wolof ⇄ Français
pour le projet Assistant Médical YAMA.

⚠️ SYSTÈME CRITIQUE - Ne traduit PAS les posologies ni les médicaments.
"""

# LOGGING
LOG_LEVEL: Final[str] = os.getenv("LOG_LEVEL", "INFO")
LOG_FILE: Final[str] = "medical_translation.log"

# LIMITES DE RATE
MAX_INPUT_LENGTH: Final[int] = 10000  # Caractères max en entrée
REQUEST_TIMEOUT: Final[int] = 30  # Secondes