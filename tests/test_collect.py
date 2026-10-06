import json

from veille_alternance.collect import collecter, collecter_ft, sources_saturees


class FauxClient:
    def __init__(self):
        self.appels = []

    def search(self, departement, romes):
        self.appels.append((departement, romes))
        return {"jobs": [], "recruiters": [], "warnings": [], "dep": departement}


class FauxClientFt:
    def __init__(self):
        self.appels = []

    def search(self, departement, nature_contrat):
        self.appels.append((departement, nature_contrat))
        return {"resultats": [{"id": f"{departement}-1"}]}


def test_collecter_ft(tmp_path):
    client = FauxClientFt()
    resultats = collecter_ft(client, ["75", "45"], "E2", tmp_path, "2026-09-26_163000")
    assert client.appels == [("75", "E2"), ("45", "E2")]
    assert [dep for dep, _ in resultats] == ["75", "45"]
    brut = json.loads((tmp_path / "2026-09-26_163000_ft_dep45.json").read_text(encoding="utf-8"))
    assert brut == {"resultats": [{"id": "45-1"}]}


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
