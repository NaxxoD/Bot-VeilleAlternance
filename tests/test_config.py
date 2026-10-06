from pathlib import Path

import pytest

from veille_alternance.config import RACINE, ConfigError, charger_config, developper_plage

TOML = """
[api]
base_url = "https://exemple.test/api"
pause_entre_appels = 0.5
timeout = 10

[recherche]
departements = ["75", "45"]
rome_plages = [["M1801", "M1803"], ["I1404", "I1404"]]

[filtres]
types_contrat = ["Apprentissage"]
mots_cles_titre = ["technicien reseau"]
mots_cles_description = ["linux"]
mots_exclus_titre = ["marketing"]
"""


def test_developper_plage():
    assert developper_plage("M1801", "M1803") == ["M1801", "M1802", "M1803"]


def test_developper_plage_lettres_differentes():
    with pytest.raises(ConfigError):
        developper_plage("M1801", "I1403")


def test_developper_plage_inversee():
    with pytest.raises(ConfigError):
        developper_plage("M1810", "M1801")


def test_charger_config(tmp_path, monkeypatch):
    chemin = tmp_path / "search.toml"
    chemin.write_text(TOML, encoding="utf-8")
    monkeypatch.setenv("LBA_API_KEY", "cle-de-test")
    config = charger_config(chemin, tmp_path / "absent.env")
    assert config.api_key == "cle-de-test"
    assert config.base_url == "https://exemple.test/api"
    assert config.pause_entre_appels == 0.5
    assert config.timeout == 10
    assert config.departements == ["75", "45"]
    assert config.romes == ["M1801", "M1802", "M1803", "I1404"]
    assert config.types_contrat == ["Apprentissage"]
    assert config.mots_cles_titre == ["technicien reseau"]
    assert config.mots_cles_description == ["linux"]
    assert config.mots_exclus_titre == ["marketing"]


def test_dossier_raw_par_defaut(tmp_path, monkeypatch):
    chemin = tmp_path / "search.toml"
    chemin.write_text(TOML, encoding="utf-8")
    monkeypatch.setenv("LBA_API_KEY", "cle-de-test")
    config = charger_config(chemin, tmp_path / "absent.env")
    assert config.dossier_raw == RACINE / "data" / "raw"


def test_dossier_raw_absolu(tmp_path, monkeypatch):
    chemin = tmp_path / "search.toml"
    cible = (tmp_path / "hdd" / "raw").as_posix()
    chemin.write_text(TOML + f'\n[stockage]\ndossier_raw = "{cible}"\n', encoding="utf-8")
    monkeypatch.setenv("LBA_API_KEY", "cle-de-test")
    config = charger_config(chemin, tmp_path / "absent.env")
    assert config.dossier_raw == Path(cible)


def test_dossier_raw_relatif(tmp_path, monkeypatch):
    chemin = tmp_path / "search.toml"
    chemin.write_text(TOML + '\n[stockage]\ndossier_raw = "archives/raw"\n', encoding="utf-8")
    monkeypatch.setenv("LBA_API_KEY", "cle-de-test")
    config = charger_config(chemin, tmp_path / "absent.env")
    assert config.dossier_raw == RACINE / "archives" / "raw"


def test_filtres_recruteurs_par_defaut_vides(tmp_path, monkeypatch):
    chemin = tmp_path / "search.toml"
    chemin.write_text(TOML, encoding="utf-8")
    monkeypatch.setenv("LBA_API_KEY", "cle-de-test")
    config = charger_config(chemin, tmp_path / "absent.env")
    assert config.naf_prefixes == []
    assert config.tailles_exclues == []


def test_filtres_recruteurs(tmp_path, monkeypatch):
    chemin = tmp_path / "search.toml"
    chemin.write_text(
        TOML + '\n[filtres_recruteurs]\nnaf_prefixes = ["62", "46.51"]\n'
        'tailles_exclues = ["0-0"]\n',
        encoding="utf-8",
    )
    monkeypatch.setenv("LBA_API_KEY", "cle-de-test")
    config = charger_config(chemin, tmp_path / "absent.env")
    assert config.naf_prefixes == ["62", "46.51"]
    assert config.tailles_exclues == ["0-0"]


def test_france_travail_desactive_par_defaut(tmp_path, monkeypatch):
    chemin = tmp_path / "search.toml"
    chemin.write_text(TOML, encoding="utf-8")
    monkeypatch.setenv("LBA_API_KEY", "cle-de-test")
    config = charger_config(chemin, tmp_path / "absent.env")
    assert config.ft_actif is False
    assert config.ecoles_naf_prefixes == []
    assert config.organismes_exclus == []


def test_france_travail_active(tmp_path, monkeypatch):
    chemin = tmp_path / "search.toml"
    chemin.write_text(
        TOML + '\n[france_travail]\nactif = true\nnature_contrat = "E2"\n'
        '\n[filtres_ecoles]\nnaf_prefixes = ["85"]\norganismes_exclus = ["ISCOD"]\n',
        encoding="utf-8",
    )
    monkeypatch.setenv("LBA_API_KEY", "cle-de-test")
    monkeypatch.setenv("FT_CLIENT_ID", "PAR_test_id")
    monkeypatch.setenv("FT_CLIENT_SECRET", "secret-test")
    config = charger_config(chemin, tmp_path / "absent.env")
    assert config.ft_actif is True
    assert config.ft_nature_contrat == "E2"
    assert config.ft_client_id == "PAR_test_id"
    assert config.ft_client_secret == "secret-test"
    assert config.ecoles_naf_prefixes == ["85"]
    assert config.organismes_exclus == ["ISCOD"]


def test_france_travail_active_sans_identifiants(tmp_path, monkeypatch):
    chemin = tmp_path / "search.toml"
    chemin.write_text(TOML + "\n[france_travail]\nactif = true\n", encoding="utf-8")
    monkeypatch.setenv("LBA_API_KEY", "cle-de-test")
    monkeypatch.delenv("FT_CLIENT_ID", raising=False)
    monkeypatch.delenv("FT_CLIENT_SECRET", raising=False)
    with pytest.raises(ConfigError, match="FT_CLIENT_ID"):
        charger_config(chemin, tmp_path / "absent.env")


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


def test_charger_config_sans_cle(tmp_path, monkeypatch):
    chemin = tmp_path / "search.toml"
    chemin.write_text(TOML, encoding="utf-8")
    monkeypatch.delenv("LBA_API_KEY", raising=False)
    with pytest.raises(ConfigError, match="LBA_API_KEY"):
        charger_config(chemin, tmp_path / "absent.env")


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


def test_charger_config_historique(tmp_path, monkeypatch):
    monkeypatch.setenv("LBA_API_KEY", "cle-de-test")
    contenu = TOML + "\n[historique]\nlancements_avant_disparition = 3\njours_disparues = 7\n"
    config = charger_config(ecrire_toml(tmp_path, contenu), tmp_path / "absent.env")
    assert config.lancements_avant_disparition == 3
    assert config.jours_disparues == 7


def test_historique_par_defaut(tmp_path, monkeypatch):
    monkeypatch.setenv("LBA_API_KEY", "cle-de-test")
    config = charger_config(ecrire_toml(tmp_path, TOML), tmp_path / "absent.env")
    assert config.lancements_avant_disparition == 2
    assert config.jours_disparues == 14


def test_charger_config_recruteurs_et_zones(tmp_path, monkeypatch):
    monkeypatch.setenv("LBA_API_KEY", "cle-de-test")
    contenu = TOML + """
[filtres_recruteurs]
naf_coeur = ["62", "63.11"]

[[rapport.zones]]
nom = "Île-de-France"
departements = ["75", "92"]

[[rapport.zones]]
nom = "Loiret"
departements = ["45", "41"]
"""
    config = charger_config(ecrire_toml(tmp_path, contenu), tmp_path / "absent.env")
    assert config.naf_coeur == ["62", "63.11"]
    assert config.zones == [("Île-de-France", ["75", "92"]), ("Loiret", ["45", "41"])]


def test_zones_absentes_par_defaut(tmp_path, monkeypatch):
    monkeypatch.setenv("LBA_API_KEY", "cle-de-test")
    config = charger_config(ecrire_toml(tmp_path, TOML), tmp_path / "absent.env")
    assert config.naf_coeur == []
    assert config.zones == []
