"""Client HTTP de l'API France Travail « Offres d'emploi v2 ».

Authentification OAuth2 « client credentials » : l'identifiant et la clé secrète
sont échangés contre un jeton temporaire (~25 min), renouvelé automatiquement.
"""

import logging
import time
from collections.abc import Callable

import requests

from veille_alternance.client import ApiError

TOKEN_URL = "https://entreprise.francetravail.fr/connexion/oauth2/access_token"
SEARCH_URL = "https://api.francetravail.io/partenaire/offresdemploi/v2/offres/search"
SCOPE = "api_offresdemploiv2 o2dsoffre"
TAILLE_PAGE = 150      # maximum accepté par l'API (au-delà : HTTP 400)
INDEX_MAX = 3000       # l'API ne pagine pas au-delà de ~3 150 résultats
MARGE_JETON = 60       # secondes : on renouvelle le jeton un peu avant son expiration
PAUSE_ENTRE_PAGES = 0.15  # secondes ; limite API = 10 appels/s

journal = logging.getLogger(__name__)


class FtClient:
    def __init__(
        self,
        client_id: str,
        client_secret: str,
        timeout: float = 60.0,
        session: requests.Session | None = None,
        max_retries: int = 3,
        sleep: Callable[[float], None] = time.sleep,
        horloge: Callable[[], float] = time.monotonic,
    ):
        self._client_id = client_id
        self._client_secret = client_secret
        self._timeout = timeout
        self._session = session or requests.Session()
        self._max_retries = max_retries
        self._sleep = sleep
        self._horloge = horloge
        self._jeton: str | None = None
        self._expiration = 0.0

    def _obtenir_jeton(self) -> str:
        if self._jeton and self._horloge() < self._expiration:
            return self._jeton
        reponse = self._session.post(
            TOKEN_URL,
            params={"realm": "/partenaire"},
            data={
                "grant_type": "client_credentials",
                "client_id": self._client_id,
                "client_secret": self._client_secret,
                "scope": SCOPE,
            },
            timeout=self._timeout,
        )
        if reponse.status_code != 200:
            raise ApiError(
                f"France Travail : authentification refusée (HTTP {reponse.status_code}) : "
                f"{reponse.text[:200]}"
            )
        donnees = reponse.json()
        self._jeton = donnees["access_token"]
        self._expiration = self._horloge() + float(donnees["expires_in"]) - MARGE_JETON
        return self._jeton

    def _page(self, params: dict):
        for tentative in range(self._max_retries + 1):
            reponse = self._session.get(
                SEARCH_URL,
                params=params,
                headers={
                    "Authorization": f"Bearer {self._obtenir_jeton()}",
                    "Accept": "application/json",
                },
                timeout=self._timeout,
            )
            if reponse.status_code == 429 and tentative < self._max_retries:
                self._sleep(float(reponse.headers.get("Retry-After", 1)))
                continue
            if reponse.status_code == 401 and tentative < self._max_retries:
                self._jeton = None  # jeton refusé : on en redemande un
                continue
            return reponse
        raise ApiError(f"France Travail : échec après {self._max_retries} nouvelles tentatives")

    def search(self, departement: str, nature_contrat: str) -> dict:
        """Toutes les offres d'un département pour une nature de contrat (pagination incluse)."""
        resultats = []
        debut = 0
        while True:
            params = {
                "departement": departement,
                "natureContrat": nature_contrat,
                "range": f"{debut}-{debut + TAILLE_PAGE - 1}",
            }
            reponse = self._page(params)
            if reponse.status_code == 204:
                break
            if reponse.status_code not in (200, 206):
                raise ApiError(
                    f"France Travail : HTTP {reponse.status_code} : {reponse.text[:200]}"
                )
            resultats.extend(reponse.json()["resultats"])
            total = int(reponse.headers.get("Content-Range", "/0").split("/")[-1])
            debut += TAILLE_PAGE
            if debut >= total:
                break
            if debut > INDEX_MAX:
                journal.warning(
                    "France Travail département %s : %d offres, seules les %d premières "
                    "sont accessibles", departement, total, debut,
                )
                break
            self._sleep(PAUSE_ENTRE_PAGES)
        return {"resultats": resultats}
