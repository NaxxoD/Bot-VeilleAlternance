"""Point d'entrée : python -m veille_alternance"""

import json
import logging
import sys
import time
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

from veille_alternance.client import ApiError, LbaClient
from veille_alternance.collect import collecter, collecter_ft
from veille_alternance.config import RACINE, Config, ConfigError, charger_config
from veille_alternance.ft_client import FtClient
from veille_alternance.history import (
    charger_historique,
    marquer_nouveautes,
    offres_disparues,
    sauvegarder_historique,
    trier_nouvelles_en_tete,
)
from veille_alternance.normalize import normaliser_reponse, normaliser_reponse_ft
from veille_alternance.output import (
    COLONNES_OFFRES,
    COLONNES_RECRUTEURS,
    ecrire_csv,
    ecrire_json,
)
from veille_alternance.rapport import ecrire_html
from veille_alternance.process import (
    dedupliquer_offres,
    dedupliquer_par_contenu,
    dedupliquer_recruteurs,
    filtrer_contrat,
    filtrer_ecoles,
    classer_familles,
    filtrer_mots_cles,
    filtrer_recruteurs,
    trier_recruteurs,
)
from veille_alternance.trajet import (
    CacheTrajets,
    ClientTransports,
    ClientVoiture,
    Geocodeur,
    Trajets,
)

journal = logging.getLogger("veille_alternance")


def executer(
    config: Config,
    client,
    dossier_sortie: Path,
    horodatage: str,
    jour: str,
    *,
    chemin_historique: Path,
    client_ft=None,
    trajets=None,
    sleep: Callable[[float], None] = time.sleep,
) -> tuple[Path, Path]:
    # France Travail d'abord : pour une offre présente dans les deux sources, la
    # déduplication garde la première vue, et la version directe est plus complète.
    offres = []
    if config.ft_actif and client_ft is not None:
        for departement, reponse in collecter_ft(
            client_ft, config.departements, config.ft_nature_contrat,
            config.dossier_raw, horodatage,
        ):
            offres.extend(normaliser_reponse_ft(reponse, departement))
    total_ft = len(offres)

    reponses = collecter(
        client, config.departements, config.romes, config.dossier_raw,
        config.pause_entre_appels, horodatage, sleep=sleep,
    )
    recruteurs = []
    for departement, reponse in reponses:
        offres_dep, recruteurs_dep = normaliser_reponse(reponse, departement)
        offres.extend(offres_dep)
        recruteurs.extend(recruteurs_dep)
    journal.info("Sources : %d offres France Travail, %d LBA", total_ft, len(offres) - total_ft)

    total_brut = len(offres)
    offres = dedupliquer_offres(offres)
    total_unique = len(offres)
    offres = filtrer_contrat(offres, config.types_contrat)
    offres = filtrer_ecoles(offres, config.ecoles_naf_prefixes, config.organismes_exclus)
    # Après le filtre contrat : sinon une version écartée (ex. professionnalisation)
    # d'une annonce en double peut éliminer la version qu'on veut garder.
    offres = dedupliquer_par_contenu(offres)
    # Vivier = toutes les offres éligibles AVANT le filtre par mots-clés. C'est
    # l'interface avec le projet parallèle Bot_Tri_Alternance (tri par IA).
    vivier = offres
    offres = filtrer_mots_cles(
        offres, config.mots_cles_titre + config.mots_cles_dev,
        config.mots_cles_description, config.mots_exclus_titre,
    )
    offres = classer_familles(offres, config.mots_cles_dev)
    # Après les mots-clés : ~20 offres à calculer au lieu de ~1 700. Les offres trop
    # loin ne sont pas notifiées.
    trop_loin = []
    if trajets is not None:
        offres, trop_loin = trajets.repartir(offres)
        journal.info(
            "Trajet : %d offres dans le périmètre, %d trop loin", len(offres), len(trop_loin)
        )
    recruteurs = dedupliquer_recruteurs(recruteurs)
    total_recruteurs = len(recruteurs)
    recruteurs = filtrer_recruteurs(recruteurs, config.naf_prefixes, config.tailles_exclues)
    trop_loin_recruteurs = []
    if trajets is not None:
        recruteurs, trop_loin_recruteurs = trajets.repartir(recruteurs)
    recruteurs = trier_recruteurs(recruteurs, config.naf_coeur)

    offres, historique = marquer_nouveautes(offres, charger_historique(chemin_historique), jour)
    # Les offres trop loin comptent comme vues : sinon elles passeraient pour disparues
    trop_loin, historique = marquer_nouveautes(trop_loin, historique, jour)
    offres = trier_nouvelles_en_tete(offres, jour)
    nouvelles = [offre for offre in offres if offre.premiere_vue == jour]
    sauvegarder_historique(historique, chemin_historique)
    disparues = offres_disparues(
        historique, jour, config.lancements_avant_disparition, config.jours_disparues
    )

    journal.info(
        "Offres : %d brutes, %d uniques, %d retenues après filtres, dont %d nouvelles",
        total_brut, total_unique, len(offres), len(nouvelles),
    )
    journal.info(
        "Recruteurs : %d uniques, %d retenus après filtres, %d trop loin",
        total_recruteurs, len(recruteurs), len(trop_loin_recruteurs),
    )
    journal.info("Disparues récemment : %d offres", len(disparues))

    chemin_offres = ecrire_json(offres, dossier_sortie / f"offres_{jour}.json")
    chemin_recruteurs = ecrire_json(recruteurs, dossier_sortie / f"recruteurs_{jour}.json")
    csv_offres = ecrire_csv(offres, dossier_sortie / f"offres_{jour}.csv", COLONNES_OFFRES)
    csv_nouvelles = ecrire_csv(
        nouvelles, dossier_sortie / f"nouvelles_offres_{jour}.csv", COLONNES_OFFRES
    )
    csv_recruteurs = ecrire_csv(
        recruteurs, dossier_sortie / f"recruteurs_{jour}.csv", COLONNES_RECRUTEURS
    )
    ecrire_json(vivier, dossier_sortie / f"pool_offres_{jour}.json")
    journal.info("Vivier (avant mots-clés) : %d offres", len(vivier))
    rapport = ecrire_html(
        offres, recruteurs, dossier_sortie / f"rapport_{jour}.html", jour,
        trop_loin=trop_loin, disparues=disparues, zones=config.zones,
    )
    # Copie sous un nom fixe : toujours le dernier rapport, à mettre en favori
    ecrire_html(
        offres, recruteurs, dossier_sortie / "rapport.html", jour,
        trop_loin=trop_loin, disparues=disparues, zones=config.zones,
    )
    # Résumé lu par scripts/notifier.ps1 pour la pop-up de fin de lancement
    resume = {
        "jour": jour,
        "nb_offres": len(offres),
        "nb_nouvelles": len(nouvelles),
        "nb_recruteurs": len(recruteurs),
        "nouvelles": [
            {"titre": o.titre, "entreprise": o.entreprise, "departement": o.departement}
            for o in nouvelles
        ],
        "rapport": str(dossier_sortie / "rapport.html"),
    }
    (dossier_sortie / "resume.json").write_text(
        json.dumps(resume, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    for chemin in (chemin_offres, chemin_recruteurs, csv_offres, csv_nouvelles, csv_recruteurs,
                   rapport):
        journal.info("Écrit : %s", chemin)
    return chemin_offres, chemin_recruteurs


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    try:
        config = charger_config()
        client = LbaClient(config.api_key, config.base_url, config.timeout)
        client_ft = (
            FtClient(config.ft_client_id, config.ft_client_secret, config.timeout)
            if config.ft_actif else None
        )
        trajets = (
            Trajets(
                config,
                Geocodeur(config.timeout),
                ClientTransports(config.prim_api_key, config.trajet_heure_depart, config.timeout),
                ClientVoiture(config.timeout),
                CacheTrajets(RACINE / "data" / "cache_trajets.json"),
            )
            if config.trajet_actif else None
        )
        maintenant = datetime.now()
        executer(
            config, client, RACINE / "data" / "processed",
            maintenant.strftime("%Y-%m-%d_%H%M%S"), maintenant.strftime("%Y-%m-%d"),
            chemin_historique=RACINE / "data" / "historique_offres.json",
            client_ft=client_ft,
            trajets=trajets,
        )
    except (ConfigError, ApiError) as erreur:
        journal.error("%s", erreur)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
