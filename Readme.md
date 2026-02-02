# 🏥 YAMA Medical Translation Service

Microservice de traduction médicale sécurisé **Wolof ⇄ Français** pour le projet Assistant Médical YAMA.

##  Objectif

Fournir un service de traduction **fiable et sécurisé** dans un pipeline RAG médical, avec protection des données critiques (posologies, médicaments, négations).

---

##  Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    CLIENT (RAG Pipeline)                    │
└─────────────────────┬───────────────────────────────────────┘
                      │ HTTP POST /translate
                      ▼
┌─────────────────────────────────────────────────────────────┐
│                     FastAPI Application                     │
│  ┌────────────────────────────────────────────────────────┐ │
│  │  1. Validation Input (injection, longueur, langue)    │ │
│  └────────────────────────────────────────────────────────┘ │
│                      ▼                                       │
│  ┌────────────────────────────────────────────────────────┐ │
│  │  2. Masquage éléments critiques (safety.py)           │ │
│  │     - Médicaments: Paracétamol → __MED_0_42__         │ │
│  │     - Posologies: 500mg → __DOS_1_58__                │ │
│  └────────────────────────────────────────────────────────┘ │
│                      ▼                                       │
│  ┌────────────────────────────────────────────────────────┐ │
│  │  3. Traduction (NLLB-200)                              │ │
│  │     - Texte masqué → Modèle → Texte traduit masqué    │ │
│  └────────────────────────────────────────────────────────┘ │
│                      ▼                                       │
│  ┌────────────────────────────────────────────────────────┐ │
│  │  4. Démasquage éléments critiques (safety.py)         │ │
│  │     - __MED_0_42__ → Paracétamol                       │ │
│  │     - __DOS_1_58__ → 500mg                             │ │
│  └────────────────────────────────────────────────────────┘ │
│                      ▼                                       │
│  ┌────────────────────────────────────────────────────────┐ │
│  │  5. Vérifications de Sécurité (safety.py)             │ │
│  │     ✓ Intégrité numérique (tous les chiffres intacts) │ │
│  │     ✓ Négations préservées (ne pas, bul, etc.)        │ │
│  │     ✓ Placeholders réinsérés correctement             │ │
│  └────────────────────────────────────────────────────────┘ │
│                      ▼                                       │
│  ┌────────────────────────────────────────────────────────┐ │
│  │  6. Retour JSON (succès ou erreur 422)                │ │
│  └────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────────────────────┐
│               Monitoring & Logging (monitoring.py)          │
│  - Tous les événements loggés (fichier + console)          │
│                                   │
│  - Audit trail des violations de sécurité                   │
└─────────────────────────────────────────────────────────────┘
```

---

## 🔒 Principes de Sécurité

### 1. **Fail-Safe**
- En cas de doute → **REJETER** la traduction
- Mieux vaut une erreur qu'une donnée médicale corrompue

### 2. **Immutabilité des Données Critiques**
- Médicaments : **JAMAIS traduits** (masqués puis réinjectés)
- Posologies : **JAMAIS traduites** (masqués puis réinjectées)
- Négations : **TOUJOURS surveillées** (perte = rejet immédiat)

### 3. **Traçabilité Totale**
- Chaque requête a un `request_id` unique
- Tous les événements sont loggés (fichier + console)
- Les violations de sécurité sont loggées en **CRITICAL**

---

## 📦 Installation

### Prérequis
- Python 3.10+
- CUDA (optionnel, pour GPU)
- 4 GB RAM minimum (8 GB recommandé)

### Étape 1 : Cloner et installer

```bash
# Installer les dépendances
pip install -r requirements.txt --break-system-packages

# Pour GPU avec CUDA 11.8
pip install torch==2.1.2 --index-url https://download.pytorch.org/whl/cu118

# Pour CPU uniquement
pip install torch==2.1.2 --index-url https://download.pytorch.org/whl/cpu
```

### Étape 2 : Lancer le service

```bash
# Lancement simple
python app.py

# Lancement avec Uvicorn (production)
uvicorn app:app --host 0.0.0.0 --port 8000 --workers 4
```

Le service sera accessible sur `http://localhost:8000`

---

## 🚀 Utilisation

### Endpoint principal : `/translate`

#### Exemple 1 : Wolof → Français

```bash
curl -X POST "http://localhost:8000/translate" \
  -H "Content-Type: application/json" \
  -d '{
    "text": "Jelel paracétamol 500mg, ñetti yoon ci bés.",
    "source_lang": "wol_Latn",
    "target_lang": "fra_Latn"
  }'
```

**Réponse attendue :**
```json
{
  "request_id": "a7b3c8d9-1234-5678-abcd-ef1234567890",
  "source_text": "Jelel paracétamol 500mg, ñetti yoon ci bés.",
  "translated_text": "Prenez paracétamol 500mg, trois fois par jour.",
  "source_lang": "wol_Latn",
  "target_lang": "fra_Latn",
  "translation_time_ms": 245.67,
  "safety_warnings": []
}
```

**Note :** `paracétamol` et `500mg` n'ont **PAS été traduits** - ils ont été protégés.

---

#### Exemple 2 : Français → Wolof

```bash
curl -X POST "http://localhost:8000/translate" \
  -H "Content-Type: application/json" \
  -d '{
    "text": "Ne prenez pas d'\''aspirine avec ce médicament.",
    "source_lang": "fra_Latn",
    "target_lang": "wol_Latn"
  }'
```

**Réponse attendue :**
```json
{
  "request_id": "b8c4d9e0-2345-6789-bcde-fg2345678901",
  "source_text": "Ne prenez pas d'aspirine avec ce médicament.",
  "translated_text": "Bul naan aspirine ak garp gi",
  "source_lang": "fra_Latn",
  "target_lang": "wol_Latn",
  "translation_time_ms": 198.34,
  "safety_warnings": []
}
```

**Note :** La négation `ne... pas` a été préservée (`bul` en wolof).

---

#### Exemple 3 : Violation de sécurité (négation perdue)

```bash
curl -X POST "http://localhost:8000/translate" \
  -H "Content-Type: application/json" \
  -d '{
    "text": "Ne jamais dépasser 3 comprimés par jour.",
    "source_lang": "fra_Latn",
    "target_lang": "wol_Latn"
  }'
```

**Si la négation est perdue, réponse 422 :**
```json
{
  "detail": {
    "request_id": "c9d5e1f2-3456-7890-cdef-gh3456789012",
    "error_code": "NEGATION_LOSS",
    "error_message": "SÉCURITÉ CRITIQUE: Négation perdue en traduction. Négations source détectées: ['ne jamais'] | Aucune négation trouvée dans la traduction.",
    "details": "La traduction a été rejetée car elle viole les règles de sécurité médicale..."
  }
}
```

---

### Autres endpoints

#### Statistiques
```bash
curl http://localhost:8000/statistics
```

#### Documentation interactive (Swagger)
Ouvrez dans votre navigateur : `http://localhost:8000/docs`

---

## 📊 Monitoring

### Logs

Tous les événements sont loggés dans :
- **Console** (niveau INFO et plus)
- **Fichier `medical_translation.log`** (niveau DEBUG et plus)

### Format de log

```
2026-01-27 14:32:10 | INFO     | app | 📥 REQUÊTE [a7b3c8d9-1234] | wol_Latn→fra_Latn | Longueur: 45 chars
2026-01-27 14:32:10 | DEBUG    | safety | Éléments protégés extraits: {...}
2026-01-27 14:32:10 | INFO     | safety | 2 éléments protégés masqués
2026-01-27 14:32:10 | DEBUG    | app | Traduction brute: Prenez __MED_0_8__ __DOS_1_20__...
2026-01-27 14:32:10 | INFO     | safety | ✅ Vérification de sécurité: TOUTES LES CHECKS PASSÉES
2026-01-27 14:32:10 | INFO     | app | ✅ Traduction réussie en 245.67ms
```

### Statistiques temps réel

```bash
curl http://localhost:8000/statistics
```

Retourne :
```json
{
  "total_requests": 1523,
  "total_successes": 1498,
  "total_failures": 25,
  "total_safety_violations": 12,
  "success_rate_percent": 98.36,
  "performance": {
    "avg_translation_time_ms": 234.56,
    "min_translation_time_ms": 89.23,
    "max_translation_time_ms": 987.45
  }
}
```


### Déploiement Docker (exemple)

```dockerfile
FROM python:3.10-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install -r requirements.txt --break-system-packages

COPY . .

EXPOSE 8000

CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]
```

### Structure du code

```
├── app.py              # Application FastAPI principale
├── config.py           # Configuration et constantes
├── safety.py           # Logique de sécurité médicale
├── monitoring.py       # Logging et statistiques
├── requirements.txt    # Dépendances Python
└── README.md          # Cette documentation
```

