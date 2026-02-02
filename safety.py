"""
Module de sécurité pour la traduction médicale
Responsabilité: Garantir qu'aucune information critique n'est perdue ou altérée
"""

import re
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass
from difflib import SequenceMatcher
import logging

from config import (
    CRITICAL_NEGATIONS_FR,
    CRITICAL_NEGATIONS_WO,
    DOSAGE_PATTERNS,
    MEDICAL_VALUES_PATTERNS,
    NUMERIC_SIMILARITY_THRESHOLD,
    MEDICATION_DATABASE_PATH
)

logger = logging.getLogger(__name__)


@dataclass
class SafetyCheckResult:
    """Résultat d'une vérification de sécurité"""
    is_safe: bool
    error_code: Optional[str] = None
    error_message: Optional[str] = None
    warnings: List[str] = None
    
    def __post_init__(self):
        if self.warnings is None:
            self.warnings = []


class MedicalSafetyChecker:
    """
    Vérificateur de sécurité pour les traductions médicales.
    
    PRINCIPES DE CONCEPTION:
    1. FAIL-SAFE: En cas de doute, rejeter la traduction
    2. TRAÇABILITÉ: Chaque rejet doit être loggé avec raison explicite
    3. IMMUTABILITÉ: Les données critiques ne doivent JAMAIS être altérées
    """
    
    def __init__(self, medication_db_path: str = None):
        # Charger la base de données médicamenteuse
        try:
            from medication_database import MedicationDatabase
            
            db_path = medication_db_path or MEDICATION_DATABASE_PATH
            self.medication_db = MedicationDatabase(db_path)
            
            # Utiliser le pattern compilé de la base de données
            self.medication_regex = [self.medication_db.medication_pattern]
            
            logger.info(
                f"Base de données médicamenteuse chargée: "
                f"{len(self.medication_db.medications)} médicaments"
            )
            
        except Exception as e:
            logger.warning(
                f"Impossible de charger la base de médicaments: {e}. "
                f"Utilisation des patterns par défaut."
            )
            # Fallback: utiliser un pattern minimal par défaut
            self.medication_regex = [
                re.compile(
                    r'\b(?:paracétamol|ibuprofène|aspirine|amoxicilline)\b',
                    re.IGNORECASE
                )
            ]
        
        # Compilation des patterns regex pour performance
        self.dosage_regex = [re.compile(p, re.IGNORECASE) for p in DOSAGE_PATTERNS]
        self.medical_values_regex = [re.compile(p, re.IGNORECASE) for p in MEDICAL_VALUES_PATTERNS]
        
        # Pattern pour extraire tous les nombres (entiers et décimaux)
        self.number_pattern = re.compile(r'\b\d+(?:[.,]\d+)?\b')
        
        logger.info("MedicalSafetyChecker initialisé avec succès")
    
    # EXTRACTION DES ÉLÉMENTS CRITIQUES (À PROTÉGER)
    
    def extract_protected_elements(self, text: str) -> Dict[str, List[str]]:
        """
        Extrait tous les éléments qui NE DOIVENT PAS être traduits.
        Ces éléments seront masqués avant traduction puis réinjectés après.
        
        Args:
            text: Texte source
            
        Returns:
            Dictionnaire contenant les éléments protégés par catégorie
        """
        protected = {
            "medications": [],
            "dosages": [],
            "medical_values": [],
            "all_numbers": []
        }
        
        # Extraction des médicaments
        for pattern in self.medication_regex:
            protected["medications"].extend(pattern.findall(text))
        
        # Extraction des posologies
        for pattern in self.dosage_regex:
            protected["dosages"].extend(pattern.findall(text))
        
        # Extraction des valeurs médicales
        for pattern in self.medical_values_regex:
            protected["medical_values"].extend(pattern.findall(text))
        
        # Extraction de TOUS les nombres (sécurité ultime)
        protected["all_numbers"] = self.number_pattern.findall(text)
        
        logger.debug(f"Éléments protégés extraits: {protected}")
        return protected
    
    def restore_critical_values_post_translation(
        self,
        source_text: str,
        translated_text: str
    ) -> str:
       
        result = translated_text
        
        # Extraire les posologies du source
        source_dosages = []
        for pattern in self.dosage_regex:
            source_dosages.extend(pattern.findall(source_text))
        
        # Extraire les posologies du traduit
        translated_dosages = []
        for pattern in self.dosage_regex:
            translated_dosages.extend(pattern.findall(translated_text))
        
        # Remplacer les posologies modifiées
        for i, source_dosage in enumerate(source_dosages):
            if source_dosage not in result:
                # La posologie a été modifiée, essayer de la restaurer
                if i < len(translated_dosages):
                    wrong_dosage = translated_dosages[i]
                    logger.warning(
                        f"Posologie modifiée détectée: '{wrong_dosage}' → '{source_dosage}' (restauration)"
                    )
                    result = result.replace(wrong_dosage, source_dosage, 1)
        
        # Extraire tous les nombres du source
        source_numbers = self.number_pattern.findall(source_text)
        
        # Extraire tous les nombres du résultat actuel
        result_numbers = self.number_pattern.findall(result)
        
        # Si des nombres manquent, essayer de les restaurer
        for i, source_num in enumerate(source_numbers):
            # Si ce nombre n'est pas dans le résultat
            if source_num not in result:
                # Essayer de trouver le nombre correspondant qui a été mal traduit
                if i < len(result_numbers):
                    wrong_num = result_numbers[i]
                    logger.warning(
                        f"Nombre modifié détecté: '{wrong_num}' → '{source_num}' (restauration)"
                    )
                    # Remplacer uniquement la première occurrence
                    result = result.replace(wrong_num, source_num, 1)
        
        logger.info(f"Restauration terminée: {len(source_numbers)} nombres vérifiés")
        return result
    
    def mask_protected_elements(self, text: str) -> Tuple[str, Dict[str, str]]:
        """
        Masque les éléments protégés avec des placeholders avant traduction.
        
        STRATÉGIE: Utiliser des mots neutres en majuscules qui ne seront pas traduits
        car ils ressemblent à des noms propres ou acronymes médicaux.
        
        Args:
            text: Texte original
            
        Returns:
            Tuple (texte_masqué, mapping_placeholders)
        """
        masked_text = text
        placeholder_map = {}
        placeholder_counter = 0
        
        # Masquer les médicaments avec des noms "médicaux" neutres
        for i, pattern in enumerate(self.medication_regex):
            for match in pattern.finditer(text):
                med_text = match.group(0)
                # Utiliser MEDICATION suivi d'une lettre (A, B, C, etc.)
                placeholder = f"MEDICATION{chr(65 + placeholder_counter)}"  # A, B, C...
                placeholder_counter += 1
                if placeholder not in masked_text and med_text in masked_text:
                    masked_text = masked_text.replace(med_text, placeholder, 1)
                    placeholder_map[placeholder] = med_text
        
        # Masquer les posologies avec le pattern DOSAGE + numéro
        for i, pattern in enumerate(self.dosage_regex):
            for match in pattern.finditer(masked_text):
                dosage_text = match.group(0)
                if not dosage_text.startswith("MEDICATION") and not dosage_text.startswith("DOSAGE"):
                    placeholder = f"DOSAGE{placeholder_counter}"
                    placeholder_counter += 1
                    masked_text = masked_text.replace(dosage_text, placeholder, 1)
                    placeholder_map[placeholder] = dosage_text
        
        # Masquer TOUS les nombres restants avec VALUEXX
        for match in self.number_pattern.finditer(masked_text):
            number_text = match.group(0)
            if not any(kw in number_text for kw in ["MEDICATION", "DOSAGE", "VALUE"]):
                placeholder = f"VALUE{placeholder_counter}"
                placeholder_counter += 1
                masked_text = masked_text.replace(number_text, placeholder, 1)
                placeholder_map[placeholder] = number_text
        
        logger.debug(f"Texte masqué: {masked_text}")
        logger.debug(f"Mapping ({len(placeholder_map)} éléments): {placeholder_map}")
        
        return masked_text, placeholder_map
    
    def unmask_protected_elements(self, text: str, placeholder_map: Dict[str, str]) -> str:
        """
        Réinjecte les éléments protégés dans le texte traduit.
        
        Args:
            text: Texte traduit avec placeholders
            placeholder_map: Mapping des placeholders vers valeurs originales
            
        Returns:
            Texte avec éléments protégés réinsérés
        """
        unmasked_text = text
        for placeholder, original_value in placeholder_map.items():
            unmasked_text = unmasked_text.replace(placeholder, original_value)
        
        logger.debug(f"Texte démasqué: {unmasked_text}")
        return unmasked_text
    
    # VÉRIFICATIONS DE SÉCURITÉ POST-TRADUCTION
    
    def check_numeric_integrity(self, source: str, translated: str) -> SafetyCheckResult:
        """
        Vérifie que TOUS les nombres sont préservés exactement.
        
        CRITIQUE: Aucune modification de chiffre n'est acceptable en contexte médical.
        
        Args:
            source: Texte source
            translated: Texte traduit
            
        Returns:
            SafetyCheckResult indiquant si les nombres sont intacts
        """
        source_numbers = self.number_pattern.findall(source)
        translated_numbers = self.number_pattern.findall(translated)
        
        # Normaliser les nombres (remplacer virgules par points)
        source_numbers_normalized = [n.replace(',', '.') for n in source_numbers]
        translated_numbers_normalized = [n.replace(',', '.') for n in translated_numbers]
        
        # Tri pour comparaison (ordre peut changer légèrement)
        source_numbers_normalized.sort()
        translated_numbers_normalized.sort()
        
        if source_numbers_normalized != translated_numbers_normalized:
            error_msg = (
                f"SÉCURITÉ CRITIQUE: Intégrité numérique compromise. "
                f"Source: {source_numbers} | Traduit: {translated_numbers}"
            )
            logger.error(error_msg)
            
            return SafetyCheckResult(
                is_safe=False,
                error_code="NUMERIC_INTEGRITY_VIOLATION",
                error_message=error_msg
            )
        
        logger.debug("Vérification numérique: OK")
        return SafetyCheckResult(is_safe=True)
    
    def check_negation_preservation(
        self, 
        source: str, 
        translated: str,
        source_lang: str
    ) -> SafetyCheckResult:
        """
        Vérifie que les négations critiques sont préservées.
        
        CRITIQUE: La perte d'une négation peut inverser une instruction médicale
        (ex: "ne pas prendre" → "prendre" est MORTEL)
        
        Args:
            source: Texte source
            translated: Texte traduit
            source_lang: Langue source ("wol_Latn" ou "fra_Latn")
            
        Returns:
            SafetyCheckResult indiquant si les négations sont préservées
        """
        # Sélectionner la liste de négations appropriée
        if source_lang == "fra_Latn":
            source_negations = CRITICAL_NEGATIONS_FR
            target_negations = CRITICAL_NEGATIONS_WO
        else:
            source_negations = CRITICAL_NEGATIONS_WO
            target_negations = CRITICAL_NEGATIONS_FR
        
        # Détecter négations dans le source
        found_negations = []
        for negation in source_negations:
            if negation.lower() in source.lower():
                found_negations.append(negation)
        
        # Si des négations sont présentes dans source, 
        # il DOIT y avoir au moins une négation dans target
        if found_negations:
            has_target_negation = any(
                neg.lower() in translated.lower() 
                for neg in target_negations
            )
            
            if not has_target_negation:
                error_msg = (
                    f"SÉCURITÉ CRITIQUE: Négation perdue en traduction. "
                    f"Négations source détectées: {found_negations} | "
                    f"Aucune négation trouvée dans la traduction."
                )
                logger.error(error_msg)
                
                return SafetyCheckResult(
                    is_safe=False,
                    error_code="NEGATION_LOSS",
                    error_message=error_msg
                )
        
        logger.debug("Vérification négations: OK")
        return SafetyCheckResult(is_safe=True)
    
    def check_length_anomaly(self, source: str, translated: str) -> SafetyCheckResult:
        """
        Vérifie qu'il n'y a pas d'anomalie de longueur suspecte.
        
        HEURISTIQUE: Une traduction 5x plus courte ou 5x plus longue 
        indique probablement un problème.
        
        Args:
            source: Texte source
            translated: Texte traduit
            
        Returns:
            SafetyCheckResult avec warning si anomalie détectée
        """
        source_len = len(source.strip())
        translated_len = len(translated.strip())
        
        if source_len == 0 or translated_len == 0:
            return SafetyCheckResult(
                is_safe=False,
                error_code="EMPTY_TRANSLATION",
                error_message="Source ou traduction vide"
            )
        
        ratio = translated_len / source_len
        
        warnings = []
        if ratio < 0.2 or ratio > 5.0:
            warning_msg = (
                f"ATTENTION: Ratio de longueur suspect ({ratio:.2f}). "
                f"Source: {source_len} chars, Traduit: {translated_len} chars"
            )
            logger.warning(warning_msg)
            warnings.append(warning_msg)
        
        return SafetyCheckResult(
            is_safe=True,
            warnings=warnings
        )
    
    def check_placeholder_integrity(
        self, 
        translated: str, 
        placeholder_map: Dict[str, str]
    ) -> SafetyCheckResult:
        """
        Vérifie que tous les placeholders ont été correctement remplacés.
        
        Args:
            translated: Texte traduit final
            placeholder_map: Mapping des placeholders
            
        Returns:
            SafetyCheckResult indiquant si des placeholders subsistent
        """
        # Chercher des patterns de placeholder non remplacés
        placeholder_pattern = re.compile(r'\b(?:MEDICATION[A-Z]|DOSAGE\d+|VALUE\d+)\b')
        remaining_placeholders = placeholder_pattern.findall(translated)
        
        if remaining_placeholders:
            error_msg = (
                f"SÉCURITÉ: Placeholders non remplacés détectés: {remaining_placeholders}"
            )
            logger.error(error_msg)
            
            return SafetyCheckResult(
                is_safe=False,
                error_code="PLACEHOLDER_RESIDUE",
                error_message=error_msg
            )
        
        return SafetyCheckResult(is_safe=True)
    
    # VÉRIFICATION GLOBALE
    
    def run_full_safety_check(
        self,
        source_text: str,
        translated_text: str,
        source_lang: str,
        placeholder_map: Optional[Dict[str, str]] = None
    ) -> SafetyCheckResult:
        """
        Exécute TOUTES les vérifications de sécurité.
        
        Cette fonction est le point d'entrée principal pour valider une traduction.
        
        Args:
            source_text: Texte source original
            translated_text: Texte traduit final
            source_lang: Langue source
            placeholder_map: Mapping des placeholders (si masquage utilisé)
            
        Returns:
            SafetyCheckResult global (safe seulement si TOUS les checks passent)
        """
        logger.info("Début de la vérification de sécurité complète")
        
        all_warnings = []
        
        # Check 1: Intégrité numérique (CRITIQUE)
        numeric_check = self.check_numeric_integrity(source_text, translated_text)
        if not numeric_check.is_safe:
            return numeric_check
        all_warnings.extend(numeric_check.warnings)
        
        # Check 2: Préservation des négations (CRITIQUE)
        negation_check = self.check_negation_preservation(
            source_text, 
            translated_text,
            source_lang
        )
        if not negation_check.is_safe:
            return negation_check
        all_warnings.extend(negation_check.warnings)
        
        # Check 3: Anomalie de longueur (WARNING)
        length_check = self.check_length_anomaly(source_text, translated_text)
        all_warnings.extend(length_check.warnings)
        
        # Check 4: Intégrité des placeholders (si applicable)
        if placeholder_map is not None:
            placeholder_check = self.check_placeholder_integrity(
                translated_text,
                placeholder_map
            )
            if not placeholder_check.is_safe:
                return placeholder_check
        
        logger.info("Vérification de sécurité: TOUTES LES CHECKS PASSÉES")
        
        return SafetyCheckResult(
            is_safe=True,
            warnings=all_warnings
        )


# ============================================================================
# UTILITAIRES DE VÉRIFICATION SUPPLÉMENTAIRES
# ============================================================================

def calculate_text_similarity(text1: str, text2: str) -> float:
    """
    Calcule la similarité entre deux textes (Ratcliff-Obershelp).
    
    Utilisé pour détecter si la traduction est trop différente (suspicion d'erreur)
    ou trop similaire (suspicion de non-traduction).
    
    Returns:
        Similarité entre 0.0 (totalement différent) et 1.0 (identique)
    """
    return SequenceMatcher(None, text1.lower(), text2.lower()).ratio()


def detect_code_injection_attempt(text: str) -> bool:
    """
    Détecte des tentatives d'injection de code dans l'input.
    
    SÉCURITÉ: Certains utilisateurs malveillants pourraient tenter d'injecter
    des prompts adverses dans le texte médical.
    
    Returns:
        True si injection suspectée
    """
    # Patterns suspects (non exhaustif, à enrichir selon les besoins)
    injection_patterns = [
        r'<script',
        r'javascript:',
        r'onclick=',
        r'onerror=',
        r'eval\(',
        r'__import__',
        r'exec\(',
    ]
    
    text_lower = text.lower()
    for pattern in injection_patterns:
        if re.search(pattern, text_lower, re.IGNORECASE):
            logger.warning(f"⚠️ Tentative d'injection détectée: {pattern}")
            return True
    
    return False