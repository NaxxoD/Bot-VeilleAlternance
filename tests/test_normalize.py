import json
from pathlib import Path

from veille_alternance.normalize import (
    nettoyer_texte,
    normaliser_offre_ft,
    normaliser_reponse,
    normaliser_reponse_ft,
)
from veille_alternance.process import cle_contenu

FIXTURE = Path(__file__).parent / "fixtures" / "jobsearch_prod_75_rome_M18xx_I14xx.json"
FIXTURE_FT = Path(__file__).parent / "fixtures" / "ft_search_75_E2_informatique.json"


def charger_ft():
    return json.loads(FIXTURE_FT.read_text(encoding="utf-8"))


def test_premiere_offre_france_travail():
    offre = normaliser_offre_ft(charger_ft()["resultats"][0], "75")
    assert offre.cle == "France Travail|213JSYX"  # même clé que la version relayée par LBA
    assert offre.source == "France Travail"
    assert offre.titre == "Technicien support HelpDesk - Alternance - Paris 12e (H/F)"
    assert offre.entreprise == "EXPONENS"
    assert offre.adresse == "75012 Paris 12e Arrondissement"
    assert offre.departement == "75"
    assert offre.contrat == ("Apprentissage",)
    assert offre.romes == ("I1404",)
    assert offre.naf == "69.20Z"
    assert offre.url == "https://candidat.francetravail.fr/offres/recherche/detail/213JSYX"
    assert offre.publiee_le == "2026-09-03T16:31:40.837Z"
    assert offre.description.startswith("Exponens")


def test_offre_france_travail_meme_cle_de_contenu_que_lba():
    ft = normaliser_offre_ft(charger_ft()["resultats"][0], "75")
    lba = next(o for o in normaliser_reponse(charger(), "75")[0] if "HelpDesk" in o.titre)
    assert cle_contenu(ft) == cle_contenu(lba)


def test_offre_france_travail_champs_absents():
    brute = {"id": "X1", "intitule": "Technicien", "natureContrat": "Contrat apprentissage",
             "lieuTravail": {"libelle": "45 - ORLEANS"}}
    offre = normaliser_offre_ft(brute, "45")
    assert offre.entreprise is None
    assert offre.adresse == "ORLEANS"
    assert offre.romes == ()
    assert offre.naf is None
    assert offre.description == ""
    assert offre.url == "https://candidat.francetravail.fr/offres/recherche/detail/X1"


def test_offre_france_travail_relayee_par_un_agregateur():
    brute = {"id": "X2", "intitule": "Dev", "lieuTravail": {}, "origineOffre": {
        "origine": "2", "partenaires": [{"nom": "METEOJOB", "url": "https://exemple.test"}]}}
    assert normaliser_offre_ft(brute, "75").relayee_par == "METEOJOB"


def test_offre_france_travail_deposee_en_direct_non_relayee():
    brute = {"id": "X3", "intitule": "Dev", "lieuTravail": {}, "origineOffre": {"origine": "1"}}
    assert normaliser_offre_ft(brute, "75").relayee_par is None
    assert normaliser_offre_ft({"id": "X4", "intitule": "Dev"}, "75").relayee_par is None


def test_normaliser_reponse_ft():
    assert len(normaliser_reponse_ft(charger_ft(), "75")) == 19


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


def test_coordonnees_recruteur():
    _, recruteurs = normaliser_reponse(json.loads(FIXTURE.read_text(encoding="utf-8")), "75")
    assert (recruteurs[0].longitude, recruteurs[0].latitude) == (
        2.299246999999999, 48.877323999986366
    )
    assert recruteurs[0].trajet_min is None
