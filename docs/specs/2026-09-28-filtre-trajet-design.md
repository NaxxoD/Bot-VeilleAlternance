# Filtre par temps de trajet — conception

**Date** : 2026-09-28 — **Statut** : validée par l'utilisateur, à planifier.

## Problème

Le filtre par département laisse passer des offres trop lointaines en pratique
(ex. Cergy, Rambouillet, Médan depuis l'est parisien). Le critère utile est le
temps de trajet réel depuis le domicile, pas l'appartenance à un département.

## Décisions

| Sujet | Choix | Écarté |
|---|---|---|
| Mesure | Temps de trajet réel | Vol d'oiseau : ignore les lignes de transport |
| Île-de-France | Transports en commun, API calculateur PRIM (IDFM, Navitia) | — |
| Loiret | Voiture, API itinéraire Géoplateforme IGN | — |
| Départ IDF | Départ A (transports) **et** Départ B (transports), on garde le plus court | Adresse du domicile (donnée perso) |
| Départ Loiret | départ Loiret (exemple) | — |
| Seuil IDF | 45 min | 60 min jugé trop long |
| Seuil voiture | 45 min **selon l'IGN** | 30 min : exclut Châteauneuf-sur-Loire |
| Offres hors seuil | Écartées des retenues, visibles dans une section « trop loin » du rapport | Afficher seulement ; écarter sans trace |
| Trajet incalculable | Offre **gardée**, marquée « ? » | L'écarter : une panne réseau ferait perdre des offres |
| Département 41 | Ajouté à la recherche (une commune du 41) ; le seuil écarte le reste | — |

### Calibrage du seuil voiture (IGN, profil `car`, `fastest`, depuis le départ Loiret)

L'IGN est pessimiste sur les petites routes : Châteauneuf via Jargeau = 53 min
selon l'API, ~30-35 min selon l'utilisateur. Le seuil est donc calé sur les
villes limites données par l'utilisateur, mesurées par l'API elle-même.

| Ville | Temps IGN | Verdict à 45 min |
|---|---|---|
| Jouy-le-Potier | 12 min | dedans |
| une commune du 41 (41) | 19 min | dedans |
| Orléans | 24 min | dedans |
| Saran | 27 min | dedans |
| Beaugency | 28 min | dedans |
| Châteauneuf-sur-Loire | 45 min | limite, dedans |
| Pithiviers | 59 min | dehors |

## Données constatées

- LBA : coordonnées toujours présentes (`workplace.location.geopoint`).
- France Travail : coordonnées dans `lieuTravail.latitude/longitude` pour
  516 offres sur 2 657 (2026-09-27). Les autres n'ont que code postal + commune
  → géocodage nécessaire.

## Fonctionnement

Le calcul s'applique **après** le filtre mots-clés (~20 offres/jour), avant
`marquer_nouveautes`. Le vivier (`pool_offres_*.json`, interface avec
Bot_Tri_Alternance) n'est pas modifié.

Pour chaque offre :

1. **Coordonnées** : celles de l'offre si présentes, sinon géocodage IGN de
   l'adresse (`https://data.geopf.fr/geocodage/search`, sans clé).
2. **Base** : département dans `[trajet.voiture] departements` → voiture depuis
   le départ Loiret ; sinon → transports depuis chaque départ IDF, minimum retenu.
3. **Date de départ** (transports) : prochain jour ouvré à 08:00.
4. **Classement** :
   - `trajet_min <= max_minutes` → retenue ;
   - `trajet_min > max_minutes` → « trop loin » ;
   - `trajet_min is None` (adresse introuvable, API en erreur) → retenue, « ? ».

Les erreurs des API de trajet sont journalisées en avertissement ; elles ne
font jamais échouer la veille (code de retour inchangé).

## Composants

- **`src/veille_alternance/trajet.py`** (nouveau)
  - géocodage IGN ;
  - client PRIM (transports) et client IGN (voiture), même interface
    `duree_minutes(depart, arrivee) -> float | None` ;
  - cache disque `data/cache_trajets.json` : coordonnées par adresse, durée
    par (mode, départ, arrivée arrondie à 3 décimales ≈ 100 m). Supprimer le
    fichier vide le cache ;
  - `calculer_trajets(offres, config, clients, cache) -> (retenues, trop_loin)`.
- **`normalize.py`** : `Offre` reçoit `latitude`, `longitude` (sources) et
  `trajet_min` (renseigné par `trajet`).
- **`__main__.py`** : appel après `filtrer_mots_cles` ; `trop_loin` exclu de
  l'historique, des nouveautés et de `resume.json` (pas de notification).
- **`output.py`** : colonne `trajet_min` dans les CSV d'offres.
- **`rapport.py`** : colonne « trajet » ; section repliée « Trop loin (N) »
  avec le temps de chaque offre ; « ? » si inconnu.
- **`config.py` / `search.toml`** : section `[trajet]`, département 41.
- **`.env`** : `PRIM_API_KEY` (compte PRIM créé avec l'alias dédié).

## Configuration

```toml
[trajet]
actif = true

[trajet.transports]      # Île-de-France, API PRIM
departs = [[2.347, 48.859], [2.32, 48.865]]  # départ A, départ B (coordonnées d exemple)
heure_depart = "08:00"   # prochain jour ouvré
max_minutes = 45

[trajet.voiture]         # API itinéraire IGN
departements = ["45", "41"]
depart = [1.88, 47.85]   # départ Loiret (exemple)
max_minutes = 45
```

Coordonnées au format `[longitude, latitude]`, obtenues par géocodage IGN
le 2026-09-28.

## API

- **PRIM** : `GET https://prim.iledefrance-mobilites.fr/marketplace/v2/navitia/journeys`
  (`from=lon;lat`, `to=lon;lat`, `datetime=AAAAMMJJTHHMMSS`), jeton dans
  l'en-tête `apikey` (vérifié le 2026-09-28). Quota 20 000 requêtes/jour.
  Réponse : `journeys[]` (types best, comfort, rapid…), `duration` en
  secondes ; on garde le minimum. Réponse brute ~290 Ko : fixture allégée
  `tests/fixtures/prim_journeys_idf_cergy.json`.

  Mesures réelles (mardi 8 h, meilleur des deux départs) : Noisy-le-Grand
  19 min, Paris 15e 39 min, Courbevoie 41 min, Cergy 71 min, Guyancourt
  88 min, Rambouillet 91 min.
- **IGN itinéraire** : `GET https://data.geopf.fr/navigation/itineraire`
  (`resource=bdtopo-osrm`, `profile=car`, `optimization=fastest`,
  `timeUnit=minute`), sans clé, 5 requêtes/s par IP. Ne tient pas compte du trafic.

## Tests

- Fixtures réelles : réponse PRIM, réponse IGN itinéraire, réponse géocodage.
- Faux clients pour : sous le seuil, au-dessus, trajet `None`, minimum des
  deux départs IDF, choix de la base selon le département, cache (pas de
  second appel pour un même lieu).
- Les 73 tests existants doivent rester verts.

## Hors périmètre

- Trafic routier, horaires multiples, retour du soir.
- Temps de trajet pour les recruteurs (candidatures spontanées).
- Filtrage du vivier.
