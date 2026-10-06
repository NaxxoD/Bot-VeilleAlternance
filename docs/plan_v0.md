# Plan d'implémentation — V0

**Objectif** : un script `python -m veille_alternance` qui interroge `jobSearch` pour les 9 départements (IDF + 45) sur la famille ROME M18xx + I14xx, puis écrit `data/processed/offres_AAAA-MM-JJ.json` (offres filtrées et dédupliquées) et `data/processed/recruteurs_AAAA-MM-JJ.json` (collecte simple).

Références : `docs/etude_api_lba.md` (API, décisions), `docs/architecture.md` (dossiers).

## Fichiers concernés

| Fichier | Rôle | Tâche |
| --- | --- | --- |
| `pyproject.toml` | dépendances, config pytest, paquet | 0 |
| `config/search.toml` | paramétrage (départements, ROME, filtres) | 0 |
| `src/veille_alternance/__init__.py` | paquet | 0 |
| `src/veille_alternance/config.py` | lecture config + clé | 1 |
| `src/veille_alternance/client.py` | appel HTTP `jobSearch` | 2 |
| `src/veille_alternance/normalize.py` | `Offre`, `Recruteur`, nettoyage texte | 3 |
| `src/veille_alternance/process.py` | filtres + déduplication | 4 |
| `src/veille_alternance/collect.py` | boucle départements, sauvegarde brute | 5 |
| `src/veille_alternance/output.py` | écriture JSON | 6 |
| `src/veille_alternance/__main__.py` | orchestration | 7 |
| `tests/test_*.py` | un fichier de test par module | 1 à 7 |

Conventions : noms en français, fonctions pures quand c'est possible, pas d'accès réseau dans les tests (faux client / fausse session).

---

### Tâche 0 — Mise en place de l'environnement

Fichiers : `pyproject.toml`, `config/search.toml`, `src/veille_alternance/__init__.py`

1. Créer `pyproject.toml` :

```toml
[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"

[project]
name = "veille-alternance"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = ["requests>=2.31", "python-dotenv>=1.0"]

[project.optional-dependencies]
dev = ["pytest>=8"]

[tool.setuptools.packages.find]
where = ["src"]

[tool.pytest.ini_options]
pythonpath = ["src"]
testpaths = ["tests"]
```

2. Créer `config/search.toml` :

```toml
[api]
base_url = "https://api.apprentissage.beta.gouv.fr/api"
pause_entre_appels = 1.1   # secondes ; limite API = 60 appels/min
timeout = 60               # secondes

[recherche]
departements = ["75", "77", "78", "91", "92", "93", "94", "95", "45"]
# Plages de codes ROME 4.0, bornes incluses (voir étude : balayage du 2026-09-25)
rome_plages = [["M1801", "M1899"], ["I1401", "I1415"]]

[filtres]
types_contrat = ["Apprentissage"]
# Comparés sans accents ni majuscules, sur titre + description
mots_cles = [
  "systeme", "reseau", "infrastructure", "administrateur", "sysadmin",
  "support informatique", "helpdesk", "help desk", "technicien informatique",
  "technicien support", "exploitation", "cybersecurite", "securite informatique",
  "linux", "windows server", "devops", "cloud", "virtualisation", "supervision",
  "telecom", "datacenter", "active directory",
]
# Comparés sans accents ni majuscules, sur le titre seulement
mots_exclus_titre = [
  "marketing", "commercial", "business developer", "graphiste", "comptab",
  "electromenager", "ressources humaines", "juridique",
]
```

3. Créer `src/veille_alternance/__init__.py` :

```python
"""Outil personnel de veille d'offres d'alternance (API La Bonne Alternance)."""
```

4. Créer l'environnement virtuel et installer :

```
python -m venv .venv
.venv\Scripts\activate
python -m pip install -e ".[dev]"
python -m pytest
```

Résultat attendu : `no tests ran` (code de sortie 5), aucune erreur d'import.

5. Commit : `git commit -m "Mise en place : pyproject, configuration de recherche, paquet"`

---

### Tâche 1 — `config.py` : lecture de la configuration

Fichiers : `src/veille_alternance/config.py`, `tests/test_config.py`

1. Test (`tests/test_config.py`) :

```python
import pytest

from veille_alternance.config import ConfigError, charger_config, developper_plage

TOML = """
[api]
base_url = "https://exemple.test/api"
pause_entre_appels = 0.5
timeout = 10

[recherche]
departements = ["75", "45"]
rome_plages = [["M1801", "M1803"], ["I1404", "I1404"]]

[filtres]
types_contrat = ["Apprentissage"]
mots_cles = ["reseau"]
mots_exclus_titre = ["marketing"]
"""


def test_developper_plage():
    assert developper_plage("M1801", "M1803") == ["M1801", "M1802", "M1803"]


def test_developper_plage_lettres_differentes():
    with pytest.raises(ConfigError):
        developper_plage("M1801", "I1403")


def test_developper_plage_inversee():
    with pytest.raises(ConfigError):
        developper_plage("M1810", "M1801")


def test_charger_config(tmp_path, monkeypatch):
    chemin = tmp_path / "search.toml"
    chemin.write_text(TOML, encoding="utf-8")
    monkeypatch.setenv("LBA_API_KEY", "cle-de-test")
    config = charger_config(chemin, tmp_path / "absent.env")
    assert config.api_key == "cle-de-test"
    assert config.base_url == "https://exemple.test/api"
    assert config.pause_entre_appels == 0.5
    assert config.timeout == 10
    assert config.departements == ["75", "45"]
    assert config.romes == ["M1801", "M1802", "M1803", "I1404"]
    assert config.types_contrat == ["Apprentissage"]
    assert config.mots_cles == ["reseau"]
    assert config.mots_exclus_titre == ["marketing"]


def test_charger_config_sans_cle(tmp_path, monkeypatch):
    chemin = tmp_path / "search.toml"
    chemin.write_text(TOML, encoding="utf-8")
    monkeypatch.delenv("LBA_API_KEY", raising=False)
    with pytest.raises(ConfigError, match="LBA_API_KEY"):
        charger_config(chemin, tmp_path / "absent.env")
```

2. Vérifier l'échec : `python -m pytest tests/test_config.py` → `ModuleNotFoundError: No module named 'veille_alternance.config'`.

3. Implémentation (`src/veille_alternance/config.py`) :

```python
"""Lecture de la configuration : config/search.toml + clé API depuis .env."""

import os
import tomllib
from dataclasses import dataclass
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
    mots_cles: list[str]
    mots_exclus_titre: list[str]


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
    return Config(
        api_key=cle,
        base_url=donnees["api"]["base_url"],
        pause_entre_appels=float(donnees["api"]["pause_entre_appels"]),
        timeout=float(donnees["api"]["timeout"]),
        departements=list(donnees["recherche"]["departements"]),
        romes=romes,
        types_contrat=list(donnees["filtres"]["types_contrat"]),
        mots_cles=list(donnees["filtres"]["mots_cles"]),
        mots_exclus_titre=list(donnees["filtres"]["mots_exclus_titre"]),
    )
```

4. Vérifier : `python -m pytest tests/test_config.py` → `5 passed`.

5. Commit : `git commit -m "config : lecture de search.toml et de la clé API"`

---

### Tâche 2 — `client.py` : appel à `jobSearch`

Fichiers : `src/veille_alternance/client.py`, `tests/test_client.py`

1. Test (`tests/test_client.py`) :

```python
import pytest

from veille_alternance.client import ApiError, LbaClient


class FausseReponse:
    def __init__(self, status_code, payload=None, headers=None, text=""):
        self.status_code = status_code
        self._payload = payload
        self.headers = headers or {}
        self.text = text

    def json(self):
        return self._payload


class FausseSession:
    def __init__(self, reponses):
        self.reponses = list(reponses)
        self.appels = []
        self.headers = {}

    def get(self, url, params=None, timeout=None):
        self.appels.append((url, params, timeout))
        return self.reponses.pop(0)


def creer_client(reponses, attentes):
    session = FausseSession(reponses)
    client = LbaClient(
        "cle-test", "https://exemple.test/api", timeout=5.0,
        session=session, max_retries=2, sleep=attentes.append,
    )
    return client, session


def test_search_succes():
    attentes = []
    payload = {"jobs": [], "recruiters": [], "warnings": []}
    client, session = creer_client([FausseReponse(200, payload)], attentes)
    assert client.search("75", ["M1801", "I1404"]) == payload
    assert session.headers["Authorization"] == "Bearer cle-test"
    assert session.appels == [(
        "https://exemple.test/api/job/v1/search",
        {"departements": "75", "romes": "M1801,I1404"},
        5.0,
    )]
    assert attentes == []


@pytest.mark.parametrize("code", [419, 429])
def test_search_quota_depasse_puis_succes(code):
    attentes = []
    payload = {"jobs": [], "recruiters": [], "warnings": []}
    client, _ = creer_client(
        [FausseReponse(code, headers={"retry-after": "2"}), FausseReponse(200, payload)],
        attentes,
    )
    assert client.search("75", ["M1801"]) == payload
    assert attentes == [2.0]


def test_search_quota_toujours_depasse():
    attentes = []
    client, _ = creer_client([FausseReponse(429, headers={"retry-after": "1"})] * 3, attentes)
    with pytest.raises(ApiError, match="Quota"):
        client.search("75", ["M1801"])
    assert attentes == [1.0, 1.0]


def test_search_401():
    client, _ = creer_client([FausseReponse(401)], [])
    with pytest.raises(ApiError, match="clé API"):
        client.search("75", ["M1801"])


def test_search_500():
    client, _ = creer_client([FausseReponse(500, text="erreur serveur")], [])
    with pytest.raises(ApiError, match="HTTP 500"):
        client.search("75", ["M1801"])
```

2. Vérifier l'échec : `python -m pytest tests/test_client.py` → `ModuleNotFoundError: No module named 'veille_alternance.client'`.

3. Implémentation (`src/veille_alternance/client.py`) :

```python
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
```

4. Vérifier : `python -m pytest tests/test_client.py` → `6 passed`.

5. Commit : `git commit -m "client : appel jobSearch avec gestion du quota et des erreurs"`

---

### Tâche 3 — `normalize.py` : offres et recruteurs normalisés

Fichiers : `src/veille_alternance/normalize.py`, `tests/test_normalize.py`

1. Test (`tests/test_normalize.py`), sur la vraie réponse de production sauvegardée :

```python
import json
from pathlib import Path

from veille_alternance.normalize import nettoyer_texte, normaliser_reponse

FIXTURE = Path(__file__).parent / "fixtures" / "jobsearch_prod_75_rome_M18xx_I14xx.json"


def charger():
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def test_nettoyer_texte():
    assert nettoyer_texte(None) == ""
    assert nettoyer_texte("IA &amp; Backend") == "IA & Backend"
    assert nettoyer_texte("<p><strong>A :</strong> b</p><p>c\xa0d</p>") == "A : b\nc d"


def test_normaliser_reponse_volumes():
    offres, recruteurs = normaliser_reponse(charger(), "75")
    assert len(offres) == 48
    assert len(recruteurs) == 150


def test_premiere_offre():
    offres, _ = normaliser_reponse(charger(), "75")
    offre = offres[0]
    assert offre.cle == "France Travail|7345250"
    assert offre.source == "France Travail"
    assert offre.titre == "Chef de projet Marketing Formation - H/F"
    assert offre.entreprise == "Groupe Revue Fiduciaire"
    assert offre.adresse == "75001 Paris"
    assert offre.departement == "75"
    assert offre.contrat == ("Professionnalisation",)
    assert offre.teletravail is None
    assert offre.debut is None
    assert offre.niveau is None
    assert offre.romes == ("M1828",)
    assert offre.url == "https://jobaffinity.fr/apply/hxcxg0x59epaifn0ej?src=FranceTravail%20API"
    assert offre.publiee_le == "2026-09-24T21:40:44.027Z"
    assert offre.description.startswith("Entreprise")


def test_titre_avec_entite_html():
    offres, _ = normaliser_reponse(charger(), "75")
    offre = next(o for o in offres if o.cle == "France Travail|6930081")
    assert offre.titre == "Alternance Software Engineer IA & Backend - Paris (F/H)"


def test_description_html_nettoyee():
    offres, _ = normaliser_reponse(charger(), "75")
    offre = next(o for o in offres if o.cle == "PASS|A-2026-235500")
    assert "<" not in offre.description
    assert offre.description.startswith("Fonction : Apprenti-e en électromagnétisme")


def test_premier_recruteur():
    _, recruteurs = normaliser_reponse(charger(), "75")
    recruteur = recruteurs[0]
    assert recruteur.siret == "85396596000018"
    assert recruteur.nom == "UNBLOCKED"
    assert recruteur.departement == "75"
    assert recruteur.taille == "3-5"
    assert recruteur.naf == "62.02A"
    assert recruteur.secteur == "Conseil en systèmes et logiciels informatiques"
    assert recruteur.telephone is None
    assert recruteur.url == (
        "https://labonnealternance.apprentissage.beta.gouv.fr"
        "/emploi/recruteurs_lba/85396596000018/unblocked"
    )
```

2. Vérifier l'échec : `python -m pytest tests/test_normalize.py` → `ModuleNotFoundError: No module named 'veille_alternance.normalize'`.

3. Implémentation (`src/veille_alternance/normalize.py`) :

```python
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
    )


def normaliser_recruteur(recruteur: dict, departement: str) -> Recruteur:
    lieu = recruteur["workplace"]
    naf = lieu["domain"]["naf"]
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
    )


def normaliser_reponse(reponse: dict, departement: str) -> tuple[list[Offre], list[Recruteur]]:
    offres = [normaliser_offre(job, departement) for job in reponse["jobs"]]
    recruteurs = [normaliser_recruteur(rec, departement) for rec in reponse["recruiters"]]
    return offres, recruteurs
```

4. Vérifier : `python -m pytest tests/test_normalize.py` → `6 passed`.

5. Commit : `git commit -m "normalize : Offre, Recruteur et nettoyage du HTML"`

---

### Tâche 4 — `process.py` : filtres et déduplication

Fichiers : `src/veille_alternance/process.py`, `tests/test_process.py`

1. Test (`tests/test_process.py`) :

```python
from veille_alternance.normalize import Offre, Recruteur
from veille_alternance.process import (
    dedupliquer_offres,
    dedupliquer_recruteurs,
    filtrer_contrat,
    filtrer_mots_cles,
    sans_accents,
)


def offre(**champs):
    valeurs = dict(
        cle="France Travail|1", source="France Travail", titre="Technicien réseau",
        entreprise=None, adresse="75001 Paris", departement="75",
        contrat=("Apprentissage",), teletravail=None, debut=None, niveau=None,
        romes=("M1810",), description="", url="https://exemple.test",
        publiee_le="2026-09-01T00:00:00.000Z",
    )
    valeurs.update(champs)
    return Offre(**valeurs)


def recruteur(siret, departement="75"):
    return Recruteur(
        siret=siret, nom="ACME", adresse="75001 Paris", departement=departement,
        taille=None, secteur=None, naf=None, site_web=None, telephone=None,
        url="https://exemple.test",
    )


def test_sans_accents():
    assert sans_accents("Réseaux Sécurité") == "reseaux securite"


def test_dedupliquer_offres_garde_la_premiere():
    a = offre(cle="X|1", departement="75")
    b = offre(cle="X|1", departement="92")
    c = offre(cle="X|2")
    assert dedupliquer_offres([a, b, c]) == [a, c]


def test_dedupliquer_recruteurs():
    a, b, c = recruteur("111", "75"), recruteur("111", "92"), recruteur("222")
    assert dedupliquer_recruteurs([a, b, c]) == [a, c]


def test_filtrer_contrat():
    appr = offre(cle="X|1", contrat=("Apprentissage",))
    pro = offre(cle="X|2", contrat=("Professionnalisation",))
    les_deux = offre(cle="X|3", contrat=("Apprentissage", "Professionnalisation"))
    assert filtrer_contrat([appr, pro, les_deux], ["Apprentissage"]) == [appr, les_deux]


def test_filtrer_mots_cles_titre_et_description():
    titre = offre(cle="X|1", titre="Administrateur Systèmes")
    description = offre(cle="X|2", titre="Alternant IT", description="Gestion du RÉSEAU")
    hors_sujet = offre(cle="X|3", titre="Assistant comptable", description="Saisie")
    resultat = filtrer_mots_cles([titre, description, hors_sujet], ["systeme", "reseau"], [])
    assert resultat == [titre, description]


def test_filtrer_mots_cles_exclusion_sur_titre():
    marketing = offre(cle="X|1", titre="Chef de projet Marketing", description="réseau")
    garde = offre(cle="X|2", titre="Technicien réseau", description="marketing digital")
    resultat = filtrer_mots_cles([marketing, garde], ["reseau"], ["marketing"])
    assert resultat == [garde]
```

2. Vérifier l'échec : `python -m pytest tests/test_process.py` → `ModuleNotFoundError: No module named 'veille_alternance.process'`.

3. Implémentation (`src/veille_alternance/process.py`) :

```python
"""Filtres et déduplication — fonctions pures, sans accès disque ni réseau."""

import unicodedata

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


def dedupliquer_recruteurs(recruteurs: list[Recruteur]) -> list[Recruteur]:
    vus: set[str] = set()
    resultat = []
    for recruteur in recruteurs:
        if recruteur.siret not in vus:
            vus.add(recruteur.siret)
            resultat.append(recruteur)
    return resultat


def filtrer_contrat(offres: list[Offre], types_contrat: list[str]) -> list[Offre]:
    return [o for o in offres if any(t in types_contrat for t in o.contrat)]


def filtrer_mots_cles(
    offres: list[Offre], mots_cles: list[str], mots_exclus_titre: list[str]
) -> list[Offre]:
    cles = [sans_accents(m) for m in mots_cles]
    exclus = [sans_accents(m) for m in mots_exclus_titre]
    resultat = []
    for offre in offres:
        titre = sans_accents(offre.titre)
        texte = f"{titre} {sans_accents(offre.description)}"
        if any(m in titre for m in exclus):
            continue
        if any(m in texte for m in cles):
            resultat.append(offre)
    return resultat
```

4. Vérifier : `python -m pytest tests/test_process.py` → `6 passed`.

5. Commit : `git commit -m "process : filtres contrat et mots-clés, déduplication"`

---

### Tâche 5 — `collect.py` : boucle sur les départements

Fichiers : `src/veille_alternance/collect.py`, `tests/test_collect.py`

1. Test (`tests/test_collect.py`) :

```python
import json

from veille_alternance.collect import collecter, sources_saturees


class FauxClient:
    def __init__(self):
        self.appels = []

    def search(self, departement, romes):
        self.appels.append((departement, romes))
        return {"jobs": [], "recruiters": [], "warnings": [], "dep": departement}


def job(label):
    return {"identifier": {"partner_label": label}}


def test_collecter(tmp_path):
    client = FauxClient()
    attentes = []
    resultats = collecter(
        client, ["75", "45"], ["M1801"], tmp_path, 1.1, "2026-09-26_080000",
        sleep=attentes.append,
    )
    assert client.appels == [("75", ["M1801"]), ("45", ["M1801"])]
    assert [dep for dep, _ in resultats] == ["75", "45"]
    assert attentes == [1.1]
    brut = json.loads((tmp_path / "2026-09-26_080000_dep45.json").read_text(encoding="utf-8"))
    assert brut["dep"] == "45"


def test_sources_saturees():
    reponse = {
        "jobs": [job("France Travail")] * 150 + [job("offres_emploi_lba")] * 3
        + [job("Meteojob")] * 100 + [job("PASS")] * 50,
        "recruiters": [],
    }
    assert sources_saturees(reponse) == ["France Travail", "partenaires"]


def test_sources_non_saturees():
    assert sources_saturees({"jobs": [job("France Travail")] * 149, "recruiters": []}) == []
```

2. Vérifier l'échec : `python -m pytest tests/test_collect.py` → `ModuleNotFoundError: No module named 'veille_alternance.collect'`.

3. Implémentation (`src/veille_alternance/collect.py`) :

```python
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
```

4. Vérifier : `python -m pytest tests/test_collect.py` → `3 passed`.

5. Commit : `git commit -m "collect : boucle départements, sauvegarde brute, détection de saturation"`

---

### Tâche 6 — `output.py` : écriture JSON

Fichiers : `src/veille_alternance/output.py`, `tests/test_output.py`

1. Test (`tests/test_output.py`) :

```python
import json

from veille_alternance.normalize import Recruteur
from veille_alternance.output import ecrire_json


def test_ecrire_json(tmp_path):
    recruteur = Recruteur(
        siret="111", nom="Société Générale", adresse="75009 Paris", departement="75",
        taille="100-199", secteur=None, naf=None, site_web=None, telephone=None,
        url="https://exemple.test",
    )
    chemin = ecrire_json([recruteur], tmp_path / "processed" / "recruteurs.json")
    contenu = chemin.read_text(encoding="utf-8")
    assert "Société Générale" in contenu
    assert json.loads(contenu) == [{
        "siret": "111", "nom": "Société Générale", "adresse": "75009 Paris",
        "departement": "75", "taille": "100-199", "secteur": None, "naf": None,
        "site_web": None, "telephone": None, "url": "https://exemple.test",
    }]
```

2. Vérifier l'échec : `python -m pytest tests/test_output.py` → `ModuleNotFoundError: No module named 'veille_alternance.output'`.

3. Implémentation (`src/veille_alternance/output.py`) :

```python
"""Écriture des résultats en JSON lisible (UTF-8, indenté)."""

import json
from dataclasses import asdict
from pathlib import Path


def ecrire_json(elements: list, chemin: Path) -> Path:
    chemin.parent.mkdir(parents=True, exist_ok=True)
    donnees = [asdict(element) for element in elements]
    chemin.write_text(json.dumps(donnees, ensure_ascii=False, indent=2), encoding="utf-8")
    return chemin
```

4. Vérifier : `python -m pytest tests/test_output.py` → `1 passed`.

5. Commit : `git commit -m "output : écriture JSON des résultats"`

---

### Tâche 7 — `__main__.py` : orchestration

Fichiers : `src/veille_alternance/__main__.py`, `tests/test_main.py`

1. Test (`tests/test_main.py`), avec un faux client qui renvoie la fixture de production pour chaque département :

```python
import json
from pathlib import Path

from veille_alternance.__main__ import executer
from veille_alternance.config import Config

FIXTURE = Path(__file__).parent / "fixtures" / "jobsearch_prod_75_rome_M18xx_I14xx.json"


class FauxClient:
    def search(self, departement, romes):
        return json.loads(FIXTURE.read_text(encoding="utf-8"))


def config_test():
    return Config(
        api_key="cle-test", base_url="https://exemple.test/api", pause_entre_appels=0.0,
        timeout=5.0, departements=["75", "92"], romes=["M1801"],
        types_contrat=["Apprentissage"], mots_cles=["reseau", "systeme"],
        mots_exclus_titre=["marketing"],
    )


def test_executer(tmp_path):
    chemin_offres, chemin_recruteurs = executer(
        config_test(), FauxClient(), tmp_path, "2026-09-26_080000", "2026-09-26",
        sleep=lambda _: None,
    )
    assert chemin_offres == tmp_path / "processed" / "offres_2026-09-26.json"
    assert chemin_recruteurs == tmp_path / "processed" / "recruteurs_2026-09-26.json"
    assert (tmp_path / "raw" / "2026-09-26_080000_dep75.json").exists()
    assert (tmp_path / "raw" / "2026-09-26_080000_dep92.json").exists()

    offres = json.loads(chemin_offres.read_text(encoding="utf-8"))
    cles = [o["cle"] for o in offres]
    assert len(cles) == len(set(cles))
    assert len(offres) <= 30
    assert all("Apprentissage" in o["contrat"] for o in offres)
    assert all("marketing" not in o["titre"].lower() for o in offres)
    assert all(o["departement"] == "75" for o in offres)

    recruteurs = json.loads(chemin_recruteurs.read_text(encoding="utf-8"))
    assert len(recruteurs) == 150
```

2. Vérifier l'échec : `python -m pytest tests/test_main.py` → `ModuleNotFoundError: No module named 'veille_alternance.__main__'`.

3. Implémentation (`src/veille_alternance/__main__.py`) :

```python
"""Point d'entrée : python -m veille_alternance"""

import logging
import sys
import time
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

from veille_alternance.client import ApiError, LbaClient
from veille_alternance.collect import collecter
from veille_alternance.config import RACINE, Config, ConfigError, charger_config
from veille_alternance.normalize import normaliser_reponse
from veille_alternance.output import ecrire_json
from veille_alternance.process import (
    dedupliquer_offres,
    dedupliquer_recruteurs,
    filtrer_contrat,
    filtrer_mots_cles,
)

journal = logging.getLogger("veille_alternance")


def executer(
    config: Config,
    client,
    dossier_data: Path,
    horodatage: str,
    jour: str,
    sleep: Callable[[float], None] = time.sleep,
) -> tuple[Path, Path]:
    reponses = collecter(
        client, config.departements, config.romes, dossier_data / "raw",
        config.pause_entre_appels, horodatage, sleep=sleep,
    )
    offres, recruteurs = [], []
    for departement, reponse in reponses:
        offres_dep, recruteurs_dep = normaliser_reponse(reponse, departement)
        offres.extend(offres_dep)
        recruteurs.extend(recruteurs_dep)

    total_brut = len(offres)
    offres = dedupliquer_offres(offres)
    total_unique = len(offres)
    offres = filtrer_contrat(offres, config.types_contrat)
    offres = filtrer_mots_cles(offres, config.mots_cles, config.mots_exclus_titre)
    recruteurs = dedupliquer_recruteurs(recruteurs)

    journal.info(
        "Offres : %d brutes, %d uniques, %d retenues après filtres",
        total_brut, total_unique, len(offres),
    )
    journal.info("Recruteurs : %d uniques", len(recruteurs))

    dossier_sortie = dossier_data / "processed"
    chemin_offres = ecrire_json(offres, dossier_sortie / f"offres_{jour}.json")
    chemin_recruteurs = ecrire_json(recruteurs, dossier_sortie / f"recruteurs_{jour}.json")
    journal.info("Écrit : %s", chemin_offres)
    journal.info("Écrit : %s", chemin_recruteurs)
    return chemin_offres, chemin_recruteurs


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    try:
        config = charger_config()
        client = LbaClient(config.api_key, config.base_url, config.timeout)
        maintenant = datetime.now()
        executer(
            config, client, RACINE / "data",
            maintenant.strftime("%Y-%m-%d_%H%M%S"), maintenant.strftime("%Y-%m-%d"),
        )
    except (ConfigError, ApiError) as erreur:
        journal.error("%s", erreur)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

4. Vérifier : `python -m pytest` → `28 passed` (5 + 6 + 6 + 6 + 3 + 1 + 1).

5. Commit : `git commit -m "main : orchestration collecte → normalisation → filtres → JSON"`

---

### Tâche 8 — Premier vrai lancement et contrôle

Fichiers : aucun fichier de code ; mise à jour de `README.md`.

1. Lancer : `python -m veille_alternance`

2. Résultat attendu dans le terminal :
   - 9 lignes `INFO Département XX : N offres, N recruteurs` ;
   - une ligne `INFO Offres : N brutes, N uniques, N retenues après filtres` ;
   - une ligne `INFO Recruteurs : N uniques` ;
   - deux lignes `INFO Écrit : ...` ;
   - aucun `WARNING` de saturation (volume attendu : ~92 offres IT uniques avant filtres).

3. Contrôle manuel : ouvrir `data/processed/offres_AAAA-MM-JJ.json`, lire les titres retenus, et noter :
   - les offres pertinentes écartées à tort (→ ajouter un mot-clé) ;
   - les offres hors sujet retenues (→ ajouter une exclusion).
   Ajuster `config/search.toml` et relancer. Les réglages ne demandent aucune modification de code.

4. Vérifier que rien de sensible n'est versionné : `git status` ne doit montrer ni `.env` ni le contenu de `data/`.

5. Mettre à jour la section « État actuel » de `README.md` (V0 fonctionnelle, date, volumes observés).

6. Commit : `git commit -m "V0 fonctionnelle : premier lancement réel et réglage des filtres"`

---

## Points laissés ouverts volontairement (hors V0)

- Collecte exhaustive des recruteurs et filtre NAF (V1).
- Historique et détection des nouvelles offres (V1).
- Automatisation du lancement (tâche planifiée) : après validation de la V0.
