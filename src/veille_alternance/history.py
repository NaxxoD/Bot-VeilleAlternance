"""Historique des offres vues, d'un lancement à l'autre.

Format du fichier JSON :
    {"lancements": ["2026-09-26", ...],   dates des lancements, sans doublon
     "offres": {clé de contenu: {"premiere_vue", "derniere_vue", "titre",
                                 "entreprise", "departement", "adresse", "url"}}}
Une offre est nouvelle si sa première vue est aujourd'hui ; elle est disparue si
plusieurs lancements ont eu lieu depuis sa dernière vue.
"""

import json
from dataclasses import dataclass, replace
from datetime import date, timedelta
from pathlib import Path

from veille_alternance.normalize import Offre
from veille_alternance.process import cle_contenu


@dataclass(frozen=True)
class Disparue:
    titre: str
    entreprise: str | None
    departement: str
    adresse: str
    url: str
    premiere_vue: str
    derniere_vue: str


def historique_vide() -> dict:
    return {"lancements": [], "offres": {}}


def charger_historique(chemin: Path) -> dict:
    if not chemin.exists():
        return historique_vide()
    donnees = json.loads(chemin.read_text(encoding="utf-8"))
    if "offres" in donnees:
        return donnees
    # Ancien format (jusqu'au 2026-09-28) : clé → date de première vue, sans description
    return {
        "lancements": [],
        "offres": {cle: {"premiere_vue": vue, "derniere_vue": vue} for cle, vue in donnees.items()},
    }


def sauvegarder_historique(historique: dict, chemin: Path) -> Path:
    chemin.parent.mkdir(parents=True, exist_ok=True)
    chemin.write_text(
        json.dumps(historique, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8"
    )
    return chemin


def anciennete_jours(offre: Offre, jour: str) -> int | None:
    """Jours depuis la publication (date de la source), sinon depuis la première vue."""
    debut = (offre.publiee_le or offre.premiere_vue or "")[:10]
    if not debut:
        return None
    return max(0, (date.fromisoformat(jour) - date.fromisoformat(debut)).days)


def marquer_nouveautes(
    offres: list[Offre], historique: dict, jour: str
) -> tuple[list[Offre], dict]:
    """Renseigne premiere_vue et anciennete_jours sur chaque offre, et renvoie
    l'historique complété (lancement du jour, dernière vue, description)."""
    lancements = set(historique["lancements"]) | {jour}
    suivies = {cle: dict(infos) for cle, infos in historique["offres"].items()}
    marquees = []
    for offre in offres:
        infos = suivies.setdefault(cle_contenu(offre), {"premiere_vue": jour})
        infos.update(
            derniere_vue=jour, titre=offre.titre, entreprise=offre.entreprise,
            departement=offre.departement, adresse=offre.adresse, url=offre.url,
        )
        offre = replace(offre, premiere_vue=infos["premiere_vue"])
        marquees.append(replace(offre, anciennete_jours=anciennete_jours(offre, jour)))
    return marquees, {"lancements": sorted(lancements), "offres": suivies}


def trier_nouvelles_en_tete(offres: list[Offre], jour: str) -> list[Offre]:
    """Plus récent d'abord : date de première vue (les nouvelles du jour en tête), puis,
    à égalité, date de publication. Deux tris stables successifs : le second prime."""
    par_publication = sorted(offres, key=lambda offre: offre.publiee_le or "", reverse=True)
    return sorted(par_publication, key=lambda offre: offre.premiere_vue or "", reverse=True)


def offres_disparues(
    historique: dict, jour: str, lancements_avant_disparition: int, jours_disparues: int
) -> list[Disparue]:
    """Offres absentes d'au moins N lancements depuis leur dernière vue, vues pour la
    dernière fois il y a moins de `jours_disparues` jours ; les plus récentes d'abord."""
    limite = (date.fromisoformat(jour) - timedelta(days=jours_disparues)).isoformat()
    disparues = []
    for infos in historique["offres"].values():
        if "titre" not in infos:
            continue  # entrée migrée de l'ancien format : rien à afficher
        absences = sum(1 for lancement in historique["lancements"]
                       if lancement > infos["derniere_vue"])
        if absences >= lancements_avant_disparition and infos["derniere_vue"] >= limite:
            disparues.append(Disparue(
                titre=infos["titre"], entreprise=infos["entreprise"],
                departement=infos["departement"], adresse=infos["adresse"], url=infos["url"],
                premiere_vue=infos["premiere_vue"], derniere_vue=infos["derniere_vue"],
            ))
    return sorted(disparues, key=lambda disparue: disparue.derniere_vue, reverse=True)
