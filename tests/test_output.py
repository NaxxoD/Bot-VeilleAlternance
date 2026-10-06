import json
from dataclasses import replace

from veille_alternance.history import Disparue
from veille_alternance.normalize import Offre, Recruteur
from veille_alternance.output import COLONNES_OFFRES, ecrire_csv, ecrire_json
from veille_alternance.rapport import ecrire_html


def recruteur():
    return Recruteur(
        siret="111", nom="Société Générale", adresse="75009 Paris", departement="75",
        taille="100-199", secteur=None, naf=None, site_web=None, telephone=None,
        url="https://exemple.test",
    )


def test_ecrire_json(tmp_path):
    chemin = ecrire_json([recruteur()], tmp_path / "processed" / "recruteurs.json")
    contenu = chemin.read_text(encoding="utf-8")
    assert "Société Générale" in contenu
    assert json.loads(contenu) == [{
        "siret": "111", "nom": "Société Générale", "adresse": "75009 Paris",
        "departement": "75", "taille": "100-199", "secteur": None, "naf": None,
        "site_web": None, "telephone": None, "url": "https://exemple.test",
        "latitude": None, "longitude": None, "trajet_min": None,
    }]


def test_ecrire_csv_offres(tmp_path):
    offre = Offre(
        cle="France Travail|1", source="France Travail", titre="Technicien réseau; H/F",
        entreprise=None, adresse="75012 Paris", departement="75",
        contrat=("Apprentissage", "Professionnalisation"), teletravail=None, debut=None,
        niveau="5", romes=("I1404",), description="longue description",
        url="https://exemple.test", publiee_le="2026-09-03T16:31:40.837Z",
        premiere_vue="2026-09-26", famille="infra",
    )
    chemin = ecrire_csv([offre], tmp_path / "offres.csv", COLONNES_OFFRES)
    brut = chemin.read_bytes()
    assert brut.startswith(b"\xef\xbb\xbf")  # BOM UTF-8 : Excel reconnaît les accents
    lignes = brut.decode("utf-8-sig").splitlines()
    assert lignes == [
        "premiere_vue;departement;famille;titre;entreprise;adresse;trajet_min;anciennete_jours;"
        "contrat;niveau;source;relayee_par;publiee_le;url",
        '2026-09-26;75;infra;"Technicien réseau; H/F";;75012 Paris;;;Apprentissage, '
        "Professionnalisation;5;France Travail;;2026-09-03;https://exemple.test",
    ]


def offre_html(cle, titre, premiere_vue, url="https://exemple.test/offre"):
    return Offre(
        cle=cle, source="France Travail", titre=titre, entreprise="EXPONENS",
        adresse="75012 Paris", departement="75", contrat=("Apprentissage",),
        teletravail=None, debut=None, niveau=None, romes=("I1404",), description="",
        url=url, publiee_le="2026-09-03T16:31:40.837Z", premiere_vue=premiere_vue,
    )


def test_ecrire_html_separe_les_offres_actives_par_famille(tmp_path):
    dev = replace(offre_html("A|1", "Développeur web", "2026-09-20"), famille="dev")
    infra = replace(offre_html("A|2", "Technicien helpdesk", "2026-09-20"), famille="infra")
    page = ecrire_html([dev, infra], [], tmp_path / "r.html", "2026-09-26").read_text("utf-8")
    assert "Développement — 1" in page and "Infrastructure — 1" in page
    assert page.index("Développeur web") < page.index("Technicien helpdesk")
    assert '<span class="famille">dev</span>' in page


def test_ecrire_html_sans_famille_garde_une_seule_table(tmp_path):
    page = ecrire_html([offre_html("A|1", "Offre", "2026-09-20")], [], tmp_path / "r.html",
                       "2026-09-26").read_text("utf-8")
    assert "<h4>" not in page


def test_ecrire_html(tmp_path):
    nouvelle = offre_html("A|1", "Technicien support HelpDesk", "2026-09-26")
    ancienne = offre_html("B|2", "Administrateur systèmes", "2026-09-20")
    chemin = ecrire_html(
        [nouvelle, ancienne], [recruteur()], tmp_path / "rapport.html", "2026-09-26"
    )
    page = chemin.read_text(encoding="utf-8")
    assert page.startswith("<!DOCTYPE html>")
    assert "Technicien support HelpDesk" in page
    assert "Administrateur systèmes" in page
    assert "Société Générale" in page
    assert 'href="https://exemple.test/offre"' in page
    assert "1 nouvelle offre" in page
    assert "2 offres actives" in page
    assert "1 entreprise" in page


def test_ecrire_html_echappe_le_contenu(tmp_path):
    piege = offre_html("A|1", "<script>alert(1)</script>", "2026-09-26", url="javascript:alert(1)")
    page = ecrire_html([piege], [], tmp_path / "r.html", "2026-09-26").read_text(encoding="utf-8")
    assert "<script>alert(1)</script>" not in page
    assert "&lt;script&gt;" in page
    assert 'href="javascript:' not in page  # seuls les liens http(s) sont cliquables


def test_ecrire_html_affiche_le_trajet_et_les_offres_trop_loin(tmp_path):
    proche = replace(offre_html("A|1", "Technicien support", "2026-09-26"), trajet_min=38)
    inconnue = offre_html("B|2", "Administrateur systèmes", "2026-09-20")
    loin = replace(offre_html("C|3", "Technicien Cergy", "2026-09-26"), trajet_min=71)
    page = ecrire_html(
        [proche, inconnue], [], tmp_path / "r.html", "2026-09-26", trop_loin=[loin]
    ).read_text(encoding="utf-8")
    assert "38 min" in page
    assert "<td>?</td>" in page  # trajet inconnu
    assert "Trop loin — 1 offre écartée" in page
    assert page.index("Technicien Cergy") > page.index("<details>")
    assert "71 min" in page
    assert "2 offres actives" in page


def test_ecrire_html_sans_offre_trop_loin(tmp_path):
    page = ecrire_html(
        [offre_html("A|1", "Technicien", "2026-09-26")], [], tmp_path / "r.html", "2026-09-26"
    ).read_text(encoding="utf-8")
    assert "<details>" not in page


def test_ecrire_html_affiche_l_anciennete(tmp_path):
    ancienne = replace(offre_html("A|1", "Technicien", "2026-09-20"), anciennete_jours=25)
    page = ecrire_html([ancienne], [], tmp_path / "r.html", "2026-09-28").read_text(
        encoding="utf-8"
    )
    assert '<td title="publiée le 03/09/2026">25 j</td>' in page
    assert "<th>En ligne</th>" in page


def test_ecrire_html_liste_les_offres_disparues(tmp_path):
    disparue = Disparue(
        titre="Technicien Versailles", entreprise="EF2C", departement="78",
        adresse="78000 Versailles", url="https://exemple.test/v",
        premiere_vue="2026-09-26", derniere_vue="2026-10-02",
    )
    page = ecrire_html(
        [], [], tmp_path / "r.html", "2026-10-05", disparues=[disparue]
    ).read_text(encoding="utf-8")
    assert "Disparues récemment — 1 offre" in page
    assert "du 26/09/2026 au 02/10/2026" in page
    assert 'href="https://exemple.test/v"' in page
    assert '<option value="78">' in page


def test_ecrire_html_un_bloc_par_zone(tmp_path):
    paris = offre_html("A|1", "Technicien Paris", "2026-09-26")
    orleans = replace(offre_html("B|2", "Technicien Orléans", "2026-09-26"), departement="45")
    zones = [("Île-de-France", ["75"]), ("Loiret", ["45", "41"])]
    page = ecrire_html(
        [paris, orleans], [recruteur()], tmp_path / "r.html", "2026-09-26", zones=zones
    ).read_text(encoding="utf-8")
    debut_idf = page.index('<h2 class="zone">Île-de-France</h2>')
    debut_loiret = page.index('<h2 class="zone">Loiret</h2>')
    assert debut_idf < page.index("Technicien Paris") < debut_loiret
    assert debut_loiret < page.index("Technicien Orléans")
    assert page.index("Société Générale") < debut_loiret  # recruteur du 75
    assert "Autres départements" not in page


def test_ecrire_html_bloc_autres_departements(tmp_path):
    lyon = replace(offre_html("A|1", "Technicien Lyon", "2026-09-26"), departement="69")
    page = ecrire_html(
        [lyon], [], tmp_path / "r.html", "2026-09-26", zones=[("Loiret", ["45"])]
    ).read_text(encoding="utf-8")
    assert '<h2 class="zone">Loiret</h2>' in page
    assert '<h2 class="zone">Autres départements</h2>' in page


def test_ecrire_html_recruteur_trajet_et_lien_lba(tmp_path):
    proche = replace(recruteur(), trajet_min=22)
    page = ecrire_html([], [proche], tmp_path / "r.html", "2026-09-26").read_text(
        encoding="utf-8"
    )
    assert "<td>22 min</td>" in page
    assert ">postuler via LBA</a>" in page


def test_ecrire_html_candidatures_spontanees_repliees(tmp_path):
    page = ecrire_html([], [recruteur()], tmp_path / "r.html", "2026-09-26").read_text(
        encoding="utf-8"
    )
    assert "<details><summary>Candidatures spontanées — 1 entreprise</summary>" in page
    assert page.index("<details><summary>Candidatures") < page.index("Société Générale")


def test_rapport_employeur_inconnu_et_relais(tmp_path):
    offre = Offre(
        cle="France Travail|9", source="France Travail", titre="Développeur", entreprise=None,
        adresse="75009 Paris", departement="75", contrat=("Apprentissage",), teletravail=None,
        debut=None, niveau=None, romes=(), description="", url="https://exemple.test",
        publiee_le=None, premiere_vue="2026-09-26", relayee_par="METEOJOB",
    )
    chemin = ecrire_html([offre], [], tmp_path / "r.html", "2026-09-26")
    contenu = chemin.read_text(encoding="utf-8")
    assert "Employeur inconnu" in contenu
    assert "via Meteojob" in contenu
