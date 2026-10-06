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
