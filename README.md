# Bot Veille Alternance

Outil personnel de veille d'offres d'alternance, en Python, sans IA ni base de données.
Il interroge deux sources, filtre, déduplique et produit des fichiers prêts à lire.

## Ce que fait l'outil

- **Collecte** : La Bonne Alternance (API REST, clé Bearer) et France Travail (OAuth2, pagination).
- **Filtres** : contrat d'apprentissage, exclusion des offres d'écoles, mots-clés de titre et de description, classement développement / infrastructure.
- **Déduplication** en deux temps : par identifiant, puis par contenu (titre normalisé + code postal).
- **Temps de trajet** : transports en commun (API PRIM d'Île-de-France Mobilités) ou voiture (API IGN), avec seuil configurable.
- **Historique** : détecte les offres nouvelles et les offres disparues d'un lancement à l'autre.
- **Sorties** : JSON, CSV (Excel) et un rapport HTML autonome.
- **Automatisation** : lanceur Windows et notification native (`scripts/`).

## Installation

```bash
python -m venv .venv
.venv\Scripts\activate          # Windows
pip install -e ".[dev]"
cp .env.example .env            # puis renseigner les clés
```

Les clés (La Bonne Alternance, France Travail, PRIM) se demandent gratuitement sur les sites indiqués dans `.env.example`.

## Utilisation

```bash
python -m veille_alternance     # lance la veille
python -m veille_alternance.bilan
python -m pytest                # 131 tests, sans réseau
```

Tous les réglages (départements, mots-clés, seuils de trajet, points de départ) sont dans `config/search.toml`.
Les points de départ fournis sont des coordonnées d'exemple : remplace-les par les tiens.

## Structure

- `src/veille_alternance/` : code
- `config/` : paramétrage sans logique
- `docs/` : étude des API, architecture, plans et spécifications
- `tests/` : tests ; `tests/fixtures/` contient des réponses d'API enregistrées
- `data/` : sorties locales, non versionnées

## Données

Les offres proviennent de La Bonne Alternance et de France Travail (Licence Ouverte 2.0, usage non lucratif).
Les fixtures de test sont des extraits d'offres publiques.
