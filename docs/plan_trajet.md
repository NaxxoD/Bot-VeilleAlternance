# Plan — filtre par temps de trajet

**Objectif** : écarter des offres retenues celles qui sont à plus de 45 min en
transports (IDF, depuis départ A / départ B) ou à plus de 45 min en
voiture selon l'IGN (45 et 41, depuis départ Loiret (exemple)), en les gardant
visibles dans une section « trop loin » du rapport.

Spec : `docs/specs/2026-09-28-filtre-trajet-design.md`.

## Fichiers touchés

| Fichier | Changement |
|---|---|
| `src/veille_alternance/config.py` | champs `trajet_*` et `prim_api_key`, section `[trajet]` |
| `src/veille_alternance/normalize.py` | `Offre.latitude`, `Offre.longitude`, `Offre.trajet_min` |
| `src/veille_alternance/trajet.py` | **nouveau** : géocodage, clients PRIM/IGN, cache, `Trajets` |
| `src/veille_alternance/output.py` | colonne `trajet_min` dans les CSV d'offres |
| `src/veille_alternance/rapport.py` | colonne « Trajet », section repliée « Trop loin » |
| `src/veille_alternance/__main__.py` | appel de `Trajets.repartir` après le filtre mots-clés |
| `config/search.toml` | département 41, section `[trajet]` |
| `.env.example` | `PRIM_API_KEY` |
| `tests/test_config.py`, `test_normalize.py`, `test_trajet.py` (nouveau), `test_output.py`, `test_main.py` | tests |
| `tests/fixtures/prim_journeys_idf_cergy.json`, `ign_geocodage_95000_cergy.json`, `ign_itineraire_loiret_orleans.json` | déjà enregistrées le 2026-09-28 |
| `README.md` | état actuel |

Effet de bord connu : les JSON d'offres et le vivier gagnent les clés
`latitude`, `longitude`, `trajet_min`. Bot_Tri_Alternance lit ces fichiers par
clé (`o["cle"]`), les clés en plus sont sans effet. Ses « retenues » de
comparaison diminuent des offres trop loin.

---

### Tâche 1 — Configuration `[trajet]`

Fichiers : `src/veille_alternance/config.py`, `tests/test_config.py`

1. Test qui échoue — ajouter à la fin de `tests/test_config.py` :

```python
TOML_TRAJET = TOML + """
[trajet]
actif = true

[trajet.transports]
departs = [[2.347, 48.859], [2.32, 48.865]]
heure_depart = "08:00"
max_minutes = 45

[trajet.voiture]
departements = ["45", "41"]
depart = [1.88, 47.85]
max_minutes = 40
"""


def ecrire_toml(tmp_path, contenu):
    chemin = tmp_path / "search.toml"
    chemin.write_text(contenu, encoding="utf-8")
    return chemin


def test_charger_config_trajet(tmp_path, monkeypatch):
    monkeypatch.setenv("LBA_API_KEY", "cle-de-test")
    monkeypatch.setenv("PRIM_API_KEY", "jeton-prim")
    config = charger_config(ecrire_toml(tmp_path, TOML_TRAJET), tmp_path / "absent.env")
    assert config.trajet_actif is True
    assert config.prim_api_key == "jeton-prim"
    assert config.trajet_departs_transports == [(2.347, 48.859), (2.32, 48.865)]
    assert config.trajet_heure_depart == "08:00"
    assert config.trajet_max_transports == 45.0
    assert config.trajet_departements_voiture == ["45", "41"]
    assert config.trajet_depart_voiture == (1.88, 47.85)
    assert config.trajet_max_voiture == 40.0


def test_trajet_actif_sans_jeton_prim(tmp_path, monkeypatch):
    monkeypatch.setenv("LBA_API_KEY", "cle-de-test")
    monkeypatch.delenv("PRIM_API_KEY", raising=False)
    with pytest.raises(ConfigError, match="PRIM_API_KEY"):
        charger_config(ecrire_toml(tmp_path, TOML_TRAJET), tmp_path / "absent.env")


def test_trajet_voiture_sans_point_de_depart(tmp_path, monkeypatch):
    monkeypatch.setenv("LBA_API_KEY", "cle-de-test")
    monkeypatch.setenv("PRIM_API_KEY", "jeton-prim")
    contenu = TOML_TRAJET.replace("depart = [1.88, 47.85]\n", "")
    with pytest.raises(ConfigError, match="depart"):
        charger_config(ecrire_toml(tmp_path, contenu), tmp_path / "absent.env")


def test_trajet_desactive_sans_section(tmp_path, monkeypatch):
    monkeypatch.setenv("LBA_API_KEY", "cle-de-test")
    config = charger_config(ecrire_toml(tmp_path, TOML), tmp_path / "absent.env")
    assert config.trajet_actif is False
    assert config.trajet_departs_transports == []
```

2. Vérifier l'échec : `python -m pytest tests/test_config.py -q`
   → `AttributeError: 'Config' object has no attribute 'trajet_actif'`.

3. Implémenter — dans `Config`, après `organismes_exclus` :

```python
    trajet_actif: bool = False
    prim_api_key: str = ""
    trajet_departs_transports: list[tuple[float, float]] = field(default_factory=list)
    trajet_heure_depart: str = "08:00"
    trajet_max_transports: float = 45.0
    trajet_departements_voiture: list[str] = field(default_factory=list)
    trajet_depart_voiture: tuple[float, float] | None = None  # (longitude, latitude)
    trajet_max_voiture: float = 45.0
```

Dans `charger_config`, juste avant `return Config(` :

```python
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
```

Et dans l'appel `Config(...)`, après `organismes_exclus=...` :

```python
        trajet_actif=trajet_actif,
        prim_api_key=prim_api_key,
        trajet_departs_transports=[tuple(point) for point in transports.get("departs", [])],
        trajet_heure_depart=transports.get("heure_depart", "08:00"),
        trajet_max_transports=float(transports.get("max_minutes", 45)),
        trajet_departements_voiture=list(voiture.get("departements", [])),
        trajet_depart_voiture=tuple(depart_voiture) if depart_voiture else None,
        trajet_max_voiture=float(voiture.get("max_minutes", 45)),
```

4. Vérifier : `python -m pytest tests/test_config.py -q` → tout passe.
5. Commit : `git commit -m "Configuration du filtre par temps de trajet"`

---

### Tâche 2 — Coordonnées des offres

Fichiers : `src/veille_alternance/normalize.py`, `tests/test_normalize.py`

1. Test qui échoue — ajouter à `tests/test_normalize.py` :

```python
def test_coordonnees_lba():
    offres, _ = normaliser_reponse(json.loads(FIXTURE.read_text(encoding="utf-8")), "75")
    assert (offres[0].longitude, offres[0].latitude) == (2.347, 48.859)
    assert offres[0].trajet_min is None


def test_coordonnees_france_travail():
    resultats = charger_ft()["resultats"]
    offre = normaliser_offre_ft(resultats[0], "75")
    assert (offre.longitude, offre.latitude) == (2.388195, 48.840813)
    sans = normaliser_offre_ft(resultats[2], "75")  # lieuTravail = {"libelle": "75 - Paris"}
    assert (sans.longitude, sans.latitude) == (None, None)
```

2. Vérifier l'échec → `AttributeError: 'Offre' object has no attribute 'longitude'`.

3. Implémenter — dans `Offre`, après `naf` :

```python
    latitude: float | None = None  # lieu de travail, quand la source le donne
    longitude: float | None = None
    trajet_min: int | None = None  # depuis le domicile, renseigné par trajet
```

Dans `normaliser_offre` (LBA), avant `return Offre(` :

```python
    geopoint = job["workplace"]["location"].get("geopoint") or {}
    longitude, latitude = (geopoint.get("coordinates") or [None, None])[:2]
```

et dans l'appel, après `naf=...` : `latitude=latitude, longitude=longitude,`

Dans `normaliser_offre_ft`, après `naf=offre.get("codeNAF"),` :

```python
        latitude=lieu.get("latitude"),
        longitude=lieu.get("longitude"),
```

4. Vérifier : `python -m pytest -q` → tout passe (les tests existants aussi).
5. Commit : `git commit -m "Coordonnées du lieu de travail dans les offres"`

---

### Tâche 3 — Clients PRIM, IGN et géocodage

Fichiers : `src/veille_alternance/trajet.py` (nouveau), `tests/test_trajet.py` (nouveau)

1. Test qui échoue — créer `tests/test_trajet.py` :

```python
import json
from datetime import datetime
from pathlib import Path

import requests

from veille_alternance.trajet import (
    ClientTransports,
    ClientVoiture,
    Geocodeur,
    prochain_jour_ouvre,
)

FIXTURES = Path(__file__).parent / "fixtures"


def charger(nom):
    return json.loads((FIXTURES / nom).read_text(encoding="utf-8"))


class FausseReponse:
    def __init__(self, status_code, payload=None):
        self.status_code = status_code
        self._payload = payload

    def json(self):
        return self._payload


class FausseSession:
    def __init__(self, reponse):
        self.reponse = reponse
        self.appels = []
        self.headers = {}

    def get(self, url, params=None, timeout=None):
        self.appels.append((url, params))
        if isinstance(self.reponse, Exception):
            raise self.reponse
        return self.reponse


def test_prochain_jour_ouvre_en_semaine():
    # lundi 28 septembre 2026 au soir → mardi 8 h
    assert prochain_jour_ouvre(datetime(2026, 9, 28, 20, 0), "08:00") == "20260929T080000"


def test_prochain_jour_ouvre_saute_le_week_end():
    # vendredi 2 octobre 2026 → lundi 5 octobre
    assert prochain_jour_ouvre(datetime(2026, 10, 2, 9, 0), "08:30") == "20261005T083000"


def test_geocodeur():
    session = FausseSession(FausseReponse(200, charger("ign_geocodage_95000_cergy.json")))
    point = Geocodeur(session=session, sleep=lambda _: None).localiser("95000 Cergy")
    assert point == (2.045547, 49.04227)
    assert session.appels[0][1]["q"] == "95000 Cergy"


def test_geocodeur_adresse_introuvable():
    session = FausseSession(FausseReponse(200, {"type": "FeatureCollection", "features": []}))
    assert Geocodeur(session=session, sleep=lambda _: None).localiser("zzz") is None


def test_client_voiture():
    session = FausseSession(FausseReponse(200, charger("ign_itineraire_loiret_orleans.json")))
    client = ClientVoiture(session=session, sleep=lambda _: None)
    duree = client.duree_minutes((1.88, 47.85), (1.909251, 47.902964))
    assert duree == 32.835
    assert session.appels[0][1]["start"] == "1.88,47.85"
    assert session.appels[0][1]["profile"] == "car"


def test_client_transports_garde_le_plus_court():
    session = FausseSession(FausseReponse(200, charger("prim_journeys_idf_cergy.json")))
    client = ClientTransports(
        "jeton", "08:00", session=session, maintenant=lambda: datetime(2026, 9, 28, 20, 0)
    )
    duree = client.duree_minutes((2.347, 48.859), (2.063, 49.036))
    assert duree == 4269 / 60  # « best » : le plus court des 4 itinéraires
    assert session.headers["apikey"] == "jeton"
    assert session.appels[0][1] == {
        "from": "2.347;48.859", "to": "2.063;49.036", "datetime": "20260929T080000",
    }


def test_erreur_http_donne_un_trajet_inconnu():
    session = FausseSession(FausseReponse(401, {"message": "Invalid key"}))
    assert ClientTransports("mauvais", session=session).duree_minutes((0, 0), (1, 1)) is None


def test_erreur_reseau_donne_un_trajet_inconnu():
    session = FausseSession(requests.ConnectionError("hors ligne"))
    client = ClientVoiture(session=session, sleep=lambda _: None)
    assert client.duree_minutes((0, 0), (1, 1)) is None
```

2. Vérifier l'échec → `ModuleNotFoundError: No module named 'veille_alternance.trajet'`.

3. Implémenter — créer `src/veille_alternance/trajet.py` :

```python
"""Temps de trajet depuis le domicile, pour écarter les offres trop lointaines.

Île-de-France : transports en commun, API calculateur PRIM (Île-de-France Mobilités).
Loiret et environs : voiture, API itinéraire de la Géoplateforme IGN (sans trafic).
Une erreur réseau ne fait jamais échouer la veille : le trajet devient inconnu (None)
et l'offre est gardée.
"""

import logging
import time
from collections.abc import Callable
from datetime import datetime, timedelta

import requests

GEOCODAGE_URL = "https://data.geopf.fr/geocodage/search"
ITINERAIRE_URL = "https://data.geopf.fr/navigation/itineraire"
PRIM_URL = "https://prim.iledefrance-mobilites.fr/marketplace/v2/navitia/journeys"
PAUSE_IGN = 0.25  # secondes ; limite IGN = 5 requêtes/s par adresse IP

Point = tuple[float, float]  # (longitude, latitude)

journal = logging.getLogger(__name__)


def _get_json(session, url: str, params: dict, timeout: float) -> dict | None:
    """GET qui renvoie None au lieu de lever une exception : le trajet devient inconnu."""
    try:
        reponse = session.get(url, params=params, timeout=timeout)
    except requests.RequestException as erreur:
        journal.warning("Trajet : %s injoignable (%s)", url, erreur)
        return None
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

    def duree_minutes(self, depart: Point, arrivee: Point) -> float | None:
        donnees = _get_json(
            self._session, PRIM_URL,
            {
                "from": f"{depart[0]};{depart[1]}",
                "to": f"{arrivee[0]};{arrivee[1]}",
                "datetime": prochain_jour_ouvre(self._maintenant(), self._heure_depart),
            },
            self._timeout,
        )
        itineraires = (donnees or {}).get("journeys") or []
        if not itineraires:
            return None
        return min(itineraire["duration"] for itineraire in itineraires) / 60
```

4. Vérifier : `python -m pytest tests/test_trajet.py -q` → 8 passed.
5. Commit : `git commit -m "Clients de temps de trajet : PRIM, IGN et géocodage"`

---

### Tâche 4 — Répartition des offres et cache

Fichiers : `src/veille_alternance/trajet.py`, `tests/test_trajet.py`

1. Test qui échoue — ajouter à `tests/test_trajet.py` :

```python
from veille_alternance.config import Config
from veille_alternance.normalize import Offre
from veille_alternance.trajet import CacheTrajets, Trajets


def offre(cle, departement, adresse="75012 Paris", longitude=None, latitude=None):
    return Offre(
        cle=cle, source="France Travail", titre="Technicien", entreprise=None,
        adresse=adresse, departement=departement, contrat=("Apprentissage",),
        teletravail=None, debut=None, niveau=None, romes=(), description="",
        url="https://exemple.test", publiee_le=None, longitude=longitude, latitude=latitude,
    )


def config_trajet():
    return Config(
        api_key="k", base_url="u", pause_entre_appels=0.0, timeout=5.0, departements=[],
        romes=[], types_contrat=[], mots_cles_titre=[], mots_cles_description=[],
        mots_exclus_titre=[], dossier_raw=Path("raw"), trajet_actif=True,
        prim_api_key="jeton", trajet_departs_transports=[(2.43, 48.84), (2.42, 48.84)],
        trajet_max_transports=45.0, trajet_departements_voiture=["45", "41"],
        trajet_depart_voiture=(1.92, 47.72), trajet_max_voiture=45.0,
    )


class FauxClient:
    """Durée par (départ, arrivée), sinon par arrivée seule ; None si inconnue."""

    def __init__(self, durees):
        self.durees = durees
        self.appels = []

    def duree_minutes(self, depart, arrivee):
        self.appels.append((depart, arrivee))
        return self.durees.get((depart, arrivee), self.durees.get(arrivee))


class FauxGeocodeur:
    def __init__(self, points):
        self.points = points
        self.appels = []

    def localiser(self, adresse):
        self.appels.append(adresse)
        return self.points.get(adresse)


def creer_trajets(tmp_path, transports=None, voiture=None, geocodeur=None):
    return Trajets(
        config_trajet(), geocodeur or FauxGeocodeur({}), transports or FauxClient({}),
        voiture or FauxClient({}), CacheTrajets(tmp_path / "cache.json"),
    )


def test_repartit_selon_le_seuil(tmp_path):
    transports = FauxClient({(2.38, 48.84): 30.0, (2.06, 49.03): 71.2})
    proches, trop_loin = creer_trajets(tmp_path, transports=transports).repartir([
        offre("A", "75", longitude=2.38, latitude=48.84),
        offre("B", "95", longitude=2.06, latitude=49.03),
    ])
    assert [(o.cle, o.trajet_min) for o in proches] == [("A", 30)]
    assert [(o.cle, o.trajet_min) for o in trop_loin] == [("B", 71)]


def test_garde_le_plus_court_des_deux_departs(tmp_path):
    arrivee = (2.25, 48.89)
    transports = FauxClient({((2.43, 48.84), arrivee): 50.0, ((2.42, 48.84), arrivee): 44.0})
    proches, trop_loin = creer_trajets(tmp_path, transports=transports).repartir(
        [offre("A", "92", longitude=2.25, latitude=48.89)]
    )
    assert [o.trajet_min for o in proches] == [44]
    assert trop_loin == []


def test_loiret_en_voiture(tmp_path):
    arrivee = (1.90, 47.90)
    transports = FauxClient({arrivee: 999.0})
    voiture = FauxClient({arrivee: 33.0})
    proches, _ = creer_trajets(tmp_path, transports=transports, voiture=voiture).repartir(
        [offre("A", "45", longitude=1.90, latitude=47.90)]
    )
    assert [o.trajet_min for o in proches] == [33]
    assert voiture.appels == [((1.92, 47.72), arrivee)]
    assert transports.appels == []


def test_trajet_inconnu_garde_l_offre(tmp_path):
    proches, trop_loin = creer_trajets(tmp_path).repartir(
        [offre("A", "75", adresse="adresse introuvable")]
    )
    assert [(o.cle, o.trajet_min) for o in proches] == [("A", None)]
    assert trop_loin == []


def test_geocode_les_offres_sans_coordonnees(tmp_path):
    geocodeur = FauxGeocodeur({"95000 Cergy": (2.05, 49.04)})
    transports = FauxClient({(2.05, 49.04): 71.0})
    _, trop_loin = creer_trajets(tmp_path, transports=transports, geocodeur=geocodeur).repartir(
        [offre("A", "95", adresse="95000 Cergy")]
    )
    assert [o.trajet_min for o in trop_loin] == [71]
    assert geocodeur.appels == ["95000 Cergy"]


def test_cache_evite_les_appels_repetes(tmp_path):
    geocodeur = FauxGeocodeur({"75012 Paris": (2.38, 48.84)})
    transports = FauxClient({(2.38, 48.84): 30.0})
    creer_trajets(tmp_path, transports=transports, geocodeur=geocodeur).repartir(
        [offre("A", "75")]
    )
    assert len(transports.appels) == 2  # un appel par point de départ
    # Nouvel objet : le cache est relu depuis le disque
    creer_trajets(tmp_path, transports=transports, geocodeur=geocodeur).repartir(
        [offre("B", "75")]
    )
    assert len(transports.appels) == 2
    assert geocodeur.appels == ["75012 Paris"]
```

2. Vérifier l'échec → `ImportError: cannot import name 'CacheTrajets'`.

3. Implémenter — dans `trajet.py`, compléter les imports :

```python
import json
import logging
import time
from collections.abc import Callable
from dataclasses import replace
from datetime import datetime, timedelta
from pathlib import Path

import requests

from veille_alternance.config import Config
from veille_alternance.normalize import Offre
```

puis ajouter à la fin du fichier :

```python
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

    def _en_voiture(self, offre: Offre) -> bool:
        return offre.departement in self._config.trajet_departements_voiture

    def _point(self, offre: Offre) -> Point | None:
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

    def minutes(self, offre: Offre) -> float | None:
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

    def repartir(self, offres: list[Offre]) -> tuple[list[Offre], list[Offre]]:
        """(offres dans le périmètre ou au trajet inconnu, offres trop loin)."""
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
            journal.warning("Trajet inconnu pour %d offres, gardées par prudence", inconnus)
        return proches, trop_loin
```

4. Vérifier : `python -m pytest tests/test_trajet.py -q` → 14 passed.
5. Commit : `git commit -m "Répartition des offres selon le temps de trajet, avec cache"`

---

### Tâche 5 — CSV et rapport

Fichiers : `src/veille_alternance/output.py`, `src/veille_alternance/rapport.py`, `tests/test_output.py`

1. Tests — dans `tests/test_output.py`, remplacer l'assertion `lignes == [...]` de
   `test_ecrire_csv_offres` par :

```python
    assert lignes == [
        "premiere_vue;departement;titre;entreprise;adresse;trajet_min;contrat;niveau;"
        "source;publiee_le;url",
        '2026-09-26;75;"Technicien réseau; H/F";;75012 Paris;;Apprentissage, '
        "Professionnalisation;5;France Travail;2026-09-03;https://exemple.test",
    ]
```

ajouter en tête `from dataclasses import replace`, et à la fin :

```python
def test_ecrire_html_affiche_le_trajet_et_les_offres_trop_loin(tmp_path):
    proche = replace(offre_html("A|1", "Technicien support", "2026-09-26"), trajet_min=38)
    inconnue = offre_html("B|2", "Administrateur systèmes", "2026-09-20")
    loin = replace(offre_html("C|3", "Technicien Cergy", "2026-09-26"), trajet_min=71)
    page = ecrire_html(
        [proche, inconnue], [], tmp_path / "r.html", "2026-09-26", trop_loin=[loin]
    ).read_text(encoding="utf-8")
    assert "38 min" in page
    assert "<td>?</td>" in page  # trajet inconnu
    assert "Trop loin — 1 offre écartée" in page
    assert page.index("Technicien Cergy") > page.index("<details>")
    assert "71 min" in page
    assert "2 offres actives" in page


def test_ecrire_html_sans_offre_trop_loin(tmp_path):
    page = ecrire_html(
        [offre_html("A|1", "Technicien", "2026-09-26")], [], tmp_path / "r.html", "2026-09-26"
    ).read_text(encoding="utf-8")
    assert "<details>" not in page
```

2. Vérifier l'échec : `python -m pytest tests/test_output.py -q` → 3 échecs
   (en-tête CSV, `trop_loin` inconnu).

3. Implémenter — `output.py` :

```python
COLONNES_OFFRES = [
    "premiere_vue", "departement", "titre", "entreprise", "adresse", "trajet_min", "contrat",
    "niveau", "source", "publiee_le", "url",
]
```

`rapport.py` — ajouter après `_pluriel` :

```python
def _trajet(offre) -> str:
    return "?" if offre.trajet_min is None else f"{offre.trajet_min} min"
```

dans `_ligne_offre`, remplacer la ligne de l'entreprise et du lieu par :

```python
        f"<td>{_e(offre.entreprise or '—')}</td><td>{_e(offre.adresse)}</td>"
        f"<td>{_trajet(offre)}</td>"
```

`ENTETE_OFFRES` devient :

```python
ENTETE_OFFRES = (
    "<tr><th></th><th>Dép.</th><th>Offre</th><th>Entreprise</th><th>Lieu</th>"
    "<th>Trajet</th><th>Source</th><th>Publiée</th><th>Vue le</th></tr>"
)
```

dans `MODELE`, ajouter à la fin du CSS (avant `</style>`) :

```css
summary { cursor:pointer; font-size:1.15rem; font-weight:600; margin:0 0 10px; }
```

et remplacer la ligne `<section><h2>__TITRE_OFFRES__</h2>__TABLE_OFFRES__</section>` par :

```html
<section><h2>__TITRE_OFFRES__</h2>__TABLE_OFFRES__</section>
__SECTION_TROP_LOIN__
```

`ecrire_html` devient :

```python
def ecrire_html(
    offres: list, recruteurs: list, chemin: Path, jour: str, trop_loin: list | None = None
) -> Path:
    trop_loin = trop_loin or []
    nouvelles = [o for o in offres if o.premiere_vue == jour]
    departements = sorted(
        {o.departement for o in offres + trop_loin} | {r.departement for r in recruteurs}
    )
    section_trop_loin = ""
    if trop_loin:
        section_trop_loin = (
            "<section><details><summary>Trop loin — "
            f"{_pluriel(len(trop_loin), 'offre écartée', 'offres écartées')}"
            " par le temps de trajet</summary>"
            f"{_table(ENTETE_OFFRES, [_ligne_offre(o, jour) for o in trop_loin], '')}"
            "</details></section>"
        )
    remplacements = {
        "__JOUR_FR__": _date_fr(jour),
        "__NB_NOUVELLES__": str(len(nouvelles)),
        "__NB_OFFRES__": str(len(offres)),
        "__NB_RECRUTEURS__": str(len(recruteurs)),
        "__OPTIONS__": "".join(f'<option value="{_e(d)}">{_e(d)}</option>' for d in departements),
        "__TITRE_NOUVELLES__": _pluriel(len(nouvelles), "nouvelle offre", "nouvelles offres"),
        "__TITRE_OFFRES__": _pluriel(len(offres), "offre active", "offres actives"),
        "__TITRE_RECRUTEURS__": _pluriel(len(recruteurs), "entreprise", "entreprises"),
        "__TABLE_NOUVELLES__": _table(
            ENTETE_OFFRES, [_ligne_offre(o, jour) for o in nouvelles],
            "Rien de nouveau aujourd'hui."),
        "__TABLE_OFFRES__": _table(
            ENTETE_OFFRES, [_ligne_offre(o, jour) for o in offres], "Aucune offre."),
        "__SECTION_TROP_LOIN__": section_trop_loin,
        "__TABLE_RECRUTEURS__": _table(
            ENTETE_RECRUTEURS, [_ligne_recruteur(r) for r in recruteurs], "Aucune entreprise."),
    }
    page = MODELE
    for marqueur, valeur in remplacements.items():
        page = page.replace(marqueur, valeur)
    chemin.parent.mkdir(parents=True, exist_ok=True)
    chemin.write_text(page, encoding="utf-8")
    return chemin
```

4. Vérifier : `python -m pytest tests/test_output.py -q` → tout passe.
5. Commit : `git commit -m "Temps de trajet et section « trop loin » dans le CSV et le rapport"`

---

### Tâche 6 — Branchement dans la veille

Fichiers : `src/veille_alternance/__main__.py`, `tests/test_main.py`

1. Test qui échoue — ajouter à `tests/test_main.py` :

```python
from dataclasses import replace


class FauxTrajets:
    """Envoie « trop loin » les offres HelpDesk, garde les autres à 20 min."""

    def repartir(self, offres):
        proches = [replace(o, trajet_min=20) for o in offres if "HelpDesk" not in o.titre]
        loin = [replace(o, trajet_min=90) for o in offres if "HelpDesk" in o.titre]
        return proches, loin


def test_executer_ecarte_les_offres_trop_loin(tmp_path):
    config = config_test(tmp_path / "raw")
    config = Config(**{**config.__dict__, "departements": ["75"], "mots_cles_titre": ["helpdesk"]})
    historique = tmp_path / "historique.json"
    sortie = tmp_path / "processed"
    chemin_offres, _ = executer(
        config, ClientDoublonContrat(), sortie, "h", "2026-09-26",
        chemin_historique=historique, trajets=FauxTrajets(), sleep=lambda _: None,
    )
    assert json.loads(chemin_offres.read_text(encoding="utf-8")) == []
    resume = json.loads((sortie / "resume.json").read_text(encoding="utf-8"))
    assert resume["nb_nouvelles"] == 0  # pas de notification pour une offre trop loin
    assert json.loads(historique.read_text(encoding="utf-8")) == {}
    page = (sortie / "rapport.html").read_text(encoding="utf-8")
    assert "Trop loin — 1 offre écartée" in page
    assert "90 min" in page
```

2. Vérifier l'échec → `TypeError: executer() got an unexpected keyword argument 'trajets'`.

3. Implémenter — `__main__.py` :

import à ajouter :

```python
from veille_alternance.trajet import (
    CacheTrajets,
    ClientTransports,
    ClientVoiture,
    Geocodeur,
    Trajets,
)
```

signature d'`executer` : ajouter `trajets=None,` après `client_ft=None,`.

juste après l'appel à `filtrer_mots_cles(...)` :

```python
    # Après les mots-clés : ~20 offres à calculer au lieu de ~1 700. Les offres trop
    # loin ne passent pas par l'historique : pas de notification pour elles.
    trop_loin = []
    if trajets is not None:
        offres, trop_loin = trajets.repartir(offres)
        journal.info(
            "Trajet : %d offres dans le périmètre, %d trop loin", len(offres), len(trop_loin)
        )
```

les deux appels à `ecrire_html` reçoivent `trop_loin=trop_loin` :

```python
    rapport = ecrire_html(
        offres, recruteurs, dossier_sortie / f"rapport_{jour}.html", jour, trop_loin=trop_loin
    )
    # Copie sous un nom fixe : toujours le dernier rapport, à mettre en favori
    ecrire_html(offres, recruteurs, dossier_sortie / "rapport.html", jour, trop_loin=trop_loin)
```

dans `main()`, après la création de `client_ft` :

```python
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
```

et l'appel `executer(...)` reçoit `trajets=trajets,` après `client_ft=client_ft,`.

4. Vérifier : `python -m pytest -q` → tout passe (73 + nouveaux).
5. Commit : `git commit -m "Filtre par temps de trajet branché dans la veille"`

---

### Tâche 7 — Configuration réelle, lancement, documentation

Fichiers : `config/search.toml`, `.env.example`, `README.md`

1. `config/search.toml` — dans `[recherche]` :

```toml
departements = ["75", "77", "78", "91", "92", "93", "94", "95", "45", "41"]
```

et ajouter à la fin :

```toml
[trajet]
# Temps de trajet depuis le domicile ; au-delà du seuil, l'offre passe dans la
# section « trop loin » du rapport. Spec : docs/specs/2026-09-28-filtre-trajet-design.md
actif = true

[trajet.transports]
# Île-de-France, transports en commun (API PRIM, jeton PRIM_API_KEY dans .env).
# Points de départ [longitude, latitude] : le plus court des deux est gardé.
departs = [
  [2.347, 48.859],  # départ A (exemple)
  [2.32, 48.865],   # départ B (exemple)
]
heure_depart = "08:00"    # prochain jour ouvré
max_minutes = 45

[trajet.voiture]
# Loiret et Loir-et-Cher, voiture (API IGN, sans trafic ; l'IGN compte large sur
# les petites routes, seuil calé sur Saran 27 min / Châteauneuf-sur-Loire 45 min)
departements = ["45", "41"]
depart = [1.88, 47.85]  # départ Loiret (exemple)
max_minutes = 45
```

2. `.env.example` — ajouter :

```
# Île-de-France Mobilités (PRIM) : jeton sur https://prim.iledefrance-mobilites.fr
# (API « Calculateur Île-de-France Mobilités – Accès générique v2 »)
PRIM_API_KEY=
```

3. Vérifier : `python -m pytest -q` → tout passe ; puis lancement réel
   `python -m veille_alternance` → le journal affiche
   `Trajet : N offres dans le périmètre, M trop loin` ; `rapport.html` montre la
   colonne Trajet et la section « Trop loin » (Cergy, Rambouillet, Médan,
   Guyancourt attendus dedans).

4. `README.md` — dans « État actuel », ajouter un paragraphe :

```markdown
Filtre par temps de trajet (2026-09-28) : après les mots-clés, chaque offre
reçoit `trajet_min` — transports en commun depuis départ A / départ B
via l'API PRIM (jeton `PRIM_API_KEY`), ou voiture depuis départ Loiret (exemple) via
l'API IGN pour les départements 45 et 41. Seuil 45 min dans les deux cas
(`[trajet]` de search.toml). Au-delà : section « Trop loin » du rapport, hors
historique et hors notification. Trajet incalculable → offre gardée, « ? ».
Cache : `data/cache_trajets.json` (supprimable). Département 41 ajouté pour
une commune du 41. Spec : `docs/specs/2026-09-28-filtre-trajet-design.md`.
```

5. Commit : `git commit -m "Filtre par temps de trajet activé (45 min, départements 41 ajouté)"`

---

## Auto-revue

- Exigences de la spec → tâches : mesure et API (3), deux départs + minimum (4),
  base selon département (4), seuils (1, 4), trop loin visible (5), hors
  historique / notification (6), trajet inconnu gardé (3, 4), cache (4),
  département 41 (7), `PRIM_API_KEY` (1, 7), fixtures réelles (3), vivier
  inchangé en contenu (6 : `vivier` capturé avant `trajets.repartir`).
- Noms constants : `Trajets.repartir`, `CacheTrajets`, `Geocodeur.localiser`,
  `ClientTransports.duree_minutes`, `ClientVoiture.duree_minutes`,
  `trajet_min`, `trajet_*` de `Config`.
- Import circulaire : `trajet` importe `config` et `normalize`, qui n'importent
  pas `trajet` ; `__main__` importe `trajet`. Pas de cycle.
