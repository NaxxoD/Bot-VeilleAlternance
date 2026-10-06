import json

from veille_alternance.bilan import calculer_bilan, formater


def offre(titre, jour, **champs):
    base = {"titre": titre, "departement": "75", "entreprise": "ACME", "source": "France Travail",
            "premiere_vue": jour, "trajet_min": 20}
    return {**base, **champs}


def ecrire_jour(dossier, jour, vivier, retenues):
    (dossier / f"pool_offres_{jour}.json").write_text(json.dumps(vivier), encoding="utf-8")
    (dossier / f"offres_{jour}.json").write_text(json.dumps(retenues), encoding="utf-8")


def test_bilan_flux_nouveautes_et_duree(tmp_path):
    helpdesk, dev = offre("Technicien helpdesk", "2026-10-01"), offre("Développeur web", "2026-10-02")
    bruit = offre("Boulanger", "2026-10-01")
    ecrire_jour(tmp_path, "2026-10-01", [helpdesk, bruit], [helpdesk])
    ecrire_jour(tmp_path, "2026-10-02", [helpdesk, dev], [helpdesk, dev])
    bilan = calculer_bilan(tmp_path, ["developpeu"])
    premier, second = bilan["jours"]
    assert (premier["vivier"], premier["retenues"], premier["entrees_vivier"]) == (2, 1, None)
    assert (second["entrees_vivier"], second["sorties_vivier"], second["retenues_entrees"]) == (1, 1, 1)
    assert second["nouvelles"] == 1
    assert second["familles"] == {"infra": 1, "dev": 1}
    assert bilan["distinctes"] == 2 and bilan["un_seul_jour"] == 1
    assert bilan["duree_moyenne"] == 1.5


def test_bilan_garde_la_famille_enregistree(tmp_path):
    dev = offre("Alternant IT", "2026-10-01", famille="dev")
    ecrire_jour(tmp_path, "2026-10-01", [dev], [dev])
    assert calculer_bilan(tmp_path, [])["jours"][0]["familles"]["dev"] == 1


def test_bilan_sans_sortie_quotidienne(tmp_path):
    assert formater(calculer_bilan(tmp_path, [])) == "Aucune sortie quotidienne à analyser."


def test_formater_le_bilan(tmp_path):
    helpdesk = offre("Technicien helpdesk", "2026-10-01")
    ecrire_jour(tmp_path, "2026-10-01", [helpdesk], [helpdesk])
    ecrire_jour(tmp_path, "2026-10-02", [helpdesk], [helpdesk])
    texte = formater(calculer_bilan(tmp_path, []))
    assert "2026-10-01 → 2026-10-02 (2 jours)" in texte
    assert "France Travail 1" in texte
