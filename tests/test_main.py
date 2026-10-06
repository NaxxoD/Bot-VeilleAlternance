import json
from dataclasses import replace
from pathlib import Path

from veille_alternance.__main__ import executer
from veille_alternance.config import Config

FIXTURE = Path(__file__).parent / "fixtures" / "jobsearch_prod_75_rome_M18xx_I14xx.json"


class FauxClient:
    def search(self, departement, romes):
        return json.loads(FIXTURE.read_text(encoding="utf-8"))


def config_test(dossier_raw):
    return Config(
        api_key="cle-test", base_url="https://exemple.test/api", pause_entre_appels=0.0,
        timeout=5.0, departements=["75", "92"], romes=["M1801"],
        types_contrat=["Apprentissage"], mots_cles_titre=["informatique", "technicien"],
        mots_cles_description=["linux"], mots_exclus_titre=["marketing"],
        dossier_raw=dossier_raw,
    )


def test_executer(tmp_path):
    # Réponses brutes ailleurs que les sorties (cas réel : HDD D: vs SSD)
    chemin_offres, chemin_recruteurs = executer(
        config_test(tmp_path / "hdd" / "raw"), FauxClient(), tmp_path / "processed",
        "2026-09-26_080000", "2026-09-26",
        chemin_historique=tmp_path / "historique.json", sleep=lambda _: None,
    )
    assert chemin_offres == tmp_path / "processed" / "offres_2026-09-26.json"
    assert chemin_recruteurs == tmp_path / "processed" / "recruteurs_2026-09-26.json"
    assert (tmp_path / "hdd" / "raw" / "2026-09-26_080000_dep75.json").exists()
    assert (tmp_path / "hdd" / "raw" / "2026-09-26_080000_dep92.json").exists()
    assert (tmp_path / "processed" / "offres_2026-09-26.csv").exists()
    assert (tmp_path / "processed" / "recruteurs_2026-09-26.csv").exists()
    assert (tmp_path / "processed" / "rapport_2026-09-26.html").exists()
    assert (tmp_path / "processed" / "rapport.html").read_text(encoding="utf-8") == (
        tmp_path / "processed" / "rapport_2026-09-26.html"
    ).read_text(encoding="utf-8")

    offres = json.loads(chemin_offres.read_text(encoding="utf-8"))
    cles = [o["cle"] for o in offres]
    assert len(cles) == len(set(cles))
    assert len(offres) <= 30
    assert all("Apprentissage" in o["contrat"] for o in offres)
    assert all("marketing" not in o["titre"].lower() for o in offres)
    assert all(o["departement"] == "75" for o in offres)

    recruteurs = json.loads(chemin_recruteurs.read_text(encoding="utf-8"))
    assert len(recruteurs) == 150


def test_executer_filtre_les_recruteurs(tmp_path):
    config = config_test(tmp_path / "raw")
    config = Config(**{**config.__dict__, "departements": ["75"],
                       "naf_prefixes": ["62"], "tailles_exclues": ["0-0"]})
    _, chemin_recruteurs = executer(
        config, FauxClient(), tmp_path / "processed", "h", "2026-09-26",
        chemin_historique=tmp_path / "historique.json", sleep=lambda _: None,
    )
    recruteurs = json.loads(chemin_recruteurs.read_text(encoding="utf-8"))
    assert 0 < len(recruteurs) < 150
    assert all(r["naf"].startswith("62") for r in recruteurs)
    assert all(r["taille"] != "0-0" for r in recruteurs)


FIXTURE_FT = Path(__file__).parent / "fixtures" / "ft_search_75_E2_informatique.json"


class FauxClientFt:
    def __init__(self):
        self.appels = []

    def search(self, departement, nature_contrat):
        self.appels.append((departement, nature_contrat))
        return json.loads(FIXTURE_FT.read_text(encoding="utf-8"))


def config_deux_sources(dossier_raw, ft_actif=True):
    return Config(**{
        **config_test(dossier_raw).__dict__, "departements": ["75"],
        "mots_cles_titre": ["informatique", "helpdesk", "technicien", "administrateur reseau"],
        "ft_actif": ft_actif, "ft_nature_contrat": "E2",
        "ecoles_naf_prefixes": ["85"], "organismes_exclus": ["ISCOD"],
    })


def test_executer_fusionne_france_travail_et_lba(tmp_path):
    client_ft = FauxClientFt()
    chemin_offres, _ = executer(
        config_deux_sources(tmp_path / "raw"), FauxClient(), tmp_path / "processed", "h", "2026-09-26",
        chemin_historique=tmp_path / "historique.json", client_ft=client_ft,
        sleep=lambda _: None,
    )
    assert client_ft.appels == [("75", "E2")]
    assert (tmp_path / "raw" / "h_ft_dep75.json").exists()
    offres = json.loads(chemin_offres.read_text(encoding="utf-8"))
    helpdesk = [o for o in offres if "HelpDesk" in o["titre"]]
    assert len(helpdesk) == 1  # présente dans les deux sources, gardée une seule fois
    assert helpdesk[0]["entreprise"] == "EXPONENS"  # version France Travail, plus complète
    assert not any(o["entreprise"] in ("GROUPE IGF", "ISCOD") for o in offres)  # écoles
    assert any(o["source"] == "France Travail" for o in offres)


def test_executer_ecrit_le_vivier_avant_le_filtre_mots_cles(tmp_path):
    executer(
        config_deux_sources(tmp_path / "raw"), FauxClient(), tmp_path / "processed", "h",
        "2026-09-26", chemin_historique=tmp_path / "historique.json", client_ft=FauxClientFt(),
        sleep=lambda _: None,
    )
    vivier = json.loads(
        (tmp_path / "processed" / "pool_offres_2026-09-26.json").read_text(encoding="utf-8")
    )
    retenues = json.loads(
        (tmp_path / "processed" / "offres_2026-09-26.json").read_text(encoding="utf-8")
    )
    cles_vivier = {o["cle"] for o in vivier}
    assert len(vivier) > len(retenues)
    assert {o["cle"] for o in retenues} <= cles_vivier  # les retenues font partie du vivier
    assert all("Apprentissage" in o["contrat"] for o in vivier)
    assert not any(o["entreprise"] in ("GROUPE IGF", "ISCOD") for o in vivier)
    assert len(cles_vivier) == len(vivier)


def test_executer_ecrit_le_resume_pour_la_pop_up(tmp_path):
    config = config_test(tmp_path / "raw")
    config = Config(**{**config.__dict__, "departements": ["75"], "mots_cles_titre": ["helpdesk"]})
    historique = tmp_path / "historique.json"
    sortie = tmp_path / "processed"
    executer(config, ClientDoublonContrat(), sortie, "h1", "2026-09-26",
             chemin_historique=historique, sleep=lambda _: None)
    resume = json.loads((sortie / "resume.json").read_text(encoding="utf-8"))
    assert resume["jour"] == "2026-09-26"
    assert resume["nb_offres"] == 1
    assert resume["nb_nouvelles"] == 1
    assert resume["nb_recruteurs"] == 0
    assert resume["nouvelles"] == [{
        "titre": "Technicien support HelpDesk", "entreprise": "EXPONENS", "departement": "75",
    }]
    assert resume["rapport"] == str(sortie / "rapport.html")

    executer(config, ClientDoublonContrat(), sortie, "h2", "2026-09-27",
             chemin_historique=historique, sleep=lambda _: None)
    resume = json.loads((sortie / "resume.json").read_text(encoding="utf-8"))
    assert resume["nb_nouvelles"] == 0 and resume["nouvelles"] == []


def test_executer_france_travail_desactive(tmp_path):
    client_ft = FauxClientFt()
    executer(
        config_deux_sources(tmp_path / "raw", ft_actif=False), FauxClient(),
        tmp_path / "processed", "h", "2026-09-26", chemin_historique=tmp_path / "historique.json",
        client_ft=client_ft, sleep=lambda _: None,
    )
    assert client_ft.appels == []


def job(identifiant, contrat):
    return {
        "identifier": {"id": None, "partner_label": "France Travail", "partner_job_id": identifiant},
        "workplace": {"name": "EXPONENS", "location": {"address": "75012 Paris"}},
        "apply": {"url": "https://exemple.test"},
        "contract": {"type": [contrat], "remote": None, "start": None},
        "offer": {
            "title": "Technicien support HelpDesk", "description": "", "rome_codes": ["I1404"],
            "target_diploma": None, "publication": {"creation": None},
        },
    }


class ClientDoublonContrat:
    """Même annonce publiée en professionnalisation puis en apprentissage."""

    def search(self, departement, romes):
        return {
            "jobs": [job("PRO", "Professionnalisation"), job("APPR", "Apprentissage")],
            "recruiters": [], "warnings": [],
        }


def test_executer_doublon_de_contrat_garde_la_version_apprentissage(tmp_path):
    config = config_test(tmp_path / "raw")
    config = Config(**{**config.__dict__, "departements": ["75"], "mots_cles_titre": ["helpdesk"]})
    chemin_offres, _ = executer(
        config, ClientDoublonContrat(), tmp_path / "processed", "h", "2026-09-26",
        chemin_historique=tmp_path / "historique.json", sleep=lambda _: None,
    )
    offres = json.loads(chemin_offres.read_text(encoding="utf-8"))
    assert [o["cle"] for o in offres] == ["France Travail|APPR"]


def test_executer_detecte_les_nouvelles_offres_d_un_jour_a_l_autre(tmp_path):
    config = config_test(tmp_path / "raw")
    config = Config(**{**config.__dict__, "departements": ["75"], "mots_cles_titre": ["helpdesk"]})
    historique = tmp_path / "historique.json"
    sortie = tmp_path / "processed"

    executer(config, ClientDoublonContrat(), sortie, "h1", "2026-09-26",
             chemin_historique=historique, sleep=lambda _: None)
    lignes_jour_1 = (sortie / "nouvelles_offres_2026-09-26.csv").read_text(encoding="utf-8-sig")
    assert len(lignes_jour_1.splitlines()) == 2  # en-tête + 1 nouvelle offre

    chemin_offres, _ = executer(config, ClientDoublonContrat(), sortie, "h2", "2026-09-27",
                                chemin_historique=historique, sleep=lambda _: None)
    lignes_jour_2 = (sortie / "nouvelles_offres_2026-09-27.csv").read_text(encoding="utf-8-sig")
    assert len(lignes_jour_2.splitlines()) == 1  # en-tête seul : rien de nouveau
    offres = json.loads(chemin_offres.read_text(encoding="utf-8"))
    assert [o["premiere_vue"] for o in offres] == ["2026-09-26"]
    suivi = json.loads(historique.read_text(encoding="utf-8"))
    assert suivi["lancements"] == ["2026-09-26", "2026-09-27"]
    infos = suivi["offres"]["technicien support helpdesk|75012"]
    assert (infos["premiere_vue"], infos["derniere_vue"]) == ("2026-09-26", "2026-09-27")


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
    suivi = json.loads(historique.read_text(encoding="utf-8"))
    # Vue (donc jamais « disparue »), mais pas notifiée
    assert "technicien support helpdesk|75012" in suivi["offres"]
    page = (sortie / "rapport.html").read_text(encoding="utf-8")
    assert "Trop loin — 1 offre écartée" in page
    assert "90 min" in page


class ClientVide:
    def search(self, departement, romes):
        return {"jobs": [], "recruiters": [], "warnings": []}


def test_executer_signale_les_offres_disparues(tmp_path):
    config = config_test(tmp_path / "raw")
    config = Config(**{**config.__dict__, "departements": ["75"], "mots_cles_titre": ["helpdesk"]})
    historique = tmp_path / "historique.json"
    sortie = tmp_path / "processed"
    lancements = [(ClientDoublonContrat(), "h1", "2026-09-26"), (ClientVide(), "h2", "2026-09-27")]
    for client, horodatage, jour in lancements:
        executer(config, client, sortie, horodatage, jour,
                 chemin_historique=historique, sleep=lambda _: None)
    page = (sortie / "rapport.html").read_text(encoding="utf-8")
    assert "Disparues récemment" not in page  # une seule absence

    executer(config, ClientVide(), sortie, "h3", "2026-09-28",
             chemin_historique=historique, sleep=lambda _: None)
    page = (sortie / "rapport.html").read_text(encoding="utf-8")
    assert "Disparues récemment — 1 offre" in page
    assert "du 26/09/2026 au 26/09/2026" in page


class TrajetsFixes:
    """Services informatiques (NAF 62.02) à 10 min, tout le reste à 30 min."""

    def repartir(self, elements):
        return [
            replace(e, trajet_min=10 if (e.naf or "").startswith("62.02") else 30)
            for e in elements
        ], []


def test_executer_classe_les_recruteurs(tmp_path):
    config = config_test(tmp_path / "raw")
    config = Config(**{**config.__dict__, "departements": ["75"], "naf_coeur": ["62"]})
    _, chemin_recruteurs = executer(
        config, FauxClient(), tmp_path / "processed", "h", "2026-09-26",
        chemin_historique=tmp_path / "historique.json", trajets=TrajetsFixes(),
        sleep=lambda _: None,
    )
    recruteurs = json.loads(chemin_recruteurs.read_text(encoding="utf-8"))
    coeur = [(r["naf"] or "").startswith("62") for r in recruteurs]
    assert True in coeur and False in coeur
    assert coeur == sorted(coeur, reverse=True)  # cœur numérique d'abord
    trajets_coeur = [r["trajet_min"] for r in recruteurs if (r["naf"] or "").startswith("62")]
    assert trajets_coeur == sorted(trajets_coeur)  # puis du plus proche au plus loin
