"""Conversion des réponses brutes de l'API en objets Offre et Recruteur."""

import html
import re
from dataclasses import dataclass


@dataclass(frozen=True)
class Offre:
    cle: str
    source: str
    titre: str
    entreprise: str | None
    adresse: str
    departement: str
    contrat: tuple[str, ...]
    teletravail: str | None
    debut: str | None
    niveau: str | None
    romes: tuple[str, ...]
    description: str
    url: str
    publiee_le: str | None
    premiere_vue: str | None = None  # date de première détection, renseignée par history
    naf: str | None = None  # secteur de l'employeur (sert à repérer les écoles, NAF 85)
    latitude: float | None = None  # lieu de travail, quand la source le donne
    longitude: float | None = None
    trajet_min: int | None = None  # depuis le domicile, renseigné par trajet
    anciennete_jours: int | None = None  # jours en ligne, renseigné par history
    relayee_par: str | None = None  # agrégateur qui relaie l'offre (France Travail), ex. « METEOJOB »
    famille: str | None = None  # « dev » ou « infra », renseigné par process.classer_familles


@dataclass(frozen=True)
class Recruteur:
    siret: str
    nom: str | None
    adresse: str
    departement: str
    taille: str | None
    secteur: str | None
    naf: str | None
    site_web: str | None
    telephone: str | None
    url: str
    latitude: float | None = None
    longitude: float | None = None
    trajet_min: int | None = None  # depuis le domicile, renseigné par trajet


def nettoyer_texte(texte: str | None) -> str:
    """Retire les balises HTML, décode les entités (&amp;) et normalise les espaces."""
    if not texte:
        return ""
    resultat = re.sub(r"<br\s*/?>|</p>|</li>", "\n", texte, flags=re.IGNORECASE)
    resultat = re.sub(r"<[^>]+>", "", resultat)
    resultat = html.unescape(resultat).replace("\xa0", " ")
    resultat = re.sub(r"[ \t]+", " ", resultat)
    resultat = re.sub(r" *\n *", "\n", resultat)
    resultat = re.sub(r"\n{3,}", "\n\n", resultat)
    return resultat.strip()


def normaliser_offre(job: dict, departement: str) -> Offre:
    identifiant = job["identifier"]
    offre = job["offer"]
    contrat = job["contract"]
    diplome = offre.get("target_diploma")
    geopoint = job["workplace"]["location"].get("geopoint") or {}
    longitude, latitude = (geopoint.get("coordinates") or [None, None])[:2]
    return Offre(
        cle=f"{identifiant['partner_label']}|{identifiant['partner_job_id']}",
        source=identifiant["partner_label"],
        titre=nettoyer_texte(offre["title"]),
        entreprise=job["workplace"]["name"],
        adresse=job["workplace"]["location"]["address"],
        departement=departement,
        contrat=tuple(contrat["type"]),
        teletravail=contrat["remote"],
        debut=contrat["start"],
        niveau=diplome["european"] if diplome else None,
        romes=tuple(offre["rome_codes"]),
        description=nettoyer_texte(offre["description"]),
        url=job["apply"]["url"],
        publiee_le=offre["publication"]["creation"],
        naf=((job["workplace"].get("domain") or {}).get("naf") or {}).get("code"),
        latitude=latitude,
        longitude=longitude,
    )


URL_OFFRE_FT = "https://candidat.francetravail.fr/offres/recherche/detail/{id}"


def _contrat_ft(nature: str | None) -> tuple[str, ...]:
    """'Contrat apprentissage' → ('Apprentissage',), pour rester aligné sur LBA."""
    texte = (nature or "").lower()
    if "apprentissage" in texte:
        return ("Apprentissage",)
    if "professionnalisation" in texte:
        return ("Professionnalisation",)
    return (nature,) if nature else ()


def _relais_ft(offre: dict) -> str | None:
    """Nom du site partenaire qui a publié l'offre, quand elle n'est pas déposée en direct
    (origine « 2 » ; origine « 1 » = déposée sur France Travail par l'employeur)."""
    origine = offre.get("origineOffre") or {}
    if origine.get("origine") != "2":
        return None
    partenaires = origine.get("partenaires") or []
    return partenaires[0].get("nom") if partenaires else None


def normaliser_offre_ft(offre: dict, departement: str) -> Offre:
    """Offre de l'API France Travail. La clé « France Travail|<id> » est la même que
    celle des offres France Travail relayées par LBA : les doublons se fusionnent."""
    lieu = offre.get("lieuTravail") or {}
    commune = re.sub(r"^\d{2,3} - ", "", lieu.get("libelle") or "")  # "75 - Paris 12e" → "Paris 12e"
    return Offre(
        cle=f"France Travail|{offre['id']}",
        source="France Travail",
        titre=nettoyer_texte(offre.get("intitule")),
        entreprise=(offre.get("entreprise") or {}).get("nom"),
        adresse=f"{lieu.get('codePostal') or ''} {commune}".strip(),
        departement=departement,
        contrat=_contrat_ft(offre.get("natureContrat")),
        teletravail=None,
        debut=None,
        niveau=None,
        romes=(offre["romeCode"],) if offre.get("romeCode") else (),
        description=nettoyer_texte(offre.get("description")),
        url=(offre.get("origineOffre") or {}).get("urlOrigine")
        or URL_OFFRE_FT.format(id=offre["id"]),
        publiee_le=offre.get("dateCreation"),
        naf=offre.get("codeNAF"),
        latitude=lieu.get("latitude"),
        longitude=lieu.get("longitude"),
        relayee_par=_relais_ft(offre),
    )


def normaliser_reponse_ft(reponse: dict, departement: str) -> list[Offre]:
    return [normaliser_offre_ft(offre, departement) for offre in reponse["resultats"]]


def normaliser_recruteur(recruteur: dict, departement: str) -> Recruteur:
    lieu = recruteur["workplace"]
    naf = lieu["domain"]["naf"]
    geopoint = lieu["location"].get("geopoint") or {}
    longitude, latitude = (geopoint.get("coordinates") or [None, None])[:2]
    return Recruteur(
        siret=lieu["siret"] or recruteur["identifier"]["id"],
        nom=lieu["name"],
        adresse=lieu["location"]["address"],
        departement=departement,
        taille=lieu["size"],
        secteur=naf["label"] if naf else None,
        naf=naf["code"] if naf else None,
        site_web=lieu["website"],
        telephone=recruteur["apply"]["phone"],
        url=recruteur["apply"]["url"],
        latitude=latitude,
        longitude=longitude,
    )


def normaliser_reponse(reponse: dict, departement: str) -> tuple[list[Offre], list[Recruteur]]:
    offres = [normaliser_offre(job, departement) for job in reponse["jobs"]]
    recruteurs = [normaliser_recruteur(rec, departement) for rec in reponse["recruiters"]]
    return offres, recruteurs
