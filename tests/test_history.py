from dataclasses import replace

from veille_alternance.history import (
    charger_historique,
    historique_vide,
    marquer_nouveautes,
    offres_disparues,
    sauvegarder_historique,
    trier_nouvelles_en_tete,
)
from veille_alternance.normalize import Offre


def offre(titre, cle="X|1"):
    return Offre(
        cle=cle, source="France Travail", titre=titre, entreprise=None,
        adresse="75012 Paris", departement="75", contrat=("Apprentissage",),
        teletravail=None, debut=None, niveau=None, romes=("I1404",), description="",
        url="https://exemple.test", publiee_le=None,
    )


def test_trier_par_vue_puis_publication():
    from dataclasses import replace
    A = replace(offre("A", "A|1"), premiere_vue="2026-09-26", publiee_le="2026-07-02T10:00:00Z")
    B = replace(offre("B", "B|2"), premiere_vue="2026-09-26", publiee_le="2026-09-20T10:00:00Z")
    C = replace(offre("C", "C|3"), premiere_vue="2026-10-04", publiee_le="2026-09-01T10:00:00Z")
    D = replace(offre("D", "D|4"), premiere_vue="2026-09-26", publiee_le=None)
    assert [o.titre for o in trier_nouvelles_en_tete([A, B, C, D], "2026-10-05")] == ["C", "B", "A", "D"]


def suivie(premiere_vue, derniere_vue):
    return {"premiere_vue": premiere_vue, "derniere_vue": derniere_vue}


def test_charger_historique_absent(tmp_path):
    assert charger_historique(tmp_path / "absent.json") == {"lancements": [], "offres": {}}


def test_sauvegarder_puis_charger(tmp_path):
    chemin = tmp_path / "data" / "historique.json"
    historique = {
        "lancements": ["2026-09-20"],
        "offres": {"technicien|75012": suivie("2026-09-20", "2026-09-20")},
    }
    sauvegarder_historique(historique, chemin)
    assert charger_historique(chemin) == historique


def test_charger_ancien_format(tmp_path):
    chemin = tmp_path / "historique.json"
    chemin.write_text('{"technicien|75012": "2026-09-26"}', encoding="utf-8")
    assert charger_historique(chemin) == {
        "lancements": [],
        "offres": {"technicien|75012": suivie("2026-09-26", "2026-09-26")},
    }


def test_marquer_nouveautes():
    historique = {
        "lancements": ["2026-09-20"],
        "offres": {"ancienne|75012": suivie("2026-09-20", "2026-09-20")},
    }
    ancienne, nouvelle = offre("Ancienne", "A|1"), offre("Nouvelle", "B|2")
    marquees, mis_a_jour = marquer_nouveautes([ancienne, nouvelle], historique, "2026-09-26")
    assert [o.premiere_vue for o in marquees] == ["2026-09-20", "2026-09-26"]
    assert mis_a_jour["lancements"] == ["2026-09-20", "2026-09-26"]
    assert mis_a_jour["offres"]["ancienne|75012"] == {
        "premiere_vue": "2026-09-20", "derniere_vue": "2026-09-26", "titre": "Ancienne",
        "entreprise": None, "departement": "75", "adresse": "75012 Paris",
        "url": "https://exemple.test",
    }
    assert mis_a_jour["offres"]["nouvelle|75012"]["premiere_vue"] == "2026-09-26"
    # l'original n'est pas modifié
    assert historique["offres"]["ancienne|75012"] == suivie("2026-09-20", "2026-09-20")


def test_relance_le_meme_jour_reste_nouvelle():
    historique = {
        "lancements": ["2026-09-26"],
        "offres": {"nouvelle|75012": suivie("2026-09-26", "2026-09-26")},
    }
    marquees, mis_a_jour = marquer_nouveautes([offre("Nouvelle")], historique, "2026-09-26")
    assert marquees[0].premiere_vue == "2026-09-26"
    assert mis_a_jour["lancements"] == ["2026-09-26"]  # pas de doublon


def test_trier_nouvelles_en_tete():
    historique = {"lancements": [], "offres": {
        "a|75012": suivie("2026-09-20", "2026-09-20"),
        "c|75012": suivie("2026-09-21", "2026-09-21"),
    }}
    marquees, _ = marquer_nouveautes(
        [offre("A", "A|1"), offre("B", "B|2"), offre("C", "C|3"), offre("D", "D|4")],
        historique, "2026-09-26",
    )
    assert [o.titre for o in trier_nouvelles_en_tete(marquees, "2026-09-26")] == ["B", "D", "C", "A"]


def test_anciennete_depuis_la_publication_sinon_la_premiere_vue():
    publiee = replace(offre("A", "A|1"), publiee_le="2026-09-03T16:31:40.837Z")
    marquees, _ = marquer_nouveautes([publiee, offre("B", "B|2")], historique_vide(), "2026-09-28")
    assert [o.anciennete_jours for o in marquees] == [25, 0]


def historique_avec(derniere_vue, lancements):
    infos = {
        **suivie("2026-09-20", derniere_vue), "titre": "Technicien", "entreprise": "EXPONENS",
        "departement": "75", "adresse": "75012 Paris", "url": "https://exemple.test",
    }
    return {"lancements": lancements, "offres": {"technicien|75012": infos}}


def test_disparue_apres_deux_lancements_sans_elle():
    historique = historique_avec("2026-09-26", ["2026-09-26", "2026-09-27", "2026-09-28"])
    disparues = offres_disparues(historique, "2026-09-28", 2, 14)
    assert [(d.titre, d.departement, d.premiere_vue, d.derniere_vue) for d in disparues] == [
        ("Technicien", "75", "2026-09-20", "2026-09-26")
    ]


def test_une_seule_absence_ne_suffit_pas():
    historique = historique_avec("2026-09-27", ["2026-09-26", "2026-09-27", "2026-09-28"])
    assert offres_disparues(historique, "2026-09-28", 2, 14) == []


def test_disparue_depuis_trop_longtemps_masquee():
    historique = historique_avec("2026-09-01", ["2026-09-01", "2026-09-27", "2026-09-28"])
    assert offres_disparues(historique, "2026-09-28", 2, 14) == []


def test_entree_migree_sans_description_ignoree():
    historique = {
        "lancements": ["2026-09-26", "2026-09-27", "2026-09-28"],
        "offres": {"x|75012": suivie("2026-09-20", "2026-09-20")},
    }
    assert offres_disparues(historique, "2026-09-28", 2, 14) == []
