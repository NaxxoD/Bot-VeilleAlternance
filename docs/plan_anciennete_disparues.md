# Plan — ancienneté des offres et offres disparues

**Objectif** : afficher depuis combien de jours chaque offre est en ligne et
lister dans le rapport les offres disparues (absentes de 2 lancements) des 14
derniers jours.

Spec : `docs/specs/2026-09-28-anciennete-disparues-design.md`.

## Fichiers touchés

| Fichier | Changement |
|---|---|
| `src/veille_alternance/config.py` | `lancements_avant_disparition`, `jours_disparues`, section `[historique]` |
| `src/veille_alternance/normalize.py` | `Offre.anciennete_jours` |
| `src/veille_alternance/history.py` | nouveau format + migration, `anciennete_jours`, `offres_disparues`, `Disparue` |
| `src/veille_alternance/output.py` | colonne `anciennete_jours` |
| `src/veille_alternance/rapport.py` | colonne « En ligne », section « Disparues récemment », `_section_repliee` |
| `src/veille_alternance/__main__.py` | historique mis à jour aussi par les offres trop loin, disparues au rapport |
| `config/search.toml` | section `[historique]` |
| `tests/test_config.py`, `test_history.py`, `test_output.py`, `test_main.py` | tests |
| `README.md` | état actuel |

---

### Tâche 1 — Configuration `[historique]`

Fichiers : `src/veille_alternance/config.py`, `tests/test_config.py`

1. Tests — ajouter à la fin de `tests/test_config.py` :

```python
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
```

2. Échec attendu : `AttributeError: 'Config' object has no attribute 'lancements_avant_disparition'`.

3. Code — dans `Config`, après `trajet_max_voiture` :

```python
    lancements_avant_disparition: int = 2
    jours_disparues: int = 14
```

dans `charger_config`, avant `return Config(` :

```python
    # Section [historique] facultative : offres disparues (absentes de N lancements)
    suivi = donnees.get("historique", {})
```

et dans l'appel `Config(...)`, après `trajet_max_voiture=...` :

```python
        lancements_avant_disparition=int(suivi.get("lancements_avant_disparition", 2)),
        jours_disparues=int(suivi.get("jours_disparues", 14)),
```

4. `python -m pytest tests/test_config.py -q` → vert.
5. Commit : `Configuration du suivi des offres disparues`

---

### Tâche 2 — Historique : nouveau format, ancienneté, disparues

Fichiers : `src/veille_alternance/normalize.py`, `src/veille_alternance/history.py`,
`tests/test_history.py`

1. Tests — remplacer tout `tests/test_history.py` par :

```python
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
    assert [o.titre for o in trier_nouvelles_en_tete(marquees, "2026-09-26")] == ["B", "D", "A", "C"]


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
```

2. Échec attendu : `ImportError: cannot import name 'historique_vide'`.

3. Code — `normalize.py`, dans `Offre` après `trajet_min` :

```python
    anciennete_jours: int | None = None  # jours en ligne, renseigné par history
```

remplacer tout `history.py` par :

```python
"""Historique des offres vues, d'un lancement à l'autre.

Format du fichier JSON :
    {"lancements": ["2026-09-26", ...],   dates des lancements, sans doublon
     "offres": {clé de contenu: {"premiere_vue", "derniere_vue", "titre",
                                 "entreprise", "departement", "adresse", "url"}}}
Une offre est nouvelle si sa première vue est aujourd'hui ; elle est disparue si
plusieurs lancements ont eu lieu depuis sa dernière vue.
"""

import json
from dataclasses import dataclass, replace
from datetime import date, timedelta
from pathlib import Path

from veille_alternance.normalize import Offre
from veille_alternance.process import cle_contenu


@dataclass(frozen=True)
class Disparue:
    titre: str
    entreprise: str | None
    departement: str
    adresse: str
    url: str
    premiere_vue: str
    derniere_vue: str


def historique_vide() -> dict:
    return {"lancements": [], "offres": {}}


def charger_historique(chemin: Path) -> dict:
    if not chemin.exists():
        return historique_vide()
    donnees = json.loads(chemin.read_text(encoding="utf-8"))
    if "offres" in donnees:
        return donnees
    # Ancien format (jusqu'au 2026-09-28) : clé → date de première vue, sans description
    return {
        "lancements": [],
        "offres": {cle: {"premiere_vue": vue, "derniere_vue": vue} for cle, vue in donnees.items()},
    }


def sauvegarder_historique(historique: dict, chemin: Path) -> Path:
    chemin.parent.mkdir(parents=True, exist_ok=True)
    chemin.write_text(
        json.dumps(historique, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8"
    )
    return chemin


def anciennete_jours(offre: Offre, jour: str) -> int | None:
    """Jours depuis la publication (date de la source), sinon depuis la première vue."""
    debut = (offre.publiee_le or offre.premiere_vue or "")[:10]
    if not debut:
        return None
    return max(0, (date.fromisoformat(jour) - date.fromisoformat(debut)).days)


def marquer_nouveautes(
    offres: list[Offre], historique: dict, jour: str
) -> tuple[list[Offre], dict]:
    """Renseigne premiere_vue et anciennete_jours sur chaque offre, et renvoie
    l'historique complété (lancement du jour, dernière vue, description)."""
    lancements = set(historique["lancements"]) | {jour}
    suivies = {cle: dict(infos) for cle, infos in historique["offres"].items()}
    marquees = []
    for offre in offres:
        infos = suivies.setdefault(cle_contenu(offre), {"premiere_vue": jour})
        infos.update(
            derniere_vue=jour, titre=offre.titre, entreprise=offre.entreprise,
            departement=offre.departement, adresse=offre.adresse, url=offre.url,
        )
        offre = replace(offre, premiere_vue=infos["premiere_vue"])
        marquees.append(replace(offre, anciennete_jours=anciennete_jours(offre, jour)))
    return marquees, {"lancements": sorted(lancements), "offres": suivies}


def trier_nouvelles_en_tete(offres: list[Offre], jour: str) -> list[Offre]:
    # sorted est stable : l'ordre d'origine est conservé dans chaque groupe
    return sorted(offres, key=lambda offre: offre.premiere_vue != jour)


def offres_disparues(
    historique: dict, jour: str, lancements_avant_disparition: int, jours_disparues: int
) -> list[Disparue]:
    """Offres absentes d'au moins N lancements depuis leur dernière vue, vues pour la
    dernière fois il y a moins de `jours_disparues` jours ; les plus récentes d'abord."""
    limite = (date.fromisoformat(jour) - timedelta(days=jours_disparues)).isoformat()
    disparues = []
    for infos in historique["offres"].values():
        if "titre" not in infos:
            continue  # entrée migrée de l'ancien format : rien à afficher
        absences = sum(1 for lancement in historique["lancements"]
                       if lancement > infos["derniere_vue"])
        if absences >= lancements_avant_disparition and infos["derniere_vue"] >= limite:
            disparues.append(Disparue(
                titre=infos["titre"], entreprise=infos["entreprise"],
                departement=infos["departement"], adresse=infos["adresse"], url=infos["url"],
                premiere_vue=infos["premiere_vue"], derniere_vue=infos["derniere_vue"],
            ))
    return sorted(disparues, key=lambda disparue: disparue.derniere_vue, reverse=True)
```

4. `python -m pytest tests/test_history.py -q` → vert. `test_main.py` échoue
   (format de l'historique) : corrigé en Tâche 4.
5. Commit avec la Tâche 4 (la suite doit rester verte à chaque commit).

---

### Tâche 3 — Rapport et CSV

Fichiers : `src/veille_alternance/output.py`, `src/veille_alternance/rapport.py`,
`tests/test_output.py`

1. Tests — dans `test_ecrire_csv_offres`, remplacer l'assertion `lignes == [...]` :

```python
    assert lignes == [
        "premiere_vue;departement;titre;entreprise;adresse;trajet_min;anciennete_jours;"
        "contrat;niveau;source;publiee_le;url",
        '2026-09-26;75;"Technicien réseau; H/F";;75012 Paris;;;Apprentissage, '
        "Professionnalisation;5;France Travail;2026-09-03;https://exemple.test",
    ]
```

ajouter en tête `from veille_alternance.history import Disparue`, et à la fin :

```python
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
```

2. Échec attendu : en-tête CSV, `anciennete_jours` inconnu, `disparues` inconnu.

3. Code — `output.py` :

```python
COLONNES_OFFRES = [
    "premiere_vue", "departement", "titre", "entreprise", "adresse", "trajet_min",
    "anciennete_jours", "contrat", "niveau", "source", "publiee_le", "url",
]
```

`rapport.py` — après `_trajet` :

```python
def _anciennete(offre) -> str:
    if offre.anciennete_jours is None:
        return "<td>—</td>"
    titre = f' title="publiée le {_date_fr(offre.publiee_le)}"' if offre.publiee_le else ""
    return f"<td{titre}>{offre.anciennete_jours} j</td>"
```

dans `_ligne_offre`, remplacer
`f"<td>{_e(offre.source)}</td><td>{_date_fr(offre.publiee_le)}</td>"` par :

```python
        f"<td>{_e(offre.source)}</td>{_anciennete(offre)}"
```

après `_ligne_recruteur`, ajouter :

```python
def _ligne_disparue(disparue) -> str:
    texte = f"{disparue.titre} {disparue.entreprise or ''} {disparue.adresse}".lower()
    return (
        f'<tr data-dep="{_e(disparue.departement)}" data-texte="{_e(texte)}">'
        f"<td>{_e(disparue.departement)}</td>"
        f'<td class="titre">{_lien(disparue.url, disparue.titre)}</td>'
        f"<td>{_e(disparue.entreprise or '—')}</td><td>{_e(disparue.adresse)}</td>"
        f"<td>du {_date_fr(disparue.premiere_vue)} au {_date_fr(disparue.derniere_vue)}</td>"
        "</tr>"
    )
```

`ENTETE_OFFRES` : `<th>Publiée</th>` devient `<th>En ligne</th>` ; ajouter :

```python
ENTETE_DISPARUES = (
    "<tr><th>Dép.</th><th>Offre</th><th>Entreprise</th><th>Lieu</th><th>En ligne</th></tr>"
)
```

après `_table`, ajouter :

```python
def _section_repliee(titre: str, entete: str, lignes: list[str]) -> str:
    """Section fermée par défaut ; absente s'il n'y a rien à montrer."""
    if not lignes:
        return ""
    return (
        f"<section><details><summary>{titre}</summary>"
        f"{_table(entete, lignes, '')}</details></section>"
    )
```

dans `MODELE`, après `__SECTION_TROP_LOIN__`, ajouter une ligne `__SECTION_DISPARUES__`.

`ecrire_html` — signature et début :

```python
def ecrire_html(
    offres: list, recruteurs: list, chemin: Path, jour: str,
    trop_loin: list | None = None, disparues: list | None = None,
) -> Path:
    trop_loin = trop_loin or []
    disparues = disparues or []
    nouvelles = [o for o in offres if o.premiere_vue == jour]
    departements = sorted(
        {o.departement for o in offres + trop_loin} | {d.departement for d in disparues}
        | {r.departement for r in recruteurs}
    )
    section_trop_loin = _section_repliee(
        f"Trop loin — {_pluriel(len(trop_loin), 'offre écartée', 'offres écartées')}"
        " par le temps de trajet",
        ENTETE_OFFRES, [_ligne_offre(o, jour) for o in trop_loin],
    )
    section_disparues = _section_repliee(
        f"Disparues récemment — {_pluriel(len(disparues), 'offre', 'offres')}",
        ENTETE_DISPARUES, [_ligne_disparue(d) for d in disparues],
    )
```

et dans `remplacements`, après `"__SECTION_TROP_LOIN__": section_trop_loin,` :

```python
        "__SECTION_DISPARUES__": section_disparues,
```

4. `python -m pytest tests/test_output.py -q` → vert.
5. Commit avec la Tâche 4.

---

### Tâche 4 — Branchement

Fichiers : `src/veille_alternance/__main__.py`, `tests/test_main.py`

1. Tests — dans `test_executer_detecte_les_nouvelles_offres_d_un_jour_a_l_autre`,
   remplacer l'assertion finale sur `historique` par :

```python
    suivi = json.loads(historique.read_text(encoding="utf-8"))
    assert suivi["lancements"] == ["2026-09-26", "2026-09-27"]
    infos = suivi["offres"]["technicien support helpdesk|75012"]
    assert (infos["premiere_vue"], infos["derniere_vue"]) == ("2026-09-26", "2026-09-27")
```

dans `test_executer_ecarte_les_offres_trop_loin`, remplacer
`assert json.loads(historique.read_text(encoding="utf-8")) == {}` par :

```python
    suivi = json.loads(historique.read_text(encoding="utf-8"))
    # Vue (donc jamais « disparue »), mais pas notifiée
    assert "technicien support helpdesk|75012" in suivi["offres"]
```

ajouter à la fin :

```python
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
```

2. Échec attendu : format de l'historique, section absente.

3. Code — `__main__.py` : import `offres_disparues` depuis `history` ;
   le commentaire avant `trop_loin = []` devient :

```python
    # Après les mots-clés : ~20 offres à calculer au lieu de ~1 700. Les offres trop
    # loin ne sont pas notifiées.
```

le bloc historique devient :

```python
    offres, historique = marquer_nouveautes(offres, charger_historique(chemin_historique), jour)
    # Les offres trop loin comptent comme vues : sinon elles passeraient pour disparues
    trop_loin, historique = marquer_nouveautes(trop_loin, historique, jour)
    offres = trier_nouvelles_en_tete(offres, jour)
    nouvelles = [offre for offre in offres if offre.premiere_vue == jour]
    sauvegarder_historique(historique, chemin_historique)
    disparues = offres_disparues(
        historique, jour, config.lancements_avant_disparition, config.jours_disparues
    )
```

après le journal « Recruteurs : … » :

```python
    journal.info("Disparues récemment : %d offres", len(disparues))
```

les deux appels `ecrire_html` reçoivent `disparues=disparues` en plus de
`trop_loin=trop_loin`.

4. `python -m pytest -q` → toute la suite verte.
5. Commit : `Ancienneté des offres et suivi des offres disparues`

---

### Tâche 5 — Activation et documentation

1. `config/search.toml`, avant `[trajet]` :

```toml
[historique]
# Offre « disparue » : absente d'au moins N lancements depuis sa dernière vue
# (un jour sans lancement, PC éteint, ne compte pas). Affichée N jours au rapport.
lancements_avant_disparition = 2
jours_disparues = 14
```

2. Lancement réel `python -m veille_alternance` : l'historique est migré,
   le journal affiche « Disparues récemment : 0 offres », le rapport montre
   la colonne « En ligne ».
3. `README.md` : paragraphe dans « État actuel » + nouveau format de
   l'historique (remplace la phrase « clé de contenu → date de première vue »).
4. Commit : `Suivi des offres disparues activé`

---

## Auto-revue

- Spec → tâches : format + migration (2), critère 2 lancements (2), unité
  lancements (2 : `lancements` dédupliqués par date), offre vue = retenue ou
  trop loin (4), revenue garde sa première vue (2 : `setdefault`), 14 jours (1, 2),
  ancienneté (2, 3), pas de notification (4 : `resume` inchangé), CSV (3).
- Noms constants : `marquer_nouveautes`, `offres_disparues`, `Disparue`,
  `historique_vide`, `anciennete_jours`, `lancements_avant_disparition`,
  `jours_disparues`, `_section_repliee`, `ENTETE_DISPARUES`.
- Les Tâches 2-4 sont commitées ensemble : le format de l'historique change
  dans `history.py` et `__main__.py` en même temps.
