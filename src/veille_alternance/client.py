"""Client HTTP de l'API La Bonne Alternance (GET /job/v1/search)."""

import time
from collections.abc import Callable

import requests

CODES_QUOTA = (419, 429)  # la spec annonce 429 dans le texte et 419 dans le schéma


class ApiError(Exception):
    """Erreur renvoyée par l'API ou quota épuisé."""


class LbaClient:
    def __init__(
        self,
        api_key: str,
        base_url: str,
        timeout: float = 60.0,
        session: requests.Session | None = None,
        max_retries: int = 3,
        sleep: Callable[[float], None] = time.sleep,
    ):
        self._session = session or requests.Session()
        self._session.headers["Authorization"] = f"Bearer {api_key}"
        self._url = f"{base_url}/job/v1/search"
        self._timeout = timeout
        self._max_retries = max_retries
        self._sleep = sleep

    def search(self, departement: str, romes: list[str]) -> dict:
        params = {"departements": departement, "romes": ",".join(romes)}
        for tentative in range(self._max_retries + 1):
            reponse = self._session.get(self._url, params=params, timeout=self._timeout)
            if reponse.status_code in CODES_QUOTA:
                if tentative == self._max_retries:
                    break
                self._sleep(float(reponse.headers.get("retry-after", 60)))
                continue
            if reponse.status_code == 401:
                raise ApiError("HTTP 401 : clé API invalide ou absente")
            if reponse.status_code != 200:
                raise ApiError(f"HTTP {reponse.status_code} : {reponse.text[:200]}")
            return reponse.json()
        raise ApiError(f"Quota dépassé après {self._max_retries} nouvelles tentatives")
