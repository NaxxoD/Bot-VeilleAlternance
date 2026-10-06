import pytest

from veille_alternance.client import ApiError
from veille_alternance.ft_client import SEARCH_URL, TOKEN_URL, FtClient


class FausseReponse:
    def __init__(self, status_code, payload=None, headers=None, text=""):
        self.status_code = status_code
        self._payload = payload
        self.headers = headers or {}
        self.text = text

    def json(self):
        return self._payload


def jeton(valeur="jeton-1", duree=1499):
    return FausseReponse(200, {"access_token": valeur, "expires_in": duree, "token_type": "Bearer"})


def page(ids, debut, total):
    fin = debut + len(ids) - 1
    return FausseReponse(
        206 if fin + 1 < total else 200,
        {"resultats": [{"id": i} for i in ids]},
        {"Content-Range": f"offres {debut}-{fin}/{total}"},
    )


class FausseSession:
    def __init__(self, posts, gets):
        self.posts, self.gets = list(posts), list(gets)
        self.appels_post, self.appels_get = [], []

    def post(self, url, params=None, data=None, timeout=None):
        self.appels_post.append((url, params, data))
        return self.posts.pop(0)

    def get(self, url, params=None, headers=None, timeout=None):
        self.appels_get.append((url, params, headers))
        return self.gets.pop(0)


class Horloge:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t


def creer(posts, gets, horloge=None):
    session = FausseSession(posts, gets)
    client = FtClient(
        "PAR_id", "secret", session=session, sleep=lambda _: None,
        horloge=horloge or Horloge(),
    )
    return client, session


def test_search_une_page():
    client, session = creer([jeton()], [page(["A", "B"], 0, 2)])
    assert client.search("75", "E2") == {"resultats": [{"id": "A"}, {"id": "B"}]}
    url, params, data = session.appels_post[0]
    assert url == TOKEN_URL
    assert params == {"realm": "/partenaire"}
    assert data == {
        "grant_type": "client_credentials", "client_id": "PAR_id",
        "client_secret": "secret", "scope": "api_offresdemploiv2 o2dsoffre",
    }
    assert session.appels_get == [(
        SEARCH_URL,
        {"departement": "75", "natureContrat": "E2", "range": "0-149"},
        {"Authorization": "Bearer jeton-1", "Accept": "application/json"},
    )]


def test_search_pagine_jusqu_au_total():
    ids_1, ids_2 = [f"A{i}" for i in range(150)], ["B0", "B1"]
    client, session = creer([jeton()], [page(ids_1, 0, 152), page(ids_2, 150, 152)])
    resultat = client.search("75", "E2")
    assert len(resultat["resultats"]) == 152
    assert [p["range"] for _, p, _ in session.appels_get] == ["0-149", "150-299"]
    assert len(session.appels_post) == 1  # un seul jeton pour les deux pages


def test_search_aucun_resultat_204():
    client, _ = creer([jeton()], [FausseReponse(204)])
    assert client.search("45", "E2") == {"resultats": []}


def test_jeton_reutilise_puis_renouvele_a_expiration():
    horloge = Horloge()
    client, session = creer(
        [jeton("jeton-1", 1499), jeton("jeton-2", 1499)],
        [page(["A"], 0, 1), page(["B"], 0, 1), page(["C"], 0, 1)],
        horloge,
    )
    client.search("75", "E2")
    horloge.t = 1000  # jeton encore valide
    client.search("92", "E2")
    horloge.t = 1500  # jeton expiré
    client.search("93", "E2")
    assert [h["Authorization"] for _, _, h in session.appels_get] == [
        "Bearer jeton-1", "Bearer jeton-1", "Bearer jeton-2",
    ]


def test_quota_depasse_puis_succes():
    attentes = []
    session = FausseSession(
        [jeton()], [FausseReponse(429, headers={"Retry-After": "2"}), page(["A"], 0, 1)]
    )
    client = FtClient("PAR_id", "secret", session=session, sleep=attentes.append,
                      horloge=Horloge())
    assert client.search("75", "E2") == {"resultats": [{"id": "A"}]}
    assert 2.0 in attentes


def test_authentification_refusee():
    refus = FausseReponse(400, {"error": "invalid_client"}, text='{"error": "invalid_client"}')
    client, _ = creer([refus], [])
    with pytest.raises(ApiError, match="invalid_client"):
        client.search("75", "E2")


def test_erreur_serveur_recherche():
    client, _ = creer([jeton()], [FausseReponse(500, text="panne")])
    with pytest.raises(ApiError, match="HTTP 500"):
        client.search("75", "E2")
