# Tri des recruteurs et rapport en deux zones — conception

**Date** : 2026-09-28 — **Statut** : validée par l'utilisateur, à planifier.

## Problème

- 613 entreprises « à démarcher » : trop pour candidater à la main, sans ordre
  de priorité ni notion de distance.
- Le Loiret n'a presque aucune offre informatique sur FT/LBA (vérifié le
  2026-09-28 : 0 en apprentissage, 0 en contrat pro, 1 sur LBA) : les
  candidatures spontanées y sont le principal levier.
- Le rapport mélange Île-de-France et Loiret : peu lisible.

## Décisions

| Sujet | Choix | Écarté |
|---|---|---|
| Taille | ≥ 10 salariés (`tailles_exclues` += 1-2, 3-5, 6-9 ; config seule) | 6+ (moins ciblé), 20+ (Loiret ~15), pas de seuil |
| Trajet | Même règle et seuils que les offres (45 min, PRIM / IGN) ; trop loin → écartés, comptés au journal | Section « trop loin » pour les recruteurs (inutile) |
| Trajet inconnu | Gardé, classé en fin de groupe | — |
| Classement | Cœur numérique (`naf_coeur` = 62, 63.11, 61) d'abord, puis trajet croissant | Trajet seul ; taille puis trajet |
| Rapport | Deux blocs complets, zones dans `search.toml` | Onglets ; sous-titres par section |
| Département hors zone | Bloc « Autres départements », affiché s'il n'est pas vide | — |
| Colonne Contact | Lien « postuler via LBA » + site / téléphone s'ils existent | — |

## Fonctionnement

1. Recruteurs : dédoublonnage → `filtrer_recruteurs` (NAF, taille) →
   `Trajets.repartir` (coordonnées LBA, pas de géocodage) →
   `trier_recruteurs(recruteurs, naf_coeur)`.
2. Rapport : pour chaque zone `(nom, départements)`, un bloc avec ses chiffres
   (nouveautés, offres actives, entreprises) et ses sections (nouveautés,
   offres actives, trop loin, disparues, candidatures spontanées). Recherche
   et filtre par département restent communs, en haut de page.

Coût : ~650 appels PRIM au premier lancement (~10 min), puis seulement les
nouvelles entreprises de l'échantillon LBA du jour (cache par coordonnées).

## Configuration

```toml
[filtres_recruteurs]
tailles_exclues = ["0-0", "1-2", "3-5", "6-9"]
naf_coeur = ["62", "63.11", "61"]

[[rapport.zones]]
nom = "Île-de-France"
departements = ["75", "77", "78", "91", "92", "93", "94", "95"]

[[rapport.zones]]
nom = "Loiret"
departements = ["45", "41"]
```

## Composants

- `normalize.py` : `Recruteur.latitude`, `longitude`, `trajet_min` ;
  coordonnées lues dans `workplace.location.geopoint`.
- `trajet.py` : annotations `Offre | Recruteur` (logique inchangée).
- `process.py` : `trier_recruteurs`.
- `config.py` : `naf_coeur`, `zones`.
- `__main__.py` : trajet + tri des recruteurs, zones passées au rapport.
- `rapport.py` : `_bloc` par zone, sections en `h3`, colonne Trajet et lien LBA
  pour les recruteurs.
- `output.py` : `trajet_min` dans le CSV des recruteurs.

## Tests

- Coordonnées des recruteurs (fixture LBA).
- `trier_recruteurs` : cœur d'abord, trajet croissant, inconnu en fin de groupe.
- `Trajets.repartir` sur un `Recruteur`.
- Rapport : un bloc par zone dans l'ordre, éléments dans le bon bloc, bloc
  « Autres départements » seulement si nécessaire, colonne Trajet recruteurs.
- `executer` : recruteurs triés et porteurs d'un `trajet_min` avec trajets.

## Hors périmètre

- Recherche d'adresses e-mail, envoi via Bridge ou API LBA.
- Onglets, tri interactif des colonnes.
