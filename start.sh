#!/bin/bash

# ============================================================================
# YAMA Medical Translation Service - Script de Démarrage
# ============================================================================
#
# Ce script facilite le démarrage du service avec différentes configurations.
#
# Usage:
#   ./start.sh [dev|prod|test]
#
# Modes:
#   dev  - Mode développement (reload activé, logs verbeux)
#   prod - Mode production (multiple workers, logs optimisés)
#   test - Mode test (charge curl_examples.sh)
#
# ============================================================================

set -e  # Arrêter en cas d'erreur

# Couleurs pour les logs
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Fonction de logging
log() {
    echo -e "${GREEN}[$(date +'%Y-%m-%d %H:%M:%S')]${NC} $1"
}

error() {
    echo -e "${RED}[ERROR]${NC} $1" >&2
}

warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

# Vérifier que Python est installé
check_python() {
    if ! command -v python3 &> /dev/null; then
        error "Python 3 n'est pas installé"
        exit 1
    fi
    
    PYTHON_VERSION=$(python3 --version | cut -d' ' -f2)
    log "Python version: $PYTHON_VERSION"
}

# Vérifier que les dépendances sont installées
check_dependencies() {
    log "Vérification des dépendances..."
    
    if ! python3 -c "import fastapi" 2>/dev/null; then
        error "FastAPI n'est pas installé"
        error "Lancez: pip install -r requirements.txt --break-system-packages"
        exit 1
    fi
    
    if ! python3 -c "import torch" 2>/dev/null; then
        error "PyTorch n'est pas installé"
        error "Lancez: pip install -r requirements.txt --break-system-packages"
        exit 1
    fi
    
    log "✅ Dépendances OK"
}

# Vérifier la disponibilité GPU
check_gpu() {
    if python3 -c "import torch; print(torch.cuda.is_available())" | grep -q "True"; then
        GPU_NAME=$(python3 -c "import torch; print(torch.cuda.get_device_name(0))")
        log "🎮 GPU détecté: $GPU_NAME"
    else
        warning "⚠️  Pas de GPU détecté, utilisation du CPU (plus lent)"
    fi
}

# Créer le fichier .env s'il n'existe pas
#setup_env() {
 #   if [ ! -f .env ]; then
  #      warning "Fichier .env non trouvé"
   #     info "Copie de .env.example vers .env..."
   #     cp .env.example .env
   #     warning "⚠️  Pensez à adapter les valeurs dans .env selon votre environnement"
   # fi
#} 

# Mode développement
start_dev() {
    log "🚀 Démarrage en mode DÉVELOPPEMENT"
    log "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    
    export LOG_LEVEL=DEBUG
    export RELOAD=true
    
    info "Logs: DEBUG"
    info "Reload: Activé"
    info "Workers: 1"
    
    log "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    
    # Lancer avec Uvicorn en mode reload
    python3 -m uvicorn app:app \
        --host 0.0.0.0 \
        --port 8000 \
        --reload \
        --log-level debug
}

# Mode production
start_prod() {
    log "🚀 Démarrage en mode PRODUCTION"
    log "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    
    export LOG_LEVEL=INFO
    export RELOAD=false
    
    # Déterminer le nombre de workers (2 x cores + 1)
    WORKERS=$(python3 -c "import os; print((os.cpu_count() or 1) * 2 + 1)")
    
    info "Logs: INFO"
    info "Reload: Désactivé"
    info "Workers: $WORKERS"
    
    warning "⚠️  MODE PRODUCTION: Assurez-vous d'avoir configuré:"
    warning "   - ALLOWED_ORIGINS dans .env"
    warning "   - ENABLE_AUTH=true"
    warning "   - SECRET_KEY"
    
    log "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    
    # Lancer avec Uvicorn en mode production
    python3 -m uvicorn app:app \
        --host 0.0.0.0 \
        --port 8000 \
        --workers "$WORKERS" \
        --log-level info \
        --no-access-log  # Les logs sont gérés par notre système
}

# Mode test
start_test() {
    log "🧪 Démarrage en mode TEST"
    log "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    
    # Vérifier que le service est déjà lancé
    if ! curl -s http://localhost:8000/health > /dev/null 2>&1; then
        error "Le service n'est pas lancé"
        error "Lancez d'abord: ./start.sh dev (dans un autre terminal)"
        exit 1
    fi
    
    log "✅ Service détecté sur http://localhost:8000"
    
    # Vérifier que curl_examples.sh existe et est exécutable
    if [ ! -f curl_examples.sh ]; then
        error "curl_examples.sh non trouvé"
        exit 1
    fi
    
    if [ ! -x curl_examples.sh ]; then
        info "Ajout des permissions d'exécution à curl_examples.sh..."
        chmod +x curl_examples.sh
    fi
    
    log "🚀 Lancement des tests..."
    log "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    
    ./curl_examples.sh
}

# Afficher l'aide
show_help() {
    cat << EOF
Usage: $0 [mode]

Modes disponibles:
  dev   - Mode développement (reload activé, logs DEBUG)
  prod  - Mode production (multiple workers, logs INFO)
  test  - Mode test (exécute curl_examples.sh)
  help  - Affiche cette aide

Exemples:
  $0 dev          # Démarrage en mode développement
  $0 prod         # Démarrage en mode production
  $0 test         # Lancement des tests (nécessite service démarré)

Avant le premier lancement:
  1. Installer les dépendances: pip install -r requirements.txt --break-system-packages
  2. Configurer .env (copie de .env.example)
  3. Vérifier la configuration GPU/CPU

EOF
}

# ============================================================================
# MAIN
# ============================================================================

main() {
    # Banner
    echo ""
    echo "╔═══════════════════════════════════════════════════════════════════╗"
    echo "║                                                                   ║"
    echo "║        🏥 YAMA MEDICAL TRANSLATION SERVICE 🏥                    ║"
    echo "║                                                                   ║"
    echo "║        Wolof ⇄ Français - Traduction Médicale Sécurisée         ║"
    echo "║                                                                   ║"
    echo "╚═══════════════════════════════════════════════════════════════════╝"
    echo ""
    
    # Vérifications préliminaires
    check_python
    check_dependencies
    check_gpu
    #setup_env
    
    echo ""
    
    # Déterminer le mode
    MODE="${1:-dev}"  # Par défaut: dev
    
    case "$MODE" in
        dev)
            start_dev
            ;;
        prod)
            start_prod
            ;;
        test)
            start_test
            ;;
        help|--help|-h)
            show_help
            ;;
        *)
            error "Mode inconnu: $MODE"
            echo ""
            show_help
            exit 1
            ;;
    esac
}

# Gestion des signaux (Ctrl+C)
trap 'echo ""; log "👋 Arrêt du service..."; exit 0' SIGINT SIGTERM

# Lancer le script
main "$@"