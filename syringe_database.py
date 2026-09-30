"""
syringe_database.py - Base de données des seringues de laboratoire (DecLiq - LIPhy).
Diamètres internes nominaux (en mm) calibrés selon les abaques KD Scientific & Harvard Apparatus.
"""
from typing import Dict, List, Optional, Tuple

CATALOGUE_SERINGUES: Dict[str, Dict[str, float]] = {
    # =========================================================================
    # 1. AIR-TITE HSW NORM-JECT (Plastique PP/PE sans huile silicone ni caoutchouc)
    # =========================================================================
    "Air-Tite HSW Norm-Ject": {
        "Air-Tite Norm-Ject 1 mL": 4.69,
        "Air-Tite Norm-Ject 2.5 mL": 9.65,
        "Air-Tite Norm-Ject 5 mL": 12.45,
        "Air-Tite Norm-Ject 10 mL": 15.90,
        "Air-Tite Norm-Ject 20 mL": 20.05,
        "Air-Tite Norm-Ject 30 mL": 22.90,
        "Air-Tite Norm-Ject 50 mL": 29.20,
    },

    # =========================================================================
    # 2. HAMILTON GASTIGHT (Séries 1700 & 1000 - Verre borosilicaté / Piston PTFE)
    # =========================================================================
    "Hamilton Gastight (Verre / PTFE)": {
        "Hamilton Gastight 10 µL": 0.485,
        "Hamilton Gastight 25 µL": 0.729,
        "Hamilton Gastight 50 µL": 1.030,
        "Hamilton Gastight 100 µL": 1.457,
        "Hamilton Gastight 250 µL": 2.303,
        "Hamilton Gastight 500 µL": 3.257,
        "Hamilton Gastight 1 mL": 4.608,
        "Hamilton Gastight 2.5 mL": 7.284,
        "Hamilton Gastight 5 mL": 10.300,
        "Hamilton Gastight 10 mL": 14.570,
        "Hamilton Gastight 25 mL": 23.030,
        "Hamilton Gastight 50 mL": 32.570,
        "Hamilton Gastight 100 mL": 32.570,
    },

    # =========================================================================
    # 3. HAMILTON MICROLITER (Série 700 - Verre / Aiguille scellée)
    # =========================================================================
    "Hamilton 700 Microliter (Verre)": {
        "Hamilton 700 0.5 µL": 0.103,
        "Hamilton 700 1 µL": 0.145,
        "Hamilton 700 2 µL": 0.206,
        "Hamilton 700 5 µL": 0.343,
        "Hamilton 700 10 µL": 0.460,
        "Hamilton 700 25 µL": 0.729,
        "Hamilton 700 50 µL": 1.030,
        "Hamilton 700 100 µL": 1.457,
        "Hamilton 700 250 µL": 2.303,
        "Hamilton 700 500 µL": 3.257,
    },

    # =========================================================================
    # 4. BECTON DICKINSON (BD Plastipak / Luer-Lok - Polypropylène standard)
    # =========================================================================
    "BD Plastique (Plastipak)": {
        "BD Plastique 1 mL": 4.78,
        "BD Plastique 2 mL": 8.66,
        "BD Plastique 3 mL": 8.66,
        "BD Plastique 5 mL": 12.06,
        "BD Plastique 10 mL": 14.50,
        "BD Plastique 20 mL": 19.13,
        "BD Plastique 30 mL": 21.70,
        "BD Plastique 50 mL / 60 mL": 26.70,
    },

    # =========================================================================
    # 5. BECTON DICKINSON (BD Verre dépoli)
    # =========================================================================
    "BD Verre (Yale / Multifit)": {
        "BD Verre 0.5 mL": 4.64,
        "BD Verre 1 mL": 4.64,
        "BD Verre 2.5 mL": 8.66,
        "BD Verre 5 mL": 11.86,
        "BD Verre 10 mL": 14.34,
        "BD Verre 20 mL": 19.13,
        "BD Verre 30 mL": 22.70,
        "BD Verre 50 mL": 28.60,
        "BD Verre 100 mL": 34.90,
    },

    # =========================================================================
    # 6. B. BRAUN (Omnifix & Injekt)
    # =========================================================================
    "B. Braun (Injekt & Omnifix)": {
        "B. Braun Injekt 1 mL": 4.69,
        "B. Braun Injekt 2 mL": 9.65,
        "B. Braun Injekt 5 mL": 12.45,
        "B. Braun Injekt 10 mL": 15.90,
        "B. Braun Injekt 20 mL": 20.05,
        "B. Braun Omnifix 1 mL": 4.69,
        "B. Braun Omnifix 3 mL": 9.65,
        "B. Braun Omnifix 5 mL": 12.50,
        "B. Braun Omnifix 10 mL": 15.90,
        "B. Braun Omnifix 20 mL": 20.00,
        "B. Braun Omnifix 30 mL": 22.50,
        "B. Braun Omnifix 50 mL": 29.20,
    },

    # =========================================================================
    # 7. TERUMO (Plastique médical)
    # =========================================================================
    "Terumo Medical (Plastique)": {
        "Terumo 1 mL": 4.70,
        "Terumo 3 mL": 9.00,
        "Terumo 5 mL": 13.00,
        "Terumo 10 mL": 15.80,
        "Terumo 20 mL": 20.10,
        "Terumo 30 mL": 23.10,
        "Terumo 50 mL / 60 mL": 29.70,
    },

    # =========================================================================
    # 8. SGE / TRAJAN (Verre analytique haute précision)
    # =========================================================================
    "SGE / Trajan (Verre)": {
        "SGE 0.5 µL": 0.10,
        "SGE 1 µL": 0.15,
        "SGE 5 µL": 0.34,
        "SGE 10 µL": 0.46,
        "SGE 25 µL": 0.73,
        "SGE 50 µL": 1.03,
        "SGE 100 µL": 1.46,
        "SGE 250 µL": 2.30,
        "SGE 500 µL": 3.26,
        "SGE 1 mL": 4.61,
        "SGE 2.5 mL": 7.28,
        "SGE 5 mL": 10.30,
        "SGE 10 mL": 14.57,
        "SGE 25 mL": 23.03,
        "SGE 50 mL": 32.57,
        "SGE 100 mL": 32.57,
    },

    # =========================================================================
    # 9. MONOJECT / COVIDIEN / SHERWOOD (Plastique)
    # =========================================================================
    "Monoject (Covidien / Sherwood)": {
        "Monoject 1 mL": 4.67,
        "Monoject 3 mL": 8.86,
        "Monoject 6 mL": 12.65,
        "Monoject 12 mL": 15.72,
        "Monoject 20 mL": 20.12,
        "Monoject 35 mL": 23.67,
        "Monoject 60 mL": 26.64,
        "Monoject 140 mL": 37.95,
    },

    # =========================================================================
    # 10. CADENCE SCIENCE / POPPER & SONS (Micro-Mate Verre)
    # =========================================================================
    "Cadence Science (Micro-Mate Verre)": {
        "Micro-Mate 0.25 mL": 3.47,
        "Micro-Mate 0.5 mL": 3.47,
        "Micro-Mate 1 mL": 4.62,
        "Micro-Mate 2 mL": 8.92,
        "Micro-Mate 3 mL": 8.92,
        "Micro-Mate 5 mL": 11.75,
        "Micro-Mate 10 mL": 14.70,
        "Micro-Mate 20 mL": 19.58,
        "Micro-Mate 30 mL": 22.70,
        "Micro-Mate 50 mL": 28.60,
        "Micro-Mate 100 mL": 35.70,
    },

    # =========================================================================
    # 11. KLOEHN (Verre analytique)
    # =========================================================================
    "Kloehn (Verre)": {
        "Kloehn 10 µL": 0.46,
        "Kloehn 25 µL": 0.73,
        "Kloehn 50 µL": 1.03,
        "Kloehn 100 µL": 1.46,
        "Kloehn 250 µL": 2.30,
        "Kloehn 500 µL": 3.26,
        "Kloehn 1 mL": 4.61,
        "Kloehn 2.5 mL": 7.28,
        "Kloehn 5 mL": 10.30,
        "Kloehn 10 mL": 14.57,
        "Kloehn 25 mL": 23.03,
        "Kloehn 50 mL": 32.57,
    },

    # =========================================================================
    # 12. RANFAC (Verre)
    # =========================================================================
    "Ranfac (Verre)": {
        "Ranfac 2 mL": 9.12,
        "Ranfac 5 mL": 12.34,
        "Ranfac 10 mL": 14.55,
        "Ranfac 20 mL": 19.86,
        "Ranfac 30 mL": 23.20,
        "Ranfac 50 mL": 27.60,
    },

    # =========================================================================
    # 13. TOP (Plastique)
    # =========================================================================
    "Top (Plastique)": {
        "Top 1 mL": 4.70,
        "Top 2 mL": 6.40,
        "Top 3 mL": 9.30,
        "Top 6 mL": 13.10,
        "Top 12 mL": 15.40,
        "Top 20 mL": 19.30,
        "Top 30 mL": 23.40,
        "Top 50 mL": 29.10,
    },

    # =========================================================================
    # 14. UNIMETRICS (Micro-seringues verre)
    # =========================================================================
    "Unimetrics (Verre)": {
        "Unimetrics 10 µL": 0.46,
        "Unimetrics 25 µL": 0.73,
        "Unimetrics 50 µL": 1.03,
        "Unimetrics 100 µL": 1.46,
        "Unimetrics 250 µL": 2.30,
        "Unimetrics 500 µL": 3.26,
        "Unimetrics 1 mL": 4.61,
    }
}

# Table plate pour consultation directe O(1)
TABLE_PLATE: Dict[str, float] = {
    nom: diam
    for groupe in CATALOGUE_SERINGUES.values()
    for nom, diam in groupe.items()
}

OPTION_PERSONNALISEE = "Diamètre personnalisé..."


def get_marques() -> List[str]:
    """Retourne la liste des fabricants répertoriés."""
    return list(CATALOGUE_SERINGUES.keys())


def get_seringues_par_marque(marque: str) -> Dict[str, float]:
    """Renvoie le sous-dictionnaire des seringues pour une marque donnée."""
    return CATALOGUE_SERINGUES.get(marque, {})


def get_tous_les_modeles() -> List[str]:
    """Retourne l'ensemble des modèles triés avec l'option personnalisée."""
    modeles = sorted(list(TABLE_PLATE.keys()))
    modeles.append(OPTION_PERSONNALISEE)
    return modeles


def get_diametre(nom_modele: str, defaut: float = 4.608) -> Optional[float]:
    """
    Renvoie le diamètre intérieur en mm correspondant au modèle.
    Renvoie None s'il s'agit d'un diamètre libre sur-mesure.
    """
    if nom_modele == OPTION_PERSONNALISEE:
        return None
    return TABLE_PLATE.get(nom_modele, defaut)


def formater_nom_complet(nom_modele: str) -> str:
    """Affiche le modèle avec son diamètre calibré entre parenthèses."""
    if nom_modele in TABLE_PLATE:
        return f"{nom_modele} (Ø {TABLE_PLATE[nom_modele]:.3f} mm)"
    return nom_modele