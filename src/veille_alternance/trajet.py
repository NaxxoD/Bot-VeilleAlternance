"""Temps de trajet depuis le domicile, pour écarter les offres trop lointaines.

Île-de-France : transports en commun, API calculateur PRIM (Île-de-France Mobilités).
Loiret et environs : voiture, API itinéraire de la Géoplateforme IGN (sans trafic).
Une erreur réseau ne fait jamais échouer la veille : le trajet devient inconnu (None)
et l'offre est gardée.
"""

import json
import logging
import statistics
import time
from collections.abc import Callable
from dataclasses import replace
from datetime import datetime, timedelta
from pathlib import Path

import requests

from veille_alternance.config import Config
from veille_alternance.normalize import Offre, Recruteur

GEOCODAGE_URL = "https://data.geopf.fr/geocodage/search"
ITINERAIRE_URL = "https://data.geopf.fr/navigation/itineraire"
PRIM_URL = "https://prim.iledefrance-mobilites.fr/marketplace/v2/navitia/journeys"
PAUSE_IGN = 0.25  # secondes ; limite IGN = 5 requêtes/s par adresse IP

Point = tuple[float, float]  # (longitude, latitude)
# ~100 m autour d'un point que PRIM ne sait pas rattacher au réseau piéton
DECALAGES_VOISINS = ((0.001, 0), (-0.001, 0), (0, 0.001), (0, -0.001))

journal = logging.getLogger(__name__)


def _get_json(
    session, url: str, params: dict, timeout: float, sans_solution: bool = False
) -> dict | None:
    """GET qui renvoie None au lieu de lever une exception : le trajet devient inconnu.
    Avec sans_solution, un 404 (PRIM : « no_solution ») n'est pas une erreur : renvoie {}."""
    try:
        reponse = session.get(url, params=params, timeout=timeout)
    except requests.RequestException as erreur:
        journal.warning("Trajet : %s injoignable (%s)", url, erreur)
        return None
    if reponse.status_code == 404 and sans_solution:
        return {}
    if reponse.status_code != 200:
        journal.warning("Trajet : HTTP %s sur %s", reponse.status_code, url)
        return None
    return reponse.json()


def prochain_jour_ouvre(maintenant: datetime, heure: str) -> str:
    """Date Navitia (AAAAMMJJTHHMMSS) du prochain jour du lundi au vendredi, à l'heure
    donnée ("08:00"). Les jours fériés ne sont pas gérés."""
    jour = maintenant + timedelta(days=1)
    while jour.weekday() >= 5:
        jour += timedelta(days=1)
    heures, minutes = heure.split(":")
    return f"{jour:%Y%m%d}T{int(heures):02d}{int(minutes):02d}00"


class Geocodeur:
    """Adresse → coordonnées, via le géocodage IGN (sans clé)."""

    def __init__(
        self,
        timeout: float = 30.0,
        session: requests.Session | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ):
        self._session = session or requests.Session()
        self._timeout = timeout
        self._sleep = sleep

    def localiser(self, adresse: str) -> Point | None:
        self._sleep(PAUSE_IGN)
        donnees = _get_json(
            self._session, GEOCODAGE_URL,
            {"q": adresse, "limit": 1, "index": "address"}, self._timeout,
        )
        features = (donnees or {}).get("features") or []
        if not features:
            return None
        longitude, latitude = features[0]["geometry"]["coordinates"][:2]
        return (longitude, latitude)


class ClientVoiture:
    """Durée en voiture, itinéraire le plus rapide selon l'IGN (sans trafic)."""

    def __init__(
        self,
        timeout: float = 30.0,
        session: requests.Session | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ):
        self._session = session or requests.Session()
        self._timeout = timeout
        self._sleep = sleep

    def duree_minutes(self, depart: Point, arrivee: Point) -> float | None:
        self._sleep(PAUSE_IGN)
        donnees = _get_json(
            self._session, ITINERAIRE_URL,
            {
                "resource": "bdtopo-osrm", "profile": "car", "optimization": "fastest",
                "start": f"{depart[0]},{depart[1]}", "end": f"{arrivee[0]},{arrivee[1]}",
                "timeUnit": "minute", "getSteps": "false",
            },
            self._timeout,
        )
        if not donnees or donnees.get("duration") is None:
            return None
        return float(donnees["duration"])


class ClientTransports:
    """Durée en transports en commun (PRIM), départ le prochain jour ouvré à heure fixe."""

    def __init__(
        self,
        api_key: str,
        heure_depart: str = "08:00",
        timeout: float = 30.0,
        session: requests.Session | None = None,
        maintenant: Callable[[], datetime] = datetime.now,
    ):
        self._session = session or requests.Session()
        self._session.headers["apikey"] = api_key
        self._heure_depart = heure_depart
        self._timeout = timeout
        self._maintenant = maintenant

    def _meilleure_duree(self, depart: Point, arrivee: Point) -> tuple[float | None, bool]:
        """(durée en minutes ou None, erreur) ; erreur = autre chose qu'« aucune solution »."""
        donnees = _get_json(
            self._session, PRIM_URL,
            {
                "from": f"{depart[0]};{depart[1]}",
                "to": f"{arrivee[0]};{arrivee[1]}",
                "datetime": prochain_jour_ouvre(self._maintenant(), self._heure_depart),
            },
            self._timeout, sans_solution=True,
        )
        if donnees is None:
            return None, True
        itineraires = donnees.get("journeys") or []
        if not itineraires:
            return None, False
        return min(itineraire["duration"] for itineraire in itineraires) / 60, False

    def duree_minutes(self, depart: Point, arrivee: Point) -> float | None:
        """Durée du meilleur itinéraire. PRIM répond « no_solution » quand le point exact
        tombe hors du réseau piéton (cas constaté : un bureau de Saint-Cloud, alors que
        le même point décalé de 100 m donne 45-60 min) : on réessaie alors autour du
        point et on garde la médiane. Une vraie erreur (clé, réseau) n'est pas réessayée."""
        duree, erreur = self._meilleure_duree(depart, arrivee)
        if duree is not None or erreur:
            return duree
        voisines = []
        for decalage_x, decalage_y in DECALAGES_VOISINS:
            duree, erreur = self._meilleure_duree(
                depart, (round(arrivee[0] + decalage_x, 6), round(arrivee[1] + decalage_y, 6))
            )
            if erreur:
                return None
            if duree is not None:
                voisines.append(duree)
        if not voisines:
            journal.warning("Trajet : aucun itinéraire en transports vers %s", arrivee)
            return None
        return statistics.median(voisines)


class CacheTrajets:
    """Coordonnées par adresse et durées par trajet, gardées sur disque. Seuls les
    succès sont enregistrés : une panne passagère ne fige pas un trajet inconnu.
    Supprimer le fichier vide le cache."""

    def __init__(self, chemin: Path):
        self._chemin = chemin
        donnees = json.loads(chemin.read_text(encoding="utf-8")) if chemin.exists() else {}
        self.lieux: dict[str, list[float]] = donnees.get("lieux", {})
        self.durees: dict[str, float] = donnees.get("durees", {})

    def sauvegarder(self) -> None:
        self._chemin.parent.mkdir(parents=True, exist_ok=True)
        self._chemin.write_text(
            json.dumps({"lieux": self.lieux, "durees": self.durees}, ensure_ascii=False, indent=1),
            encoding="utf-8",
        )


def _cle_duree(mode: str, depart: Point, arrivee: Point) -> str:
    # Arrondi à 3 décimales (~100 m) : deux offres voisines partagent le calcul
    return f"{mode}|{depart[0]:.3f},{depart[1]:.3f}|{arrivee[0]:.3f},{arrivee[1]:.3f}"


class Trajets:
    """Calcule le temps de trajet de chaque offre et sépare les offres trop lointaines."""

    def __init__(self, config: Config, geocodeur, transports, voiture, cache: CacheTrajets):
        self._config = config
        self._geocodeur = geocodeur
        self._transports = transports
        self._voiture = voiture
        self._cache = cache

    def _en_voiture(self, offre: Offre | Recruteur) -> bool:
        return offre.departement in self._config.trajet_departements_voiture

    def _point(self, offre: Offre | Recruteur) -> Point | None:
        if offre.longitude is not None and offre.latitude is not None:
            return (offre.longitude, offre.latitude)
        if not offre.adresse:
            return None
        if offre.adresse in self._cache.lieux:
            longitude, latitude = self._cache.lieux[offre.adresse]
            return (longitude, latitude)
        point = self._geocodeur.localiser(offre.adresse)
        if point is not None:
            self._cache.lieux[offre.adresse] = list(point)
        return point

    def _duree(self, mode: str, client, depart: Point, arrivee: Point) -> float | None:
        cle = _cle_duree(mode, depart, arrivee)
        if cle in self._cache.durees:
            return self._cache.durees[cle]
        duree = client.duree_minutes(depart, arrivee)
        if duree is not None:
            self._cache.durees[cle] = duree
        return duree

    def minutes(self, offre: Offre | Recruteur) -> float | None:
        arrivee = self._point(offre)
        if arrivee is None:
            return None
        if self._en_voiture(offre):
            return self._duree(
                "voiture", self._voiture, self._config.trajet_depart_voiture, arrivee
            )
        durees = [
            self._duree("transports", self._transports, depart, arrivee)
            for depart in self._config.trajet_departs_transports
        ]
        connues = [duree for duree in durees if duree is not None]
        return min(connues) if connues else None

    def repartir(
        self, offres: list[Offre | Recruteur]
    ) -> tuple[list[Offre | Recruteur], list[Offre | Recruteur]]:
        """(éléments dans le périmètre ou au trajet inconnu, éléments trop loin)."""
        proches, trop_loin = [], []
        for offre in offres:
            minutes = self.minutes(offre)
            offre = replace(offre, trajet_min=None if minutes is None else round(minutes))
            seuil = (
                self._config.trajet_max_voiture if self._en_voiture(offre)
                else self._config.trajet_max_transports
            )
            if offre.trajet_min is not None and offre.trajet_min > seuil:
                trop_loin.append(offre)
            else:
                proches.append(offre)
        self._cache.sauvegarder()
        inconnus = sum(1 for offre in proches if offre.trajet_min is None)
        if inconnus:
            journal.warning("Trajet inconnu pour %d éléments, gardés par prudence", inconnus)
        return proches, trop_loin
