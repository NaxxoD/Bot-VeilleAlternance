import json
from datetime import datetime
from pathlib import Path

import requests

from veille_alternance.config import Config
from veille_alternance.normalize import Offre, Recruteur
from veille_alternance.trajet import (
    CacheTrajets,
    ClientTransports,
    ClientVoiture,
    Geocodeur,
    Trajets,
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


class SessionParPoint:
    """Répond « no_solution » (404) sauf pour les points listés dans `reussis`."""

    def __init__(self, reussis, duree=3000):
        self.reussis, self.duree = reussis, duree
        self.appels = []
        self.headers = {}

    def get(self, url, params=None, timeout=None):
        self.appels.append(params["to"])
        if params["to"] in self.reussis:
            return FausseReponse(200, {"journeys": [{"duration": self.reussis[params["to"]]}]})
        return FausseReponse(404, {"error": {"id": "no_solution"}})


def test_no_solution_reessaie_autour_du_point_et_garde_la_mediane():
    session = SessionParPoint({"2.221;48.841": 2700, "2.219;48.841": 3000, "2.22;48.842": 3600})
    client = ClientTransports("jeton", session=session, maintenant=lambda: datetime(2026, 9, 28))
    assert client.duree_minutes((2.43, 48.85), (2.22, 48.841)) == 3000 / 60
    assert len(session.appels) == 5  # point exact puis 4 voisins


def test_no_solution_partout_donne_un_trajet_inconnu_sans_erreur_http(caplog):
    session = SessionParPoint({})
    client = ClientTransports("jeton", session=session, maintenant=lambda: datetime(2026, 9, 28))
    assert client.duree_minutes((2.43, 48.85), (2.0, 48.5)) is None
    assert "HTTP 404" not in caplog.text


def test_erreur_http_n_est_pas_reessayee_autour_du_point():
    session = FausseSession(FausseReponse(401, {"message": "Invalid key"}))
    assert ClientTransports("mauvais", session=session).duree_minutes((0, 0), (1, 1)) is None
    assert len(session.appels) == 1


def test_erreur_http_donne_un_trajet_inconnu():
    session = FausseSession(FausseReponse(401, {"message": "Invalid key"}))
    assert ClientTransports("mauvais", session=session).duree_minutes((0, 0), (1, 1)) is None


def test_erreur_reseau_donne_un_trajet_inconnu():
    session = FausseSession(requests.ConnectionError("hors ligne"))
    client = ClientVoiture(session=session, sleep=lambda _: None)
    assert client.duree_minutes((0, 0), (1, 1)) is None


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


def test_repartit_aussi_les_recruteurs(tmp_path):
    esn = Recruteur(
        siret="1", nom="ESN", adresse="45000 Orléans", departement="45", taille="20-49",
        secteur=None, naf="62.02A", site_web=None, telephone=None,
        url="https://exemple.test", longitude=1.90, latitude=47.90,
    )
    voiture = FauxClient({(1.90, 47.90): 24.0})
    proches, trop_loin = creer_trajets(tmp_path, voiture=voiture).repartir([esn])
    assert [r.trajet_min for r in proches] == [24]
    assert trop_loin == []
