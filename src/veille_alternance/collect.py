"""Collecte : un appel par département, sauvegarde des réponses brutes."""

import json
import logging
import time
from collections import Counter
from collections.abc import Callable
from pathlib import Path

PLAFOND_PAR_SOURCE = 150
SOURCES_NOMMEES = ("offres_emploi_lba", "France Travail")

journal = logging.getLogger(__name__)


def sources_saturees(reponse: dict) -> list[str]:
    """Sources d'offres ayant atteint le plafond de 150 (des offres sont perdues)."""
    compte = Counter(
        label if label in SOURCES_NOMMEES else "partenaires"
        for label in (job["identifier"]["partner_label"] for job in reponse["jobs"])
    )
    return sorted(source for source, n in compte.items() if n >= PLAFOND_PAR_SOURCE)


def collecter(
    client,
    departements: list[str],
    romes: list[str],
    dossier_raw: Path,
    pause: float,
    horodatage: str,
    sleep: Callable[[float], None] = time.sleep,
) -> list[tuple[str, dict]]:
    dossier_raw.mkdir(parents=True, exist_ok=True)
    resultats = []
    for index, departement in enumerate(departements):
        if index > 0:
            sleep(pause)
        reponse = client.search(departement, romes)
        chemin = dossier_raw / f"{horodatage}_dep{departement}.json"
        chemin.write_text(json.dumps(reponse, ensure_ascii=False), encoding="utf-8")
        journal.info(
            "Département %s : %d offres, %d recruteurs",
            departement, len(reponse["jobs"]), len(reponse["recruiters"]),
        )
        for source in sources_saturees(reponse):
            journal.warning("Département %s : source %s saturée (150)", departement, source)
        resultats.append((departement, reponse))
    return resultats


def collecter_ft(
    client_ft,
    departements: list[str],
    nature_contrat: str,
    dossier_raw: Path,
    horodatage: str,
) -> list[tuple[str, dict]]:
    """France Travail : toutes les offres de chaque département (la pagination et le
    rythme des appels sont gérés par le client)."""
    dossier_raw.mkdir(parents=True, exist_ok=True)
    resultats = []
    for departement in departements:
        reponse = client_ft.search(departement, nature_contrat)
        chemin = dossier_raw / f"{horodatage}_ft_dep{departement}.json"
        chemin.write_text(json.dumps(reponse, ensure_ascii=False), encoding="utf-8")
        journal.info(
            "France Travail département %s : %d offres", departement, len(reponse["resultats"])
        )
        resultats.append((departement, reponse))
    return resultats
