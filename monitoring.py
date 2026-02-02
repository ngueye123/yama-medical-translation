"""
Module de monitoring et logging pour la traduction médicale
Responsabilité: Traçabilité complète des requêtes et détection d'anomalies
"""

import logging
import json
import time
from datetime import datetime
from typing import Dict, Any, Optional
from pathlib import Path
from dataclasses import dataclass, asdict
import sys

from config import LOG_FILE, LOG_LEVEL


# CONFIGURATION DU LOGGING

def setup_logging():
    """
    Configure le système de logging avec sorties console et fichier.
    
    FORMAT:
    - Console: INFO et plus, format lisible
    - Fichier: DEBUG et plus, format JSON pour analyse ultérieure
    """
    # Créer le logger racine
    logger = logging.getLogger()
    logger.setLevel(getattr(logging, LOG_LEVEL))
    
    # Formateurs
    console_formatter = logging.Formatter(
        '%(asctime)s | %(levelname)-8s | %(name)s | %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    file_formatter = logging.Formatter(
        '%(asctime)s | %(levelname)s | %(name)s | %(funcName)s:%(lineno)d | %(message)s'
    )
    
    # Handler console (stdout)
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(console_formatter)
    
    # Handler fichier
    file_handler = logging.FileHandler(LOG_FILE, encoding='utf-8')
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(file_formatter)
    
    # Ajouter les handlers
    logger.addHandler(console_handler)
    logger.addHandler(file_handler)
    
    logging.info("=" * 80)
    logging.info("YAMA Medical Translation Service - Logging initialisé")
    logging.info("=" * 80)


# DATACLASSES POUR STRUCTURED LOGGING

@dataclass
class TranslationRequestLog:
    """Log structuré d'une requête de traduction"""
    timestamp: str
    request_id: str
    source_lang: str
    target_lang: str
    source_text_length: int
    source_text_preview: str  # Premiers 100 chars
    client_ip: Optional[str] = None
    user_agent: Optional[str] = None


@dataclass
class TranslationResponseLog:
    """Log structuré d'une réponse de traduction"""
    timestamp: str
    request_id: str
    success: bool
    translation_time_ms: float
    translated_text_length: int
    translated_text_preview: str  # Premiers 100 chars
    safety_warnings: list[str]
    error_code: Optional[str] = None
    error_message: Optional[str] = None


@dataclass
class SafetyViolationLog:
    """Log structuré d'une violation de sécurité"""
    timestamp: str
    request_id: str
    violation_type: str
    source_text: str
    translated_text: str
    details: str
    severity: str  # "CRITICAL", "HIGH", "MEDIUM", "LOW"


# MONITEUR DE REQUÊTES

class TranslationMonitor:
    """
    Moniteur centralisé pour toutes les métriques de traduction.
    
    OBJECTIFS:
    1. Traçabilité complète (audit trail)
    2. Détection d'anomalies en temps réel
    3. Métriques de performance
    """
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        
        # Compteurs globaux
        self.total_requests = 0
        self.total_successes = 0
        self.total_failures = 0
        self.total_safety_violations = 0
        
        # Métriques de performance
        self.translation_times = []
        self.max_translation_time = 0.0
        self.min_translation_time = float('inf')
        
        self.logger.info("TranslationMonitor initialisé")
    
    def log_request(
        self,
        request_id: str,
        source_lang: str,
        target_lang: str,
        source_text: str,
        client_ip: Optional[str] = None,
        user_agent: Optional[str] = None
    ) -> None:
        """
        Log une requête entrante.
        
        Args:
            request_id: Identifiant unique de la requête
            source_lang: Langue source
            target_lang: Langue cible
            source_text: Texte à traduire
            client_ip: IP du client (optionnel)
            user_agent: User agent (optionnel)
        """
        self.total_requests += 1
        
        log_entry = TranslationRequestLog(
            timestamp=datetime.utcnow().isoformat(),
            request_id=request_id,
            source_lang=source_lang,
            target_lang=target_lang,
            source_text_length=len(source_text),
            source_text_preview=source_text[:100],
            client_ip=client_ip,
            user_agent=user_agent
        )
        
        self.logger.info(
            f"REQUÊTE [{request_id}] | "
            f"{source_lang}→{target_lang} | "
            f"Longueur: {len(source_text)} chars"
        )
        
        # Log JSON détaillé pour analyse
        self.logger.debug(f"Request details: {json.dumps(asdict(log_entry), ensure_ascii=False)}")
    
    def log_response(
        self,
        request_id: str,
        success: bool,
        translation_time_ms: float,
        translated_text: str = "",
        safety_warnings: list[str] = None,
        error_code: Optional[str] = None,
        error_message: Optional[str] = None
    ) -> None:
        """
        Log une réponse de traduction.
        
        Args:
            request_id: Identifiant unique de la requête
            success: Succès ou échec
            translation_time_ms: Temps de traduction en millisecondes
            translated_text: Texte traduit
            safety_warnings: Liste des warnings de sécurité
            error_code: Code d'erreur (si échec)
            error_message: Message d'erreur (si échec)
        """
        if success:
            self.total_successes += 1
            status_icon = "✅"
        else:
            self.total_failures += 1
            status_icon = "❌"
        
        # Mise à jour des métriques de performance
        self.translation_times.append(translation_time_ms)
        self.max_translation_time = max(self.max_translation_time, translation_time_ms)
        if translation_time_ms > 0:
            self.min_translation_time = min(self.min_translation_time, translation_time_ms)
        
        log_entry = TranslationResponseLog(
            timestamp=datetime.utcnow().isoformat(),
            request_id=request_id,
            success=success,
            translation_time_ms=translation_time_ms,
            translated_text_length=len(translated_text),
            translated_text_preview=translated_text[:100] if translated_text else "",
            safety_warnings=safety_warnings or [],
            error_code=error_code,
            error_message=error_message
        )
        
        self.logger.info(
            f"{status_icon} RÉPONSE [{request_id}] | "
            f"Temps: {translation_time_ms:.2f}ms | "
            f"Longueur: {len(translated_text)} chars"
        )
        
        if not success:
            self.logger.error(
                f"❌ ÉCHEC [{request_id}] | "
                f"Code: {error_code} | "
                f"Message: {error_message}"
            )
        
        if safety_warnings:
            self.logger.warning(
                f"⚠️ WARNINGS [{request_id}] | "
                f"Nombre: {len(safety_warnings)}"
            )
        
        # Log JSON détaillé
        self.logger.debug(f"Response details: {json.dumps(asdict(log_entry), ensure_ascii=False)}")
    
    def log_safety_violation(
        self,
        request_id: str,
        violation_type: str,
        source_text: str,
        translated_text: str,
        details: str,
        severity: str = "CRITICAL"
    ) -> None:
        """
        Log une violation de sécurité (CRITIQUE).
        
        Ces logs doivent être surveillés en priorité car ils indiquent
        des traductions potentiellement dangereuses rejetées.
        
        Args:
            request_id: Identifiant unique de la requête
            violation_type: Type de violation
            source_text: Texte source
            translated_text: Texte traduit (dangereux)
            details: Détails de la violation
            severity: Niveau de sévérité
        """
        self.total_safety_violations += 1
        
        log_entry = SafetyViolationLog(
            timestamp=datetime.utcnow().isoformat(),
            request_id=request_id,
            violation_type=violation_type,
            source_text=source_text[:200],  # Tronquer pour log
            translated_text=translated_text[:200],
            details=details,
            severity=severity
        )
        
        self.logger.critical(
            f"VIOLATION DE SÉCURITÉ [{request_id}] | "
            f"Type: {violation_type} | "
            f"Sévérité: {severity}"
        )
        
        self.logger.critical(
            f"Details: {details}"
        )
        
        # Log JSON pour analyse forensique
        self.logger.critical(
            f"Violation details: {json.dumps(asdict(log_entry), ensure_ascii=False)}"
        )
    
    def get_statistics(self) -> Dict[str, Any]:
        """
        Retourne les statistiques globales du service.
        
        Returns:
            Dictionnaire avec toutes les métriques
        """
        avg_time = (
            sum(self.translation_times) / len(self.translation_times)
            if self.translation_times else 0
        )
        
        success_rate = (
            (self.total_successes / self.total_requests * 100)
            if self.total_requests > 0 else 0
        )
        
        stats = {
            "total_requests": self.total_requests,
            "total_successes": self.total_successes,
            "total_failures": self.total_failures,
            "total_safety_violations": self.total_safety_violations,
            "success_rate_percent": round(success_rate, 2),
            "performance": {
                "avg_translation_time_ms": round(avg_time, 2),
                "min_translation_time_ms": round(self.min_translation_time, 2) if self.min_translation_time != float('inf') else 0,
                "max_translation_time_ms": round(self.max_translation_time, 2),
            }
        }
        
        self.logger.info(f"📊 Statistiques: {json.dumps(stats, indent=2)}")
        return stats
    
    def log_startup(self, model_name: str, device: str) -> None:
        """
        Log le démarrage du service.
        
        Args:
            model_name: Nom du modèle chargé
            device: Device utilisé (cuda/cpu)
        """
        self.logger.info("=" * 80)
        self.logger.info("🏥 YAMA MEDICAL TRANSLATION SERVICE - DÉMARRAGE")
        self.logger.info("=" * 80)
        self.logger.info(f"📦 Modèle: {model_name}")
        self.logger.info(f"💻 Device: {device}")
        self.logger.info(f"🕐 Timestamp: {datetime.utcnow().isoformat()}")
        self.logger.info("=" * 80)
    
    def log_shutdown(self) -> None:
        """Log l'arrêt du service avec statistiques finales."""
        self.logger.info("=" * 80)
        self.logger.info("🛑 YAMA MEDICAL TRANSLATION SERVICE - ARRÊT")
        self.logger.info("=" * 80)
        
        # Afficher les stats finales
        self.get_statistics()
        
        self.logger.info(f"🕐 Timestamp: {datetime.utcnow().isoformat()}")
        self.logger.info("=" * 80)


# INSTANCE GLOBALE

# Instance singleton du monitor (sera initialisée au démarrage de l'app)
monitor: Optional[TranslationMonitor] = None


def get_monitor() -> TranslationMonitor:
    """
    Récupère l'instance globale du monitor.
    
    Returns:
        Instance de TranslationMonitor
    """
    global monitor
    if monitor is None:
        monitor = TranslationMonitor()
    return monitor