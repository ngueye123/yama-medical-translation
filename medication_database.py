"""
Module de gestion de la base de données médicamenteuse
Charge et gère une liste complète de médicaments pour la détection
"""

import re
import json
from pathlib import Path
from typing import Set, List
import logging

logger = logging.getLogger(__name__)


class MedicationDatabase:
    """
    Base de données de médicaments pour détection et protection.
    
    """
    
    def __init__(self, medication_file: str = None):
        """
        Initialise la base de données.
        
        Args:
            medication_file: Chemin vers un fichier JSON contenant les médicaments
        """
        # Ensemble pour recherche rapide O(1)
        self.medications: Set[str] = set()
        
        # Noms normalisés (minuscules, sans accents)
        self.normalized_medications: Set[str] = set()
        
        # Pattern regex compilé (sera généré dynamiquement)
        self.medication_pattern = None
        
        # Charger les médicaments par défaut
        self._load_default_medications()
        
        # Charger depuis un fichier si fourni
        if medication_file and Path(medication_file).exists():
            self.load_from_file(medication_file)
        
        # Compiler le pattern regex
        self._compile_pattern()
        
        logger.info(f"Base de données médicamenteuse chargée: {len(self.medications)} médicaments")
    
    def _load_default_medications(self):
        """
        Charge une liste par défaut de médicaments courants.
        Cette liste peut être étendue ou remplacée.
        """
        # DCI (Dénomination Commune Internationale) les plus courants
        dci_common = [
            # Antalgiques / Anti-inflammatoires
            "paracétamol", "paracetamol", "acetaminophen",
            "ibuprofène", "ibuprofen", "ibuprofene",
            "aspirine", "aspirin", "acide acétylsalicylique",
            "codéine", "codeine",
            "tramadol",
            "morphine",
            
            # Antibiotiques
            "amoxicilline", "amoxicillin",
            "azithromycine", "azithromycin",
            "ciprofloxacine", "ciprofloxacin",
            "métronidazole", "metronidazole",
            "doxycycline",
            "ceftriaxone",
            "pénicilline", "penicillin",
            
            # Antipaludéens (important pour le Sénégal)
            "artemether", "artémether",
            "lumefantrine", "luméfantrine",
            "chloroquine",
            "quinine",
            "méfloquine", "mefloquine",
            "atovaquone",
            "proguanil",
            
            # Antidiabétiques
            "metformine", "metformin",
            "glibenclamide",
            "insuline", "insulin",
            
            # Cardiovasculaires
            "amlodipine",
            "atenolol", "aténolol",
            "lisinopril",
            "furosémide", "furosemide",
            "hydrochlorothiazide",
            
            # Antihistaminiques
            "cétirizine", "cetirizine",
            "loratadine",
            "chlorphéniramine", "chlorpheniramine",
            
            # Autres
            "oméprazole", "omeprazole",
            "ranitidine",
            "salbutamol",
            "prednisolone",
            "diazépam", "diazepam",
        ]
        
        # Noms commerciaux courants
        brand_names = [
            # Paracétamol
            "Doliprane", "Efferalgan", "Dafalgan", "Dolko",
            
            # Ibuprofène
            "Advil", "Nurofen", "Brufen",
            
            # Autres
            "Flagyl",  # métronidazole
            "Amoxil",  # amoxicilline
            "Coartem", "Riamet",  # artemether-lumefantrine
            "Malarone",  # atovaquone-proguanil
            "Glucophage",  # metformine
            "Ventolin",  # salbutamol
        ]
        
        # Ajouter tous les médicaments
        for med in dci_common + brand_names:
            self.add_medication(med)
    
    def add_medication(self, medication: str):
        """
        Ajoute un médicament à la base de données.
        
        Args:
            medication: Nom du médicament
        """
        # Ajouter le nom original
        self.medications.add(medication)
        
        # Ajouter la version normalisée (minuscules)
        normalized = medication.lower()
        self.normalized_medications.add(normalized)
        
        # Variations courantes (avec/sans accents)
        # Exemple: métronidazole → metronidazole
        normalized_no_accent = self._remove_accents(medication.lower())
        if normalized_no_accent != normalized:
            self.normalized_medications.add(normalized_no_accent)
    
    def load_from_file(self, filepath: str):
        """
        Charge les médicaments depuis un fichier JSON.
        
        Format attendu:
        {
          "medications": [
            {"name": "paracétamol", "category": "antalgique"},
            {"name": "Doliprane", "category": "antalgique", "dci": "paracétamol"},
            ...
          ]
        }
        
        Args:
            filepath: Chemin vers le fichier JSON
        """
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            if 'medications' in data:
                for med in data['medications']:
                    if isinstance(med, dict):
                        self.add_medication(med['name'])
                        # Ajouter aussi le DCI si fourni
                        if 'dci' in med:
                            self.add_medication(med['dci'])
                    else:
                        self.add_medication(med)
            
            logger.info(f"Chargement depuis {filepath}: {len(self.medications)} médicaments")
            
        except Exception as e:
            logger.error(f"Erreur lors du chargement de {filepath}: {e}")
    
    def save_to_file(self, filepath: str):
        """
        Sauvegarde la base de données dans un fichier JSON.
        
        Args:
            filepath: Chemin de destination
        """
        data = {
            "medications": sorted(list(self.medications))
        }
        
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        
        logger.info(f"Base sauvegardée dans {filepath}")
    
    def _compile_pattern(self):
        """
        Compile un pattern regex à partir de tous les médicaments.
        Utilise le Trie pour optimisation.
        """
        if not self.medications:
            self.medication_pattern = re.compile(r'(?!)')  # Pattern qui ne match jamais
            return
        
        # Trier par longueur décroissante (matcher les plus longs d'abord)
        sorted_meds = sorted(self.medications, key=len, reverse=True)
        
        # Échapper les caractères spéciaux regex
        escaped_meds = [re.escape(med) for med in sorted_meds]
        
        # Créer le pattern avec word boundaries
        pattern_str = r'\b(?:' + '|'.join(escaped_meds) + r')\b'
        
        # Compiler avec IGNORECASE pour capturer variations
        self.medication_pattern = re.compile(pattern_str, re.IGNORECASE)
        
        logger.debug(f"Pattern regex compilé avec {len(self.medications)} médicaments")
    
    def find_medications(self, text: str) -> List[str]:
        """
        Trouve tous les médicaments dans un texte.
        
        Args:
            text: Texte à analyser
            
        Returns:
            Liste des médicaments trouvés
        """
        if not self.medication_pattern:
            return []
        
        return self.medication_pattern.findall(text)
    
    def is_medication(self, word: str) -> bool:
        """
        Vérifie si un mot est un médicament connu.
        
        Args:
            word: Mot à vérifier
            
        Returns:
            True si c'est un médicament connu
        """
        normalized = word.lower()
        return (
            normalized in self.normalized_medications or
            self._remove_accents(normalized) in self.normalized_medications
        )
    
    def _remove_accents(self, text: str) -> str:
        """
        Supprime les accents d'un texte.
        
        Args:
            text: Texte avec accents
            
        Returns:
            Texte sans accents
        """
        import unicodedata
        nfkd_form = unicodedata.normalize('NFKD', text)
        return ''.join([c for c in nfkd_form if not unicodedata.combining(c)])


# EXEMPLE D'UTILISATION

if __name__ == "__main__":
    # Créer la base de données
    db = MedicationDatabase()
    
    # Ajouter des médicaments supplémentaires
    db.add_medication("Coartem")
    db.add_medication("Malarone")
    
    # Tester la détection
    text = "Prenez du paracétamol 500mg et de l'ibuprofène si besoin"
    medications_found = db.find_medications(text)
    print(f"Médicaments trouvés: {medications_found}")
    # Output: ['paracétamol', 'ibuprofène']
    
    # Vérifier si un mot est un médicament
    print(f"'aspirine' est un médicament: {db.is_medication('aspirine')}")
    # Output: True
    
    # Sauvegarder dans un fichier
    db.save_to_file("medications_database.json")