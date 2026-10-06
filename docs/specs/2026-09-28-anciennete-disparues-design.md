# Ancienneté des offres et offres disparues — conception

**Date** : 2026-09-28 — **Statut** : validée par l'utilisateur, à planifier.

## Problème

- Le rapport affiche la date de publication brute : l'âge d'une offre (ex.
  EDF publiée le 10 avril, toujours en ligne) ne saute pas aux yeux.
- Une offre qui n'est plus publiée sort du rapport sans laisser de trace :
  impossible de savoir qu'elle est fermée (ex. une offre où l'on a postulé).

## Décisions

| Sujet | Choix | Écarté |
|---|---|---|
| Usage des disparues | Information : « cette offre est fermée » | Suivi de candidatures (nécessite de noter ses candidatures) ; statistiques marché (trop peu de données) |
| Stockage | Enrichir `data/historique_offres.json` | Recalcul depuis les `offres_*.json` (fichiers jetables) ; fichier `disparues.json` séparé (deux états à synchroniser) |
| Critère de disparition | Absente d'au moins **2 lancements** depuis sa dernière vue | 1 lancement : bruit (plafond LBA, panne) ; 3 : info trop tardive |
| Unité | Lancements, pas jours : un jour PC éteint ne compte pas | — |
| Offre « vue » | Retenue **ou** trop loin | Retenue seule : Cergy, Rambouillet… passeraient pour disparues à cause du filtre trajet |
| Offre revenue | Redevient active, garde sa première vue | — |
| Affichage | Disparues des **14 derniers jours** (dernière vue), section repliée | — |
| Âge | Jours depuis `publiee_le` (source), sinon depuis la première vue | Première vue seule : l'historique ne remonte qu'au 2026-09-26 |
| Notification | Aucune pour les disparues | — |

## Format de l'historique

```json
{
  "lancements": ["2026-09-26", "2026-09-27"],
  "offres": {
    "technicien support helpdesk|75012": {
      "premiere_vue": "2026-09-26", "derniere_vue": "2026-09-27",
      "titre": "...", "entreprise": "...", "departement": "75",
      "adresse": "75012 Paris 12e", "url": "https://..."
    }
  }
}
```

- `lancements` : dates distinctes (deux lancements le même jour = un seul).
- **Migration** : l'ancien format `{clé: date}` devient
  `{premiere_vue: date, derniere_vue: date}` sans description ; ces entrées
  ne sont jamais affichées comme disparues (rien à montrer). Automatique,
  au chargement.

## Règles

- Disparue ⇔ description présente, nombre de `lancements` postérieurs à
  `derniere_vue` ≥ `lancements_avant_disparition`, et
  `derniere_vue` ≥ aujourd'hui − `jours_disparues`.
- `anciennete_jours` = aujourd'hui − date(`publiee_le` ou `premiere_vue`), ≥ 0.

## Composants

- `normalize.py` : `Offre.anciennete_jours`.
- `history.py` : nouveau format, migration, `marquer_nouveautes` renseigne
  aussi dernière vue, description et ancienneté ; `offres_disparues` ;
  dataclass `Disparue`.
- `__main__.py` : `marquer_nouveautes` aussi sur les offres trop loin ;
  calcul des disparues ; passage au rapport.
- `rapport.py` : colonne « En ligne » (« 25 j », date de publication au
  survol) à la place de « Publiée » ; section repliée « Disparues récemment ».
  Factorisation des sections repliées.
- `output.py` : colonne `anciennete_jours` dans les CSV d'offres.
- `config.py` / `search.toml` : section `[historique]`
  (`lancements_avant_disparition = 2`, `jours_disparues = 14`).

## Tests

- Migration de l'ancien format ; sauvegarde/chargement du nouveau.
- Dernière vue, description, lancements sans doublon ; original non modifié.
- Ancienneté depuis la publication et à défaut depuis la première vue.
- Disparue après 2 lancements sans elle ; pas après 1 ; masquée au-delà de
  14 jours ; entrée migrée ignorée.
- Bout en bout : 3 lancements (offre, vide, vide) → section « Disparues
  récemment » au 3e seulement.

## Hors périmètre

- Suivi des candidatures, statistiques de durée de vie, notification.
- Disparition des recruteurs.
