"""Bilan d'activité de la veille, recalculé depuis les sorties quotidiennes.

Lancement : `python -m veille_alternance.bilan` (lit data/processed/, ne touche à rien).
Il mesure ce que l'outil trouve, pas ce qu'il rapporte en candidatures.
"""

import json
import re
import tomllib
from collections import Counter
from pathlib import Path

from veille_alternance.config import RACINE
from veille_alternance.process import _motif, sans_accents


def _cle(element: dict) -> tuple:
    """Identité d'une offre d'un jour à l'autre : titre, département, employeur."""
    return (element["titre"], element["departement"], element.get("entreprise"))


def _lire(chemin: Path) -> list[dict]:
    return json.loads(chemin.read_text(encoding="utf-8"))


def jours_disponibles(dossier: Path) -> list[str]:
    """Jours pour lesquels le vivier ET les offres retenues existent, dans l'ordre."""
    jours = []
    for chemin in sorted(dossier.glob("offres_*.json")):
        jour = re.search(r"(\d{4}-\d{2}-\d{2})", chemin.name).group(1)
        if (dossier / f"pool_offres_{jour}.json").exists():
            jours.append(jour)
    return jours


def famille(offre: dict, motif_dev) -> str:
    """Famille enregistrée par la veille, sinon recalculée sur le titre (anciens jours)."""
    if offre.get("famille"):
        return offre["famille"]
    return "dev" if motif_dev.search(sans_accents(offre["titre"])) else "infra"


def calculer_bilan(dossier: Path, mots_cles_dev: list[str]) -> dict:
    motif_dev = _motif(mots_cles_dev)
    jours, precedent, presence = [], None, {}
    for jour in jours_disponibles(dossier):
        vivier = {_cle(o) for o in _lire(dossier / f"pool_offres_{jour}.json")}
        retenues = _lire(dossier / f"offres_{jour}.json")
        cles = {_cle(o) for o in retenues}
        for cle in cles:
            presence.setdefault(cle, []).append(jour)
        jours.append({
            "jour": jour, "vivier": len(vivier), "retenues": len(retenues),
            "nouvelles": sum(1 for o in retenues if o.get("premiere_vue") == jour),
            "entrees_vivier": None if precedent is None else len(vivier - precedent),
            "sorties_vivier": None if precedent is None else len(precedent - vivier),
            "retenues_entrees": None if precedent is None else len(cles - precedent),
            "sources": Counter(o["source"] for o in retenues),
            "familles": Counter(famille(o, motif_dev) for o in retenues),
            "trajet_inconnu": sum(1 for o in retenues if o.get("trajet_min") is None),
        })
        precedent = vivier
    durees = [len(v) for v in presence.values()]
    return {
        "jours": jours,
        "distinctes": len(presence),
        "duree_moyenne": sum(durees) / len(durees) if durees else 0,
        "un_seul_jour": sum(1 for d in durees if d == 1),
    }


def formater(bilan: dict) -> str:
    jours = bilan["jours"]
    if not jours:
        return "Aucune sortie quotidienne à analyser."
    lignes = [
        f"Bilan de la veille — {jours[0]['jour']} → {jours[-1]['jour']} ({len(jours)} jours)",
        "",
        "jour        vivier  retenues  nouvelles  entrées vivier  dont retenues  dev/infra",
    ]
    for j in jours:
        entrees = "-" if j["entrees_vivier"] is None else j["entrees_vivier"]
        pertinentes = "-" if j["retenues_entrees"] is None else j["retenues_entrees"]
        lignes.append(
            f"{j['jour']}  {j['vivier']:>6}  {j['retenues']:>8}  {j['nouvelles']:>9}  "
            f"{entrees:>14}  {pertinentes:>13}  {j['familles']['dev']}/{j['familles']['infra']}"
        )
    suivants = [j for j in jours if j["entrees_vivier"] is not None]
    if suivants:
        entrees = sum(j["entrees_vivier"] for j in suivants)
        pertinentes = sum(j["retenues_entrees"] for j in suivants)
        lignes += [
            "",
            f"Flux : {entrees / len(suivants):.0f} offres entrent dans le vivier par jour ; "
            f"{pertinentes} offres retenues sont apparues en {len(suivants)} jours "
            f"({pertinentes / len(suivants) * 7:.1f} par semaine).",
        ]
    lignes += [
        f"Offres retenues distinctes : {bilan['distinctes']} ; présence moyenne "
        f"{bilan['duree_moyenne']:.1f} jours ; {bilan['un_seul_jour']} vues un seul jour.",
        "Dernier jour, par source : "
        + ", ".join(f"{s} {n}" for s, n in jours[-1]["sources"].most_common()),
        f"Trajet inconnu au dernier jour : {jours[-1]['trajet_inconnu']}.",
        "",
        "Limites : les filtres ont évolué (trajet, mots-clés dev) donc les jours ne sont pas "
        "strictement comparables (avant le 05/10, les offres dev n'étaient pas cherchées : le "
        "dev/infra des anciens jours est recalculé mais sous-estime le dev) ; une offre republiée "
        "sous un autre titre compte comme nouvelle ; le vivier compte des offres distinctes.",
    ]
    return "\n".join(lignes)


def main() -> None:
    with open(RACINE / "config" / "search.toml", "rb") as fichier:
        mots_dev = tomllib.load(fichier)["filtres"].get("mots_cles_dev", [])
    print(formater(calculer_bilan(RACINE / "data" / "processed", mots_dev)))


if __name__ == "__main__":
    main()
