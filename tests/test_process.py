from dataclasses import replace

from veille_alternance.normalize import Offre, Recruteur
from veille_alternance.process import (
    cle_contenu,
    dedupliquer_offres,
    dedupliquer_par_contenu,
    dedupliquer_recruteurs,
    filtrer_contrat,
    filtrer_ecoles,
    classer_familles,
    filtrer_mots_cles,
    filtrer_recruteurs,
    sans_accents,
    trier_recruteurs,
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


def recruteur(siret, departement="75", naf=None, taille=None):
    return Recruteur(
        siret=siret, nom="ACME", adresse="75001 Paris", departement=departement,
        taille=taille, secteur=None, naf=naf, site_web=None, telephone=None,
        url="https://exemple.test",
    )


def test_filtrer_ecoles():
    employeur = offre(cle="X|1", entreprise="EXPONENS", naf="69.20Z")
    ecole_naf = offre(cle="X|2", entreprise="GROUPE IGF", naf="85.59A")
    ecole_nom = offre(cle="X|3", entreprise="ISCOD", naf=None)
    ecole_nom_casse = offre(cle="X|4", entreprise="Association IMC Alternance", naf=None)
    inconnu = offre(cle="X|5", entreprise=None, naf=None)
    resultat = filtrer_ecoles(
        [employeur, ecole_naf, ecole_nom, ecole_nom_casse, inconnu],
        ["85"], ["ISCOD", "IMC ALTERNANCE"],
    )
    assert resultat == [employeur, inconnu]


def test_filtrer_ecoles_nom_en_debut_de_mot():
    # "ISCOD" ne doit pas écarter une entreprise dont le nom le contient au milieu d'un mot
    voisin = offre(cle="X|1", entreprise="DISCODATA")
    assert filtrer_ecoles([voisin], [], ["ISCOD"]) == [voisin]


def test_filtrer_recruteurs_par_prefixe_naf():
    conseil = recruteur("1", naf="62.02A", taille="20-49")
    grossiste_info = recruteur("2", naf="46.51Z", taille="10-19")
    electromenager = recruteur("3", naf="47.54Z", taille="10-19")
    sans_naf = recruteur("4", naf=None, taille="10-19")
    resultat = filtrer_recruteurs(
        [conseil, grossiste_info, electromenager, sans_naf], ["62", "46.51"], []
    )
    assert resultat == [conseil, grossiste_info]


def test_filtrer_recruteurs_tailles_exclues():
    sans_salarie = recruteur("1", naf="62.02A", taille="0-0")
    pme = recruteur("2", naf="62.02A", taille="20-49")
    taille_inconnue = recruteur("3", naf="62.02A", taille=None)
    resultat = filtrer_recruteurs([sans_salarie, pme, taille_inconnue], ["62"], ["0-0"])
    assert resultat == [pme, taille_inconnue]


def test_filtrer_recruteurs_sans_prefixe_garde_tout():
    tous = [recruteur("1", naf="47.54Z"), recruteur("2", naf=None)]
    assert filtrer_recruteurs(tous, [], []) == tous


def test_sans_accents():
    assert sans_accents("Réseaux Sécurité") == "reseaux securite"


def test_dedupliquer_offres_garde_la_premiere():
    a = offre(cle="X|1", departement="75")
    b = offre(cle="X|1", departement="92")
    c = offre(cle="X|2")
    assert dedupliquer_offres([a, b, c]) == [a, c]


def test_cle_contenu_ignore_accents_genre_et_ponctuation():
    a = offre(titre="Alternant(e) Service Delivery Manager IT", adresse="93160 Noisy-le-Grand")
    b = offre(
        titre="Alternant Service Delivery Manager IT (H/F)",
        adresse="Esplanade de la Commune de Paris 93160 Noisy-le-Grand",
    )
    assert cle_contenu(a) == cle_contenu(b) == "alternant service delivery manager it|93160"


def test_cle_contenu_sans_code_postal_utilise_le_departement():
    assert cle_contenu(offre(titre="Technicien", adresse="Paris", departement="75")) == "technicien|75"


def test_dedupliquer_par_contenu():
    ratp_1 = offre(cle="Meteojob|1", titre="Alternant(e) Service Delivery Manager IT",
                   entreprise="RATP", adresse="93160 Noisy-le-Grand")
    ratp_2 = offre(cle="Talentplug|2", titre="Alternant Service Delivery Manager IT (H/F)",
                   entreprise="REGIE AUTONOME DES TRANSPORTS PARISIENS",
                   adresse="Esplanade de la Commune de Paris 93160 Noisy-le-Grand")
    ssi_1 = offre(cle="PASS|1", titre="EMA-SCA-DC SCA- TRAITANT HOMOLOGATION SSI",
                  adresse="78120 Rambouillet")
    ssi_2 = offre(cle="PASS|2", titre="EMA-SCA -TRAITANT HOMOLOGATION SSI",
                  adresse="78120 Rambouillet")
    meme_titre_autre_ville = offre(cle="X|9", titre="Alternant Service Delivery Manager IT",
                                   adresse="75012 Paris")
    resultat = dedupliquer_par_contenu([ratp_1, ratp_2, ssi_1, ssi_2, meme_titre_autre_ville])
    assert resultat == [ratp_1, ssi_1, ssi_2, meme_titre_autre_ville]


def test_dedupliquer_recruteurs():
    a, b, c = recruteur("111", "75"), recruteur("111", "92"), recruteur("222")
    assert dedupliquer_recruteurs([a, b, c]) == [a, c]


def test_filtrer_contrat():
    appr = offre(cle="X|1", contrat=("Apprentissage",))
    pro = offre(cle="X|2", contrat=("Professionnalisation",))
    les_deux = offre(cle="X|3", contrat=("Apprentissage", "Professionnalisation"))
    assert filtrer_contrat([appr, pro, les_deux], ["Apprentissage"]) == [appr, les_deux]


def test_filtrer_mots_cles_titre_ou_description():
    titre = offre(cle="X|1", titre="Administrateur Systèmes", description="")
    description = offre(cle="X|2", titre="Alternant IT", description="Serveurs LINUX")
    hors_sujet = offre(cle="X|3", titre="Assistant comptable", description="Saisie")
    resultat = filtrer_mots_cles(
        [titre, description, hors_sujet], ["administrateur systeme"], ["linux"], []
    )
    assert resultat == [titre, description]


def test_filtrer_mots_cles_titre_ignores_dans_description():
    # "reseau" est un mot-clé de titre : il ne doit pas suffire dans la description
    offre_bruit = offre(cle="X|1", titre="Chef de projet travaux", description="réseau CVC")
    assert filtrer_mots_cles([offre_bruit], ["reseau"], ["linux"], []) == []


def test_filtrer_mots_cles_debut_de_mot():
    # "ssi" doit trouver "SSI" mais pas "assistant"
    ssi = offre(cle="X|1", titre="Traitant homologation SSI")
    assistant = offre(cle="X|2", titre="Assistant de direction")
    pluriel = offre(cle="X|3", titre="Technicien réseaux")
    resultat = filtrer_mots_cles([ssi, assistant, pluriel], ["ssi", "technicien reseau"], [], [])
    assert resultat == [ssi, pluriel]


def test_classer_familles_dev_sur_le_titre_sinon_infra():
    dev = offre(cle="X|1", titre="Développeuse Full-Stack (H/F)")
    helpdesk = offre(cle="X|2", titre="Technicien helpdesk")
    description = offre(cle="X|3", titre="Alternant IT", description="Linux")
    business = offre(cle="X|4", titre="Business Developer")
    resultat = classer_familles([dev, helpdesk, description, business], ["developpeu", "full stack"])
    assert [o.famille for o in resultat] == ["dev", "infra", "infra", "infra"]


def test_filtrer_mots_cles_exclusion_sur_titre():
    marketing = offre(cle="X|1", titre="Chef de projet Marketing réseau")
    garde = offre(cle="X|2", titre="Technicien réseau", description="marketing digital")
    resultat = filtrer_mots_cles([marketing, garde], ["reseau"], [], ["marketing"])
    assert resultat == [garde]


def test_trier_recruteurs_coeur_puis_trajet():
    loin_coeur = replace(recruteur("1", naf="62.02A"), trajet_min=40)
    proche_coeur = replace(recruteur("2", naf="62.01Z"), trajet_min=10)
    inconnu_coeur = recruteur("3", naf="61.10Z")
    proche_autre = replace(recruteur("4", naf="46.51Z"), trajet_min=5)
    resultat = trier_recruteurs(
        [proche_autre, inconnu_coeur, loin_coeur, proche_coeur], ["62", "61"]
    )
    assert [r.siret for r in resultat] == ["2", "1", "3", "4"]
