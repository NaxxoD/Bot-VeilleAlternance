"""Filtres et déduplication — fonctions pures, sans accès disque ni réseau."""

import re
import unicodedata
from dataclasses import replace

from veille_alternance.normalize import Offre, Recruteur


def sans_accents(texte: str) -> str:
    """Minuscules sans accents : 'Réseaux' → 'reseaux'."""
    decompose = unicodedata.normalize("NFKD", texte.lower())
    return "".join(c for c in decompose if not unicodedata.combining(c))


def dedupliquer_offres(offres: list[Offre]) -> list[Offre]:
    vues: set[str] = set()
    resultat = []
    for offre in offres:
        if offre.cle not in vues:
            vues.add(offre.cle)
            resultat.append(offre)
    return resultat


def cle_contenu(offre: Offre) -> str:
    """Clé « titre normalisé | code postal » pour repérer une même offre
    diffusée par plusieurs partenaires sous des identifiants différents."""
    titre = sans_accents(offre.titre)
    titre = re.sub(r"\((?:h/f|f/h|h-f|f-h|e)\)|\b(?:h/f|f/h)\b", " ", titre)
    titre = " ".join(re.sub(r"[^a-z0-9]+", " ", titre).split())
    code_postal = re.search(r"\b\d{5}\b", offre.adresse or "")
    return f"{titre}|{code_postal.group() if code_postal else offre.departement}"


def dedupliquer_par_contenu(offres: list[Offre]) -> list[Offre]:
    vues: set[str] = set()
    resultat = []
    for offre in offres:
        cle = cle_contenu(offre)
        if cle not in vues:
            vues.add(cle)
            resultat.append(offre)
    return resultat


def dedupliquer_recruteurs(recruteurs: list[Recruteur]) -> list[Recruteur]:
    vus: set[str] = set()
    resultat = []
    for recruteur in recruteurs:
        if recruteur.siret not in vus:
            vus.add(recruteur.siret)
            resultat.append(recruteur)
    return resultat


def filtrer_recruteurs(
    recruteurs: list[Recruteur], naf_prefixes: list[str], tailles_exclues: list[str]
) -> list[Recruteur]:
    """Garde les recruteurs dont le code NAF commence par un des préfixes
    (liste vide = pas de filtre NAF) et dont la taille n'est pas exclue."""
    resultat = []
    for recruteur in recruteurs:
        if recruteur.taille in tailles_exclues:
            continue
        if naf_prefixes and not (
            recruteur.naf and any(recruteur.naf.startswith(p) for p in naf_prefixes)
        ):
            continue
        resultat.append(recruteur)
    return resultat


def trier_recruteurs(recruteurs: list[Recruteur], naf_coeur: list[str]) -> list[Recruteur]:
    """Cœur numérique d'abord (préfixes NAF), puis du plus proche au plus loin ;
    trajet inconnu en fin de groupe."""
    def cle(recruteur: Recruteur) -> tuple:
        coeur = bool(recruteur.naf) and any(recruteur.naf.startswith(p) for p in naf_coeur)
        return (not coeur, recruteur.trajet_min is None, recruteur.trajet_min or 0)
    return sorted(recruteurs, key=cle)


def filtrer_contrat(offres: list[Offre], types_contrat: list[str]) -> list[Offre]:
    return [o for o in offres if any(t in types_contrat for t in o.contrat)]


def _motif(mots: list[str]) -> re.Pattern:
    """Motif qui trouve un des mots au début d'un mot : 'ssi' trouve 'SSI', pas 'assistant'."""
    alternatives = "|".join(re.escape(sans_accents(m)) for m in mots)
    return re.compile(rf"\b(?:{alternatives})") if mots else re.compile(r"(?!)")


def filtrer_mots_cles(
    offres: list[Offre],
    mots_cles_titre: list[str],
    mots_cles_description: list[str],
    mots_exclus_titre: list[str],
) -> list[Offre]:
    """Garde une offre si son titre ou sa description contient un mot de sa liste,
    et si son titre ne contient aucun mot exclu."""
    motif_titre = _motif(mots_cles_titre)
    motif_description = _motif(mots_cles_description)
    motif_exclus = _motif(mots_exclus_titre)
    resultat = []
    for offre in offres:
        titre = sans_accents(offre.titre)
        if motif_exclus.search(titre):
            continue
        if motif_titre.search(titre) or motif_description.search(sans_accents(offre.description)):
            resultat.append(offre)
    return resultat


def classer_familles(offres: list[Offre], mots_cles_dev: list[str]) -> list[Offre]:
    """Double vivier : « dev » si le titre contient un mot de mots_cles_dev, sinon « infra »
    (une offre retenue par la description seule, ou par un titre infra, est de l'infra)."""
    motif_dev = _motif(mots_cles_dev)
    return [
        replace(offre, famille="dev" if motif_dev.search(sans_accents(offre.titre)) else "infra")
        for offre in offres
    ]


def filtrer_ecoles(
    offres: list[Offre], naf_prefixes: list[str], organismes_exclus: list[str]
) -> list[Offre]:
    """Écarte les offres publiées par des écoles / organismes de formation :
    code NAF commençant par un préfixe (85 = enseignement) ou nom dans la liste noire
    (comparaison sans accents ni majuscules, au début d'un mot)."""
    motif_organismes = _motif(organismes_exclus)
    resultat = []
    for offre in offres:
        if offre.naf and any(offre.naf.startswith(p) for p in naf_prefixes):
            continue
        if offre.entreprise and motif_organismes.search(sans_accents(offre.entreprise)):
            continue
        resultat.append(offre)
    return resultat
