# Architecture du dossier

Chaque dossier a une seule responsabilité.

```
Bot_Veille_Alternance/
├── .gitignore
├── .env.example              modèle du .env (clé API, jamais versionnée)
├── src/
│   └── veille_alternance/    code exécutable : client API, collecte, normalisation, filtres, sortie
├── config/                   paramétrage sans logique : ROME, départements, mots-clés, types de contrat
├── data/
│   ├── raw/                  réponses brutes de l'API, une par requête (non versionné)
│   └── processed/            offres_*.json et recruteurs_*.json (non versionné)
├── docs/                     connaissance : étude de l'API, architecture, décisions
├── tests/
│   └── fixtures/             vraies réponses API sauvegardées pour tester sans réseau
└── scripts/                  utilitaires ponctuels (ex. appel manuel de test à l'API)
```

## Règles

- `src/` ne contient aucune valeur de paramétrage en dur : tout vient de `config/` ou de `.env`.
- `config/` ne contient aucune logique.
- `data/` n'est jamais versionné, seule sa structure l'est (`.gitkeep`).
- La clé API vit uniquement dans `.env`.
- `scripts/` sert aux essais et à l'exploitation, pas au fonctionnement normal du projet.

## Références

- Étude de l'API La Bonne Alternance : `docs/etude_api_lba.md` (référence)
