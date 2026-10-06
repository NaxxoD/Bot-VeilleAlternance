"""Écriture des résultats : JSON complet et CSV lisible dans Excel."""

import csv
import json
from dataclasses import asdict
from pathlib import Path

COLONNES_OFFRES = [
    "premiere_vue", "departement", "famille", "titre", "entreprise", "adresse", "trajet_min",
    "anciennete_jours", "contrat", "niveau", "source", "relayee_par", "publiee_le", "url",
]
COLONNES_RECRUTEURS = [
    "departement", "nom", "adresse", "trajet_min", "taille", "secteur", "naf",
    "telephone", "site_web", "url",
]


def ecrire_json(elements: list, chemin: Path) -> Path:
    chemin.parent.mkdir(parents=True, exist_ok=True)
    donnees = [asdict(element) for element in elements]
    chemin.write_text(json.dumps(donnees, ensure_ascii=False, indent=2), encoding="utf-8")
    return chemin


def _valeur_csv(colonne: str, valeur) -> str:
    if valeur is None:
        return ""
    if isinstance(valeur, tuple):
        return ", ".join(valeur)
    if colonne == "publiee_le":
        return valeur[:10]  # "2026-09-03T16:31:40.837Z" → "2026-09-03"
    return str(valeur)


def ecrire_csv(elements: list, chemin: Path, colonnes: list[str]) -> Path:
    """CSV pour Excel en français : séparateur « ; » et BOM UTF-8 (utf-8-sig)."""
    chemin.parent.mkdir(parents=True, exist_ok=True)
    with open(chemin, "w", encoding="utf-8-sig", newline="") as fichier:
        ecrivain = csv.writer(fichier, delimiter=";")
        ecrivain.writerow(colonnes)
        for element in elements:
            donnees = asdict(element)
            ecrivain.writerow([_valeur_csv(c, donnees[c]) for c in colonnes])
    return chemin
