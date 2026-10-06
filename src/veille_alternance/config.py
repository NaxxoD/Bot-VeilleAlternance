"""Lecture de la configuration : config/search.toml + clé API depuis .env."""

import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

RACINE = Path(__file__).resolve().parents[2]


class ConfigError(Exception):
    """Configuration absente ou invalide."""


@dataclass(frozen=True)
class Config:
    api_key: str
    base_url: str
    pause_entre_appels: float
    timeout: float
    departements: list[str]
    romes: list[str]
    types_contrat: list[str]
    mots_cles_titre: list[str]
    mots_cles_description: list[str]
    mots_exclus_titre: list[str]
    dossier_raw: Path
    mots_cles_dev: list[str] = field(default_factory=list)  # titres classés « dev »
    naf_prefixes: list[str] = field(default_factory=list)
    tailles_exclues: list[str] = field(default_factory=list)
    ft_actif: bool = False
    ft_client_id: str = ""
    ft_client_secret: str = ""
    ft_nature_contrat: str = "E2"  # E2 = contrat d'apprentissage, FS = professionnalisation
    ecoles_naf_prefixes: list[str] = field(default_factory=list)
    organismes_exclus: list[str] = field(default_factory=list)
    trajet_actif: bool = False
    prim_api_key: str = ""
    trajet_departs_transports: list[tuple[float, float]] = field(default_factory=list)
    trajet_heure_depart: str = "08:00"
    trajet_max_transports: float = 45.0
    trajet_departements_voiture: list[str] = field(default_factory=list)
    trajet_depart_voiture: tuple[float, float] | None = None  # (longitude, latitude)
    trajet_max_voiture: float = 45.0
    lancements_avant_disparition: int = 2
    jours_disparues: int = 14
    naf_coeur: list[str] = field(default_factory=list)  # recruteurs classés en premier
    zones: list[tuple[str, list[str]]] = field(default_factory=list)  # blocs du rapport


def developper_plage(debut: str, fin: str) -> list[str]:
    """Transforme ("M1801", "M1803") en ["M1801", "M1802", "M1803"]."""
    if debut[0] != fin[0]:
        raise ConfigError(f"Plage ROME invalide (lettres différentes) : {debut}-{fin}")
    lettre = debut[0]
    premier, dernier = int(debut[1:]), int(fin[1:])
    if premier > dernier:
        raise ConfigError(f"Plage ROME invalide (bornes inversées) : {debut}-{fin}")
    return [f"{lettre}{numero:04d}" for numero in range(premier, dernier + 1)]


def charger_config(
    chemin_toml: Path = RACINE / "config" / "search.toml",
    chemin_env: Path = RACINE / ".env",
) -> Config:
    load_dotenv(chemin_env)
    cle = os.environ.get("LBA_API_KEY", "").strip()
    if not cle:
        raise ConfigError("LBA_API_KEY absente : renseigne-la dans le fichier .env")

    with open(chemin_toml, "rb") as fichier:
        donnees = tomllib.load(fichier)

    romes = [
        code
        for debut, fin in donnees["recherche"]["rome_plages"]
        for code in developper_plage(debut, fin)
    ]
    # Section [stockage] facultative ; chemin relatif = relatif à la racine du projet
    dossier_raw = Path(donnees.get("stockage", {}).get("dossier_raw", "data/raw"))
    if not dossier_raw.is_absolute():
        dossier_raw = RACINE / dossier_raw

    # Section [france_travail] facultative : source désactivée sans elle
    france_travail = donnees.get("france_travail", {})
    ft_actif = bool(france_travail.get("actif", False))
    ft_client_id = os.environ.get("FT_CLIENT_ID", "").strip()
    ft_client_secret = os.environ.get("FT_CLIENT_SECRET", "").strip()
    if ft_actif and not (ft_client_id and ft_client_secret):
        raise ConfigError(
            "France Travail activé mais FT_CLIENT_ID ou FT_CLIENT_SECRET absent du fichier .env"
        )
    ecoles = donnees.get("filtres_ecoles", {})

    # Section [trajet] facultative : sans elle, pas de filtre par temps de trajet
    trajet = donnees.get("trajet", {})
    trajet_actif = bool(trajet.get("actif", False))
    transports = trajet.get("transports", {})
    voiture = trajet.get("voiture", {})
    prim_api_key = os.environ.get("PRIM_API_KEY", "").strip()
    if trajet_actif and not prim_api_key:
        raise ConfigError("Trajet activé mais PRIM_API_KEY absente du fichier .env")
    depart_voiture = voiture.get("depart")
    if trajet_actif and voiture.get("departements") and not depart_voiture:
        raise ConfigError("[trajet.voiture] : departements sans point de depart")

    # Section [historique] facultative : offres disparues (absentes de N lancements)
    suivi = donnees.get("historique", {})

    return Config(
        api_key=cle,
        base_url=donnees["api"]["base_url"],
        pause_entre_appels=float(donnees["api"]["pause_entre_appels"]),
        timeout=float(donnees["api"]["timeout"]),
        departements=list(donnees["recherche"]["departements"]),
        romes=romes,
        types_contrat=list(donnees["filtres"]["types_contrat"]),
        mots_cles_titre=list(donnees["filtres"]["mots_cles_titre"]),
        mots_cles_description=list(donnees["filtres"]["mots_cles_description"]),
        mots_exclus_titre=list(donnees["filtres"]["mots_exclus_titre"]),
        dossier_raw=dossier_raw,
        mots_cles_dev=list(donnees["filtres"].get("mots_cles_dev", [])),
        # Section [filtres_recruteurs] facultative : sans elle, aucun filtre
        naf_prefixes=list(donnees.get("filtres_recruteurs", {}).get("naf_prefixes", [])),
        tailles_exclues=list(donnees.get("filtres_recruteurs", {}).get("tailles_exclues", [])),
        ft_actif=ft_actif,
        ft_client_id=ft_client_id,
        ft_client_secret=ft_client_secret,
        ft_nature_contrat=france_travail.get("nature_contrat", "E2"),
        ecoles_naf_prefixes=list(ecoles.get("naf_prefixes", [])),
        organismes_exclus=list(ecoles.get("organismes_exclus", [])),
        trajet_actif=trajet_actif,
        prim_api_key=prim_api_key,
        trajet_departs_transports=[tuple(point) for point in transports.get("departs", [])],
        trajet_heure_depart=transports.get("heure_depart", "08:00"),
        trajet_max_transports=float(transports.get("max_minutes", 45)),
        trajet_departements_voiture=list(voiture.get("departements", [])),
        trajet_depart_voiture=tuple(depart_voiture) if depart_voiture else None,
        trajet_max_voiture=float(voiture.get("max_minutes", 45)),
        lancements_avant_disparition=int(suivi.get("lancements_avant_disparition", 2)),
        jours_disparues=int(suivi.get("jours_disparues", 14)),
        naf_coeur=list(donnees.get("filtres_recruteurs", {}).get("naf_coeur", [])),
        zones=[
            (zone["nom"], list(zone["departements"]))
            for zone in donnees.get("rapport", {}).get("zones", [])
        ],
    )
