# 🇸🇳 YAMA - Système de Traduction Médicale Wolof ⇄ Français

## 🎯 À Propos

YAMA est un **microservice de traduction médicale** spécialisé pour le contexte sénégalais. Il traduit de manière **sécurisée** entre le **Wolof** et le **Français**, tout en préservant l'intégrité des informations médicales critiques.

### ✨ Caractéristiques Principales

- 🔒 **Protection des médicaments** : 788 médicaments de la Liste National des Médicaments Essentiiel du Sénégal 2022
- 💊 **Préservation des dosages** : 500mg reste toujours 500mg
- ✅ **Vérification d'intégrité** : 5 niveaux de contrôle de sécurité
- 🔄 **Restauration automatique** : Correction des erreurs du modèle
- 🌍 **Contexte local** : Antipaludéens et médicaments essentiels sénégalais



## 🚀 Installation Rapide

```bash
# 1. Cloner le dépôt
git clone https://github.com/ngueye123/yama-medical-translation.git
cd yama-medical-translation

#Creer un environnement virtuel
python3 -m venv venv
#Activer l'environnement virtuel
source venv/bin/activate

# 2. Installer les dépendances
pip install -r requirements.txt --break-system-packages

# 3. Tester l'installation
python3 test_medication_db.py

# 4. Démarrer le service
./start.sh dev
```

Le service sera accessible sur `http://localhost:8000/docs`

---

## 💡 Utilisation

### Exemple Simple

```bash
curl -X POST "http://localhost:8000/translate" \
  -H "Content-Type: application/json" \
  -d '{
    "text": "Dafay naan Amoxicilline 500mg ñaari yoon ci bés bi",
    "source_lang": "wol_Latn",
    "target_lang": "fra_Latn"
  }'
```

**Réponse :**
```json
{
  "translated_text": "Il doit prendre Amoxicilline 500mg deux fois par jour",
  "translation_time_ms": 245,
  "safety_warnings": []
}
```

✅ **Notez que** :
- `Amoxicilline` (médicament) n'est pas traduit
- `500mg` (dosage) est préservé exactement
- La traduction est sûre et validée

---

## 💊 Base de Données Médicamenteuse

### 788 Médicaments - LNME Sénégal 2022

La base contient **100%** des médicaments de la Liste Nationale des Médicaments Essentiels du Sénégal.


---

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────┐
│              YAMA API (FastAPI)                 │
├─────────────────────────────────────────────────┤
│                                                 │
│  ┌──────────┐  ┌──────────┐  ┌──────────────┐ │
│  │ Requête  │→ │Traduction│→ │Vérification  │ │
│  │ Wolof/FR │  │ NLLB-200 │  │  Sécurité    │ │
│  └──────────┘  └──────────┘  └──────────────┘ │
│         │             │               │         │
│         └─────────────┴───────────────┘         │
│                       ↓                         │
│           MedicalSafetyChecker                  │
│           • 788 médicaments LNME                │
│           • Vérification dosages                │
│           • Restauration auto                   │
│                                                 │
└─────────────────────────────────────────────────┘
```

### Composants

| Fichier | Description |
|---------|-------------|
| `app.py` | API FastAPI + logique traduction |
| `safety.py` | Vérifications sécurité médicale |
| `medication_database.py` | Gestion base médicaments |
| `config.py` | Configuration système |
| `monitoring.py` | Logs et métriques |

---

## 🛡️ Sécurité Médicale

### 5 Niveaux de Protection

1. **Intégrité Numérique** : 500mg → 500mg (jamais modifié)
2. **Préservation Négation** : "ne pas" reste "ne pas"
3. **Anomalies Longueur** : Détection textes suspects
4. **Intégrité Placeholders** : Médicaments bien restaurés
5. **Restauration Auto** : Correction erreurs modèle
