# Plan — tri des recruteurs et rapport en deux zones

**Objectif** : n'afficher que les entreprises de 10 salariés et plus à moins de
45 min, cœur numérique d'abord puis par trajet, dans un rapport découpé en
deux blocs Île-de-France / Loiret.

Spec : `docs/specs/2026-09-28-recruteurs-zones-design.md`.

## Fichiers touchés

| Fichier | Changement |
|---|---|
| `src/veille_alternance/config.py` | `naf_coeur`, `zones` |
| `src/veille_alternance/normalize.py` | `Recruteur.latitude/longitude/trajet_min` |
| `src/veille_alternance/process.py` | `trier_recruteurs` |
| `src/veille_alternance/trajet.py` | annotations `Offre \| Recruteur`, message de journal |
| `src/veille_alternance/output.py` | `trajet_min` dans `COLONNES_RECRUTEURS` |
| `src/veille_alternance/rapport.py` | blocs par zone, colonne Trajet et lien LBA recruteurs |
| `src/veille_alternance/__main__.py` | trajet + tri recruteurs, zones au rapport |
| `config/search.toml` | tailles, `naf_coeur`, `[[rapport.zones]]` |
| tests `config`, `normalize`, `process`, `trajet`, `output`, `main` | |
| `README.md` | état actuel |

---

### Tâche 1 — Configuration

`tests/test_config.py`, à la fin :

```python
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
```

`Config`, après `jours_disparues` :

```python
    naf_coeur: list[str] = field(default_factory=list)  # recruteurs classés en premier
    zones: list[tuple[str, list[str]]] = field(default_factory=list)  # blocs du rapport
```

`Config(...)`, après `jours_disparues=...` :

```python
        naf_coeur=list(donnees.get("filtres_recruteurs", {}).get("naf_coeur", [])),
        zones=[
            (zone["nom"], list(zone["departements"]))
            for zone in donnees.get("rapport", {}).get("zones", [])
        ],
```

Commit : `Configuration du classement des recruteurs et des zones du rapport`

---

### Tâche 2 — Recruteurs : coordonnées, tri, trajet

`tests/test_normalize.py`, à la fin :

```python
def test_coordonnees_recruteur():
    _, recruteurs = normaliser_reponse(json.loads(FIXTURE.read_text(encoding="utf-8")), "75")
    assert (recruteurs[0].longitude, recruteurs[0].latitude) == (2.299246999999999, 48.877323999986366)
    assert recruteurs[0].trajet_min is None
```

`tests/test_process.py` : ajouter `trier_recruteurs` à l'import, et à la fin :

```python
def test_trier_recruteurs_coeur_puis_trajet():
    from dataclasses import replace
    loin_coeur = replace(recruteur("1", naf="62.02A"), trajet_min=40)
    proche_coeur = replace(recruteur("2", naf="62.01Z"), trajet_min=10)
    inconnu_coeur = recruteur("3", naf="61.10Z")
    proche_autre = replace(recruteur("4", naf="46.51Z"), trajet_min=5)
    resultat = trier_recruteurs(
        [proche_autre, inconnu_coeur, loin_coeur, proche_coeur], ["62", "61"]
    )
    assert [r.siret for r in resultat] == ["2", "1", "3", "4"]
```

`tests/test_trajet.py` : importer `Recruteur` depuis `normalize`, et à la fin :

```python
def test_repartit_aussi_les_recruteurs(tmp_path):
    esn = Recruteur(
        siret="1", nom="ESN", adresse="45000 Orléans", departement="45", taille="20-49",
        secteur=None, naf="62.02A", site_web=None, telephone=None,
        url="https://exemple.test", longitude=1.90, latitude=47.90,
    )
    voiture = FauxClient({(1.90, 47.90): 24.0})
    proches, trop_loin = creer_trajets(tmp_path, voiture=voiture).repartir([esn])
    assert [r.trajet_min for r in proches] == [24]
    assert trop_loin == []
```

Code — `normalize.py`, `Recruteur` après `url` :

```python
    latitude: float | None = None
    longitude: float | None = None
    trajet_min: int | None = None  # depuis le domicile, renseigné par trajet
```

`normaliser_recruteur`, avant `return Recruteur(` :

```python
    geopoint = lieu["location"].get("geopoint") or {}
    longitude, latitude = (geopoint.get("coordinates") or [None, None])[:2]
```

et en fin d'appel : `latitude=latitude, longitude=longitude,`

`process.py`, après `filtrer_recruteurs` :

```python
def trier_recruteurs(recruteurs: list[Recruteur], naf_coeur: list[str]) -> list[Recruteur]:
    """Cœur numérique d'abord (préfixes NAF), puis du plus proche au plus loin ;
    trajet inconnu en fin de groupe."""
    def cle(recruteur: Recruteur) -> tuple:
        coeur = bool(recruteur.naf) and any(recruteur.naf.startswith(p) for p in naf_coeur)
        return (not coeur, recruteur.trajet_min is None, recruteur.trajet_min or 0)
    return sorted(recruteurs, key=cle)
```

`trajet.py` : importer `Recruteur` ; remplacer les annotations `Offre` de
`Trajets` (`_en_voiture`, `_point`, `minutes`, `repartir`) par
`Offre | Recruteur` ; docstring de `repartir` :
`"""(éléments dans le périmètre ou au trajet inconnu, éléments trop loin)."""` ;
journal : `"Trajet inconnu pour %d éléments, gardés par prudence"`.

Commit : `Recruteurs : coordonnées, trajet et classement`

---

### Tâche 3 — Rapport en blocs par zone

`tests/test_output.py` :

- `test_ecrire_json` : le dict attendu gagne
  `"latitude": None, "longitude": None, "trajet_min": None`.
- à la fin :

```python
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
    assert '>postuler via LBA</a>' in page
```

Code — `output.py` :

```python
COLONNES_RECRUTEURS = [
    "departement", "nom", "adresse", "trajet_min", "taille", "secteur", "naf",
    "telephone", "site_web", "url",
]
```

`rapport.py` — `_ligne_recruteur` devient :

```python
def _ligne_recruteur(recruteur) -> str:
    texte = f"{recruteur.nom or ''} {recruteur.adresse} {recruteur.secteur or ''}".lower()
    contacts = [_lien(recruteur.url, "postuler via LBA")]
    if recruteur.site_web:
        contacts.append(_lien(recruteur.site_web, "site"))
    if recruteur.telephone:
        contacts.append(_e(recruteur.telephone))
    return (
        f'<tr data-dep="{_e(recruteur.departement)}" data-texte="{_e(texte)}">'
        f"<td>{_e(recruteur.departement)}</td>"
        f'<td class="titre">{_lien(recruteur.url, recruteur.nom or recruteur.siret)}</td>'
        f"<td>{_e(recruteur.adresse)}</td><td>{_trajet(recruteur)}</td>"
        f"<td>{_e(recruteur.taille or '—')}</td>"
        f"<td>{_e(recruteur.secteur or '—')}</td><td>{' · '.join(contacts)}</td></tr>"
    )
```

```python
ENTETE_RECRUTEURS = (
    "<tr><th>Dép.</th><th>Entreprise</th><th>Adresse</th><th>Trajet</th><th>Effectif</th>"
    "<th>Secteur</th><th>Contact</th></tr>"
)
```

`_section_repliee` : inchangée. Ajouter après elle (constante à part : une
apostrophe dans une f-string entre guillemets simples n'est valide qu'à partir
de Python 3.12, le projet vise 3.11) :

```python
RIEN_DE_NOUVEAU = "Rien de nouveau aujourd'hui."
```

```python
def _bloc(nom: str, jour: str, offres, trop_loin, disparues, recruteurs) -> str:
    """Un bloc de zone : ses chiffres puis ses sections."""
    nouvelles = [o for o in offres if o.premiere_vue == jour]
    chiffres = (
        f'<div class="chiffres">'
        f'<div class="chiffre"><strong>{len(nouvelles)}</strong>nouveautés du jour</div>'
        f'<div class="chiffre"><strong>{len(offres)}</strong>offres actives</div>'
        f'<div class="chiffre"><strong>{len(recruteurs)}</strong>entreprises à démarcher</div>'
        f"</div>"
    )
    return (
        f'<div class="bloc"><h2 class="zone">{_e(nom)}</h2>{chiffres}'
        f"<section><h3>{_pluriel(len(nouvelles), 'nouvelle offre', 'nouvelles offres')}</h3>"
        f"{_table(ENTETE_OFFRES, [_ligne_offre(o, jour) for o in nouvelles], RIEN_DE_NOUVEAU)}"
        f"</section>"
        f"<section><h3>{_pluriel(len(offres), 'offre active', 'offres actives')}</h3>"
        f"{_table(ENTETE_OFFRES, [_ligne_offre(o, jour) for o in offres], 'Aucune offre.')}"
        f"</section>"
        + _section_repliee(
            f"Trop loin — {_pluriel(len(trop_loin), 'offre écartée', 'offres écartées')}"
            " par le temps de trajet",
            ENTETE_OFFRES, [_ligne_offre(o, jour) for o in trop_loin],
        )
        + _section_repliee(
            f"Disparues récemment — {_pluriel(len(disparues), 'offre', 'offres')}",
            ENTETE_DISPARUES, [_ligne_disparue(d) for d in disparues],
        )
        + f"<section><h3>Candidatures spontanées — "
        f"{_pluriel(len(recruteurs), 'entreprise', 'entreprises')}</h3>"
        f"{_table(ENTETE_RECRUTEURS, [_ligne_recruteur(r) for r in recruteurs], 'Aucune entreprise.')}"
        f"</section></div>"
    )
```

`MODELE` : CSS — `h2 { … }` devient :

```css
h2.zone { font-size:1.4rem; margin:0 0 14px; }
h3 { font-size:1.15rem; margin:0 0 10px; }
.bloc { margin-top:40px; padding-top:16px; border-top:3px solid var(--accent); }
```

corps — supprimer le `<div class="chiffres">…</div>` global et remplacer les
lignes de `<section><h2>__TITRE_NOUVELLES__…` jusqu'à
`<section><h2>Candidatures spontanées…</section>` par une seule ligne
`__BLOCS__`.

`ecrire_html` devient :

```python
def ecrire_html(
    offres: list, recruteurs: list, chemin: Path, jour: str,
    trop_loin: list | None = None, disparues: list | None = None,
    zones: list[tuple[str, list[str]]] | None = None,
) -> Path:
    trop_loin = trop_loin or []
    disparues = disparues or []
    zones = list(zones or [])
    tous = offres + trop_loin + disparues + recruteurs
    departements = sorted({element.departement for element in tous})
    connus = {departement for _, deps in zones for departement in deps}
    reste = [departement for departement in departements if departement not in connus]
    if reste:
        zones.append(("Autres départements" if zones else "Toutes zones", reste))

    def dans(elements, deps):
        return [element for element in elements if element.departement in deps]

    blocs = "".join(
        _bloc(nom, jour, dans(offres, deps), dans(trop_loin, deps), dans(disparues, deps),
              dans(recruteurs, deps))
        for nom, deps in zones
    )
    remplacements = {
        "__JOUR_FR__": _date_fr(jour),
        "__OPTIONS__": "".join(f'<option value="{_e(d)}">{_e(d)}</option>' for d in departements),
        "__BLOCS__": blocs,
    }
    page = MODELE
    for marqueur, valeur in remplacements.items():
        page = page.replace(marqueur, valeur)
    chemin.parent.mkdir(parents=True, exist_ok=True)
    chemin.write_text(page, encoding="utf-8")
    return chemin
```

Note : sans zone configurée, un bloc unique « Toutes zones » garde le
comportement actuel (tests existants inchangés).

Commit : `Rapport en blocs par zone, trajet des recruteurs`

---

### Tâche 4 — Branchement

`tests/test_main.py`, à la fin :

```python
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
```

Code — `__main__.py` : importer `trier_recruteurs` depuis `process` ; après
`recruteurs = filtrer_recruteurs(...)` :

```python
    trop_loin_recruteurs = []
    if trajets is not None:
        recruteurs, trop_loin_recruteurs = trajets.repartir(recruteurs)
    recruteurs = trier_recruteurs(recruteurs, config.naf_coeur)
```

le journal des recruteurs devient :

```python
    journal.info(
        "Recruteurs : %d uniques, %d retenus après filtres, %d trop loin",
        total_recruteurs, len(recruteurs), len(trop_loin_recruteurs),
    )
```

les deux appels `ecrire_html` reçoivent `zones=config.zones`.

Commit : `Recruteurs triés par cœur numérique et trajet`

---

### Tâche 5 — Activation

`config/search.toml` :

- `[filtres_recruteurs]` : `tailles_exclues = ["0-0", "1-2", "3-5", "6-9"]`
  (commentaire : moins de 10 salariés, rarement un tuteur disponible) et
  `naf_coeur = ["62", "63.11", "61"]`.
- à la fin :

```toml
[[rapport.zones]]
# Un bloc par zone dans le rapport ; un département hors zone va dans « Autres »
nom = "Île-de-France"
departements = ["75", "77", "78", "91", "92", "93", "94", "95"]

[[rapport.zones]]
nom = "Loiret"
departements = ["45", "41"]
```

Lancement réel (~10 min la première fois) ; vérifier le journal
(`Recruteurs : … trop loin`) et les deux blocs du rapport. `README.md` :
paragraphe dans « État actuel ». Commit : `Tri des recruteurs et rapport en deux zones activés`

---

## Auto-revue

- Spec → tâches : taille (5), trajet recruteurs (2, 4), inconnu en fin (2),
  classement (2, 4), deux blocs (3, 5), Autres départements (3), lien LBA (3),
  CSV (3), coût (5 : premier lancement mesuré).
- Noms : `trier_recruteurs`, `naf_coeur`, `zones`, `_bloc`, `ENTETE_RECRUTEURS`,
  `Trajets.repartir` identiques partout.
- `test_ecrire_html` existant : textes « 1 nouvelle offre », « 2 offres
  actives », « 1 entreprise » toujours présents (bloc « Toutes zones »).
