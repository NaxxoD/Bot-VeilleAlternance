"""Rapport HTML lisible : un fichier autonome (CSS et JS intégrés, aucune connexion).

Nouveautés du jour en tête, puis toutes les offres actives, puis les entreprises
pour les candidatures spontanées. Recherche et filtre par département intégrés.
"""

import html
from pathlib import Path


def _e(valeur) -> str:
    """Échappe un texte pour l'insérer dans du HTML."""
    return html.escape("" if valeur is None else str(valeur), quote=True)


def _lien(url: str | None, texte: str) -> str:
    """Lien cliquable uniquement pour une URL http(s) : jamais de 'javascript:'."""
    if url and url.startswith(("https://", "http://")):
        return f'<a href="{_e(url)}" target="_blank" rel="noopener">{_e(texte)}</a>'
    return _e(texte)


def _date_fr(iso: str | None) -> str:
    """'2026-09-03T16:31:40Z' → '03/09/2026'."""
    return f"{iso[8:10]}/{iso[5:7]}/{iso[:4]}" if iso and len(iso) >= 10 else ""


def _pluriel(n: int, singulier: str, pluriel: str) -> str:
    return f"{n} {singulier if n == 1 else pluriel}"


def _trajet(offre) -> str:
    return "?" if offre.trajet_min is None else f"{offre.trajet_min} min"


def _anciennete(offre) -> str:
    if offre.anciennete_jours is None:
        return "<td>—</td>"
    titre = f' title="publiée le {_date_fr(offre.publiee_le)}"' if offre.publiee_le else ""
    return f"<td{titre}>{offre.anciennete_jours} j</td>"


NOMS_RELAIS = {"LABONNEALTERNANCE": "La Bonne Alternance", "METEOJOB": "Meteojob", "PMEJOB": "PMEjob"}


def _relais(nom: str) -> str:
    """'METEOJOB' → 'Meteojob' ; un nom déjà en casse mixte reste tel quel."""
    return NOMS_RELAIS.get(nom, nom.capitalize() if nom.isupper() else nom)


def _source(offre) -> str:
    if not offre.relayee_par:
        return _e(offre.source)
    return f'{_e(offre.source)} <span class="relais">via {_e(_relais(offre.relayee_par))}</span>'


def _employeur(entreprise: str | None) -> str:
    return _e(entreprise) if entreprise else '<span class="inconnu">Employeur inconnu</span>'


def _ligne_offre(offre, jour: str) -> str:
    nouvelle = offre.premiere_vue == jour
    texte = (f"{offre.titre} {offre.entreprise or 'employeur inconnu'} {offre.adresse} "
             f"{offre.source} {offre.relayee_par or ''}").lower()
    badge = '<span class="badge">Nouveau</span>' if nouvelle else ""
    if offre.famille:
        badge += f' <span class="famille">{_e(offre.famille)}</span>'
    classe = ' class="nouvelle"' if nouvelle else ""
    return (
        f'<tr data-dep="{_e(offre.departement)}" data-texte="{_e(texte)}"{classe}>'
        f"<td>{badge}</td><td>{_e(offre.departement)}</td>"
        f'<td class="titre">{_lien(offre.url, offre.titre)}</td>'
        f"<td>{_employeur(offre.entreprise)}</td><td>{_e(offre.adresse)}</td>"
        f"<td>{_trajet(offre)}</td>"
        f"<td>{_source(offre)}</td>{_anciennete(offre)}"
        f"<td>{_date_fr(offre.premiere_vue)}</td></tr>"
    )


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


ENTETE_OFFRES = (
    "<tr><th></th><th>Dép.</th><th>Offre</th><th>Entreprise</th><th>Lieu</th>"
    "<th>Trajet</th><th>Source</th><th>En ligne</th><th>Vue le</th></tr>"
)
ENTETE_RECRUTEURS = (
    "<tr><th>Dép.</th><th>Entreprise</th><th>Adresse</th><th>Trajet</th><th>Effectif</th>"
    "<th>Secteur</th><th>Contact</th></tr>"
)
ENTETE_DISPARUES = (
    "<tr><th>Dép.</th><th>Offre</th><th>Entreprise</th><th>Lieu</th><th>En ligne</th></tr>"
)


def _table(entete: str, lignes: list[str], vide: str) -> str:
    if not lignes:
        return f'<div class="tableau"><p class="vide">{vide}</p></div>'
    return (
        f'<div class="tableau"><table><thead>{entete}</thead>'
        f'<tbody>{"".join(lignes)}</tbody></table></div>'
    )


def _section_repliee(titre: str, entete: str, lignes: list[str]) -> str:
    """Section fermée par défaut ; absente s'il n'y a rien à montrer."""
    if not lignes:
        return ""
    return (
        f"<section><details><summary>{titre}</summary>"
        f"{_table(entete, lignes, '')}</details></section>"
    )


RIEN_DE_NOUVEAU = "Rien de nouveau aujourd'hui."


NOMS_FAMILLES = (("dev", "Développement"), ("infra", "Infrastructure"))


def _offres_actives(offres, jour: str) -> str:
    """Table unique, ou — dès que les offres sont classées — un sous-tableau par famille."""
    if not any(o.famille for o in offres):
        return _table(ENTETE_OFFRES, [_ligne_offre(o, jour) for o in offres], "Aucune offre.")
    parties = []
    for famille, nom in NOMS_FAMILLES:
        groupe = [o for o in offres if o.famille == famille]
        parties.append(
            f"<h4>{nom} — {len(groupe)}</h4>"
            + _table(ENTETE_OFFRES, [_ligne_offre(o, jour) for o in groupe], "Aucune offre.")
        )
    return "".join(parties)


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
        f"{_offres_actives(offres, jour)}"
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
        # Repliée : plusieurs centaines de lignes, sinon il faut défiler longtemps
        + _section_repliee(
            f"Candidatures spontanées — {_pluriel(len(recruteurs), 'entreprise', 'entreprises')}",
            ENTETE_RECRUTEURS, [_ligne_recruteur(r) for r in recruteurs],
        )
        + "</div>"
    )


MODELE = """<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Veille alternance</title>
<style>
:root { --fond:#f6f7f9; --carte:#fff; --texte:#1c2330; --doux:#5b6475; --bord:#dde1e8;
        --accent:#2257d6; --nouveau:#e8f0ff; --badge:#2257d6; --badge-texte:#fff; }
@media (prefers-color-scheme: dark) {
  :root { --fond:#12151b; --carte:#1b2029; --texte:#e6e9ef; --doux:#9aa3b2; --bord:#2c3340;
          --accent:#7aa2ff; --nouveau:#1d2a44; --badge:#7aa2ff; --badge-texte:#10141c; }
}
* { box-sizing:border-box; }
body { margin:0; font:15px/1.45 system-ui,"Segoe UI",sans-serif; background:var(--fond); color:var(--texte); }
main { max-width:1200px; margin:0 auto; padding:24px 16px 48px; }
h1 { font-size:1.5rem; margin:0 0 4px; }
.sous-titre { color:var(--doux); margin:0 0 20px; }
.chiffres { display:flex; gap:12px; flex-wrap:wrap; margin-bottom:20px; }
.chiffre { background:var(--carte); border:1px solid var(--bord); border-radius:10px; padding:10px 16px; }
.chiffre strong { font-size:1.4rem; display:block; }
.outils { display:flex; gap:10px; flex-wrap:wrap; position:sticky; top:0; z-index:1;
          background:var(--fond); padding:10px 0; }
input, select { font:inherit; padding:8px 10px; border:1px solid var(--bord); border-radius:8px;
                background:var(--carte); color:var(--texte); }
input { flex:1; min-width:200px; }
section { margin-top:28px; }
h2.zone { font-size:1.4rem; margin:0 0 14px; }
h3 { font-size:1.15rem; margin:0 0 10px; }
h4 { font-size:1rem; margin:18px 0 8px; color:var(--doux); }
.famille { border:1px solid var(--bord); border-radius:999px; padding:1px 7px; font-size:.7rem;
           color:var(--doux); }
.bloc { margin-top:40px; padding-top:16px; border-top:3px solid var(--accent); }
.tableau { overflow-x:auto; background:var(--carte); border:1px solid var(--bord); border-radius:10px; }
table { border-collapse:collapse; width:100%; }
th, td { text-align:left; padding:8px 10px; border-bottom:1px solid var(--bord); vertical-align:top; }
th { font-size:.8rem; text-transform:uppercase; letter-spacing:.03em; color:var(--doux); }
tr:last-child td { border-bottom:none; }
tr.nouvelle td { background:var(--nouveau); }
td.titre { min-width:260px; font-weight:500; }
a { color:var(--accent); }
.inconnu { color:#b3541e; font-style:italic; }
.relais { color:#6b7280; font-size:.85em; }
.badge { background:var(--badge); color:var(--badge-texte); border-radius:999px; padding:2px 8px;
         font-size:.75rem; font-weight:600; white-space:nowrap; }
.vide { color:var(--doux); padding:14px; margin:0; }
summary { cursor:pointer; font-size:1.15rem; font-weight:600; margin:0 0 10px; }
</style>
</head>
<body>
<main>
<h1>Veille alternance</h1>
<p class="sous-titre">Systèmes, réseaux, infrastructure — Île-de-France et Loiret — rapport du __JOUR_FR__</p>
<div class="outils">
  <input id="recherche" type="search" placeholder="Rechercher (titre, entreprise, ville…)">
  <select id="departement"><option value="">Tous les départements</option>__OPTIONS__</select>
</div>
__BLOCS__
</main>
<script>
(function () {
  var recherche = document.getElementById("recherche");
  var departement = document.getElementById("departement");
  function filtrer() {
    var texte = recherche.value.toLowerCase().trim();
    var dep = departement.value;
    document.querySelectorAll("tr[data-dep]").forEach(function (ligne) {
      var garde = (!dep || ligne.dataset.dep === dep) &&
                  (!texte || ligne.dataset.texte.indexOf(texte) !== -1);
      ligne.style.display = garde ? "" : "none";
    });
  }
  recherche.addEventListener("input", filtrer);
  departement.addEventListener("change", filtrer);
})();
</script>
</body>
</html>
"""


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
    if reste or not zones:
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
