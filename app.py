"""
YAMA Medical Translation API - Application principale
Microservice de traduction médicale sécurisé Wolof ⇄ Français

Architecture:
1. Chargement du modèle NLLB-200 (bilalfaye/nllb-200-distilled-600M-wo-fr-en)
2. Masquage des éléments critiques (médicaments, posologies)
3. Traduction via le modèle
4. Démasquage et vérifications de sécurité
5. Retour de la traduction ou erreur
"""

import uuid
import time
from typing import Optional, List
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, validator
import torch
from transformers import AutoTokenizer, AutoModelForSeq2SeqLM, pipeline
import logging

from config import (
    MODEL_NAME,
    LANG_WOLOF,
    LANG_FRENCH,
    MAX_LENGTH,
    NUM_BEAMS,
    NO_REPEAT_NGRAM_SIZE,
    API_TITLE,
    API_VERSION,
    API_DESCRIPTION,
    MAX_INPUT_LENGTH,
    REQUEST_TIMEOUT
)
from safety import (
    MedicalSafetyChecker,
    detect_code_injection_attempt,
    calculate_text_similarity
)
from monitoring import setup_logging, get_monitor

# INITIALISATION DU LOGGING
setup_logging()
logger = logging.getLogger(__name__)


# MODÈLES PYDANTIC (SCHÉMAS API)

class TranslationRequest(BaseModel):
    """Requête de traduction"""
    text: str = Field(
        ...,
        description="Texte à traduire",
        min_length=1,
        max_length=MAX_INPUT_LENGTH
    )
    source_lang: str = Field(
        ...,
        description="Langue source (wol_Latn ou fra_Latn)"
    )
    target_lang: str = Field(
        ...,
        description="Langue cible (wol_Latn ou fra_Latn)"
    )
    
    @validator('source_lang', 'target_lang')
    def validate_language(cls, v):
        """Valider que les langues sont supportées"""
        if v not in [LANG_WOLOF, LANG_FRENCH]:
            raise ValueError(
                f"Langue non supportée: {v}. "
                f"Langues acceptées: {LANG_WOLOF}, {LANG_FRENCH}"
            )
        return v
    
    @validator('text')
    def validate_text(cls, v):
        """Valider le texte d'entrée"""
        # Détection d'injection
        if detect_code_injection_attempt(v):
            raise ValueError("Tentative d'injection de code détectée")
        
        # Vérifier que le texte n'est pas vide après strip
        if not v.strip():
            raise ValueError("Le texte ne peut pas être vide")
        
        return v.strip()


class TranslationResponse(BaseModel):
    """Réponse de traduction réussie"""
    request_id: str = Field(..., description="Identifiant unique de la requête")
    source_text: str = Field(..., description="Texte source")
    translated_text: str = Field(..., description="Texte traduit")
    source_lang: str = Field(..., description="Langue source")
    target_lang: str = Field(..., description="Langue cible")
    translation_time_ms: float = Field(..., description="Temps de traduction en ms")
    safety_warnings: List[str] = Field(
        default=[],
        description="Avertissements de sécurité (non bloquants)"
    )


class ErrorResponse(BaseModel):
    """Réponse d'erreur"""
    request_id: str = Field(..., description="Identifiant unique de la requête")
    error_code: str = Field(..., description="Code d'erreur")
    error_message: str = Field(..., description="Message d'erreur détaillé")
    details: Optional[str] = Field(None, description="Détails supplémentaires")


class HealthResponse(BaseModel):
    """Réponse de health check"""
    status: str
    model_loaded: bool
    device: str
    statistics: dict


# VARIABLES GLOBALES (État du service)
model = None
tokenizer = None
translator = None
safety_checker = None
device = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Gestion du cycle de vie de l'application (startup/shutdown).
    """
    # STARTUP
    logger.info("Initialisation du service de traduction...")
    
    global model, tokenizer, translator, safety_checker, device
    
    try:
        # Détection du device
        device = "cuda" if torch.cuda.is_available() else "cpu"
        logger.info(f"Device détecté: {device}")
        
        if device == "cuda":
            logger.info(f"GPU: {torch.cuda.get_device_name(0)}")
            logger.info(f"VRAM disponible: {torch.cuda.get_device_properties(0).total_memory / 1e9:.2f} GB")
        
        # Chargement du tokenizer
        logger.info(f"Chargement du tokenizer: {MODEL_NAME}")
        tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME)
        logger.info("Tokenizer chargé")
        
        # Chargement du modèle
        logger.info(f"Chargement du modèle: {MODEL_NAME}")
        model = AutoModelForSeq2SeqLM.from_pretrained(MODEL_NAME)
        model.to(device)
        model.eval()  # Mode évaluation (pas d'entraînement)
        logger.info("Modèle chargé et prêt")
        
        # Création du pipeline de traduction
        translator = pipeline(
            "translation",
            model=model,
            tokenizer=tokenizer,
            device=0 if device == "cuda" else -1
        )
        logger.info("Pipeline de traduction créé")
        
        # Initialisation du safety checker
        safety_checker = MedicalSafetyChecker()
        logger.info("Safety checker initialisé")
        
        # Log du démarrage
        monitor = get_monitor()
        monitor.log_startup(MODEL_NAME, device)
        
        logger.info("Service prêt à recevoir des requêtes")
        
    except Exception as e:
        logger.critical(f"ERREUR FATALE lors de l'initialisation: {str(e)}")
        raise
    
    yield
    
    # SHUTDOWN
    logger.info("Arrêt du service...")
    monitor = get_monitor()
    monitor.log_shutdown()
    
    # Libération de la mémoire GPU
    if device == "cuda" and model is not None:
        del model
        del translator
        torch.cuda.empty_cache()
        logger.info("🧹 Mémoire GPU libérée")
    
    logger.info("Service arrêté proprement")


# CRÉATION DE L'APPLICATION FASTAPI

app = FastAPI(
    title=API_TITLE,
    version=API_VERSION,
    description=API_DESCRIPTION,
    lifespan=lifespan
)

# CORS 
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # En production, spécifier les domaines autorisés
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# MIDDLEWARE DE LOGGING DES REQUÊTES

@app.middleware("http")
async def log_requests(request: Request, call_next):
    """
    Middleware pour logger toutes les requêtes HTTP.
    """
    start_time = time.time()
    
    # Générer un ID unique pour cette requête
    request_id = str(uuid.uuid4())
    request.state.request_id = request_id
    
    # Logger la requête entrante
    logger.info(f"[{request_id}] {request.method} {request.url.path}")
    
    # Traiter la requête
    response = await call_next(request)
    
    # Calculer le temps de traitement
    process_time = (time.time() - start_time) * 1000
    
    # Logger la réponse
    logger.info(
        f"[{request_id}] Status: {response.status_code} | "
        f"Temps: {process_time:.2f}ms"
    )
    
    # Ajouter le request_id dans les headers de réponse
    response.headers["X-Request-ID"] = request_id
    response.headers["X-Process-Time"] = f"{process_time:.2f}ms"
    
    return response


# ENDPOINTS

@app.get("/", response_model=dict)
async def root():
    """
    Endpoint racine - Informations sur l'API.
    """
    return {
        "service": API_TITLE,
        "version": API_VERSION,
        "status": "running",
        "endpoints": {
            "translate": "/translate",
            "health": "/health",
            "stats": "/statistics",
            "docs": "/docs"
        }
    }


@app.get("/health", response_model=HealthResponse)
async def health_check():
    """
    Health check - Vérifier l'état du service.
    
    Utile pour les orchestrateurs (Docker Swarm)
    """
    monitor = get_monitor()
    
    return HealthResponse(
        status="healthy" if model is not None else "unhealthy",
        model_loaded=model is not None,
        device=device or "unknown",
        statistics=monitor.get_statistics()
    )


@app.get("/statistics", response_model=dict)
async def get_statistics():
    """
    Récupérer les statistiques d'utilisation du service.
    """
    monitor = get_monitor()
    return monitor.get_statistics()


@app.post(
    "/translate",
    response_model=TranslationResponse,
    responses={
        200: {"description": "Traduction réussie"},
        400: {"model": ErrorResponse, "description": "Requête invalide"},
        422: {"model": ErrorResponse, "description": "Violation de sécurité"},
        500: {"model": ErrorResponse, "description": "Erreur serveur"}
    }
)
async def translate(
    request: TranslationRequest,
    http_request: Request
) -> TranslationResponse:
    
    start_time = time.time()
    request_id = http_request.state.request_id
    
    monitor = get_monitor()
    
    # Log de la requête
    monitor.log_request(
        request_id=request_id,
        source_lang=request.source_lang,
        target_lang=request.target_lang,
        source_text=request.text,
        client_ip=http_request.client.host if http_request.client else None,
        user_agent=http_request.headers.get("user-agent")
    )
    
    try:
        # Vérifier que le service est prêt
        if model is None or tokenizer is None or safety_checker is None:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Service de traduction non initialisé"
            )
        
        # Vérifier que source et target sont différents
        if request.source_lang == request.target_lang:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Langue source et cible doivent être différentes"
            )
        
        # ÉTAPE 1: TRADUCTION DIRECTE (sans masquage)
        logger.debug(f"[{request_id}] Début de la traduction...")
        
        # Définir la langue source pour le tokenizer NLLB
        tokenizer.src_lang = request.source_lang
        
        # Préparer le texte pour le modèle NLLB (TEXTE ORIGINAL, pas masqué)
        inputs = tokenizer(
            request.text,  # <- CHANGEMENT: on traduit le texte original
            return_tensors="pt",
            padding=True,
            truncation=True,
            max_length=MAX_LENGTH
        )
        
        # Déplacer sur le bon device
        inputs = {k: v.to(device) for k, v in inputs.items()}
        
        # Traduction
        with torch.no_grad():
            # Forcer la langue cible
            forced_bos_token_id = None
            
            # Essayer différentes méthodes selon la version
            if hasattr(tokenizer, 'lang_code_to_id'):
                try:
                    forced_bos_token_id = tokenizer.lang_code_to_id[request.target_lang]
                    logger.debug(f"[{request_id}] Langue cible via lang_code_to_id: {forced_bos_token_id}")
                except Exception as e:
                    logger.warning(f"[{request_id}] lang_code_to_id échoué: {e}")
            
            if forced_bos_token_id is None and hasattr(tokenizer, 'lang_token_to_id'):
                try:
                    forced_bos_token_id = tokenizer.lang_token_to_id[request.target_lang]
                    logger.debug(f"[{request_id}] Langue cible via lang_token_to_id: {forced_bos_token_id}")
                except Exception as e:
                    logger.warning(f"[{request_id}] lang_token_to_id échoué: {e}")
            
            if forced_bos_token_id is None:
                try:
                    forced_bos_token_id = tokenizer.convert_tokens_to_ids(request.target_lang)
                    logger.debug(f"[{request_id}] Langue cible via convert_tokens_to_ids: {forced_bos_token_id}")
                except Exception as e:
                    logger.warning(f"[{request_id}] convert_tokens_to_ids échoué: {e}")
            
            if forced_bos_token_id is None:
                logger.warning(
                    f"[{request_id}] Impossible de déterminer forced_bos_token_id. "
                    f"La traduction se fera sans forcer la langue cible."
                )
            
            # Générer la traduction
            translated_tokens = model.generate(
                **inputs,
                forced_bos_token_id=forced_bos_token_id,
                max_length=MAX_LENGTH,
                num_beams=NUM_BEAMS,
                no_repeat_ngram_size=NO_REPEAT_NGRAM_SIZE,
                early_stopping=True
            )
        
        # Décoder la traduction
        translated_text_raw = tokenizer.decode(
            translated_tokens[0],
            skip_special_tokens=True
        )
        
        logger.debug(f"[{request_id}] Traduction brute: {translated_text_raw[:100]}...")
        
        # ÉTAPE 2: RESTAURATION DES VALEURS CRITIQUES
        logger.debug(f"[{request_id}] Restauration des valeurs critiques...")
        
        translated_text = safety_checker.restore_critical_values_post_translation(
            source_text=request.text,
            translated_text=translated_text_raw
        )
        
       
        # ÉTAPE 3: VÉRIFICATIONS DE SÉCURITÉ
        logger.debug(f"[{request_id}] Vérifications de sécurité...")
        
        safety_result = safety_checker.run_full_safety_check(
            source_text=request.text,
            translated_text=translated_text,
            source_lang=request.source_lang,
            placeholder_map=None  # Plus de placeholders avec la nouvelle stratégie
        )
        
        if not safety_result.is_safe:
            # VIOLATION DE SÉCURITÉ - REJETER LA TRADUCTION
            logger.error(
                f"[{request_id}] ❌ VIOLATION DE SÉCURITÉ: "
                f"{safety_result.error_code}"
            )
            
            # Logger la violation
            monitor.log_safety_violation(
                request_id=request_id,
                violation_type=safety_result.error_code,
                source_text=request.text,
                translated_text=translated_text,
                details=safety_result.error_message,
                severity="CRITICAL"
            )
            
            # Calculer le temps écoulé
            elapsed_time = (time.time() - start_time) * 1000
            
            # Logger la réponse d'erreur
            monitor.log_response(
                request_id=request_id,
                success=False,
                translation_time_ms=elapsed_time,
                error_code=safety_result.error_code,
                error_message=safety_result.error_message
            )
            
            # Retourner une erreur 422 (Unprocessable Entity)
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail={
                    "request_id": request_id,
                    "error_code": safety_result.error_code,
                    "error_message": safety_result.error_message,
                    "details": (
                        "La traduction a été rejetée car elle viole les règles "
                        "de sécurité médicale. Cela peut indiquer une perte "
                        "d'information critique (posologie, négation, etc.)."
                    )
                }
            )
        
        # ÉTAPE 5: SUCCÈS - RETOURNER LA TRADUCTION
        elapsed_time = (time.time() - start_time) * 1000
        
        logger.info(
            f"[{request_id}] ✅ Traduction réussie en {elapsed_time:.2f}ms"
        )
        
        # Logger la réponse de succès
        monitor.log_response(
            request_id=request_id,
            success=True,
            translation_time_ms=elapsed_time,
            translated_text=translated_text,
            safety_warnings=safety_result.warnings
        )
        
        return TranslationResponse(
            request_id=request_id,
            source_text=request.text,
            translated_text=translated_text,
            source_lang=request.source_lang,
            target_lang=request.target_lang,
            translation_time_ms=elapsed_time,
            safety_warnings=safety_result.warnings
        )
    
    except HTTPException:
        # Re-lever les HTTPException (déjà gérées)
        raise
    
    except Exception as e:
        # Erreur inattendue
        elapsed_time = (time.time() - start_time) * 1000
        
        logger.exception(f"[{request_id}] ❌ ERREUR INATTENDUE: {str(e)}")
        
        # Logger l'erreur
        monitor.log_response(
            request_id=request_id,
            success=False,
            translation_time_ms=elapsed_time,
            error_code="INTERNAL_ERROR",
            error_message=str(e)
        )
        
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "request_id": request_id,
                "error_code": "INTERNAL_ERROR",
                "error_message": "Une erreur interne est survenue",
                "details": str(e)
            }
        )


# EXCEPTION HANDLERS

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """
    Handler global pour toutes les exceptions non gérées.
    """
    request_id = getattr(request.state, "request_id", "unknown")
    
    logger.exception(f"[{request_id}] Exception non gérée: {str(exc)}")
    
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "request_id": request_id,
            "error_code": "UNHANDLED_EXCEPTION",
            "error_message": "Une erreur interne est survenue",
            "details": str(exc)
        }
    )


# POINT D'ENTRÉE

if __name__ == "__main__":
    import uvicorn
    
    logger.info("🚀 Lancement du serveur FastAPI...")
    
    uvicorn.run(
        "app:app",
        host="0.0.0.0",
        port=8000,
        reload=False,  # Pas de reload en production
        log_level="info"
    )