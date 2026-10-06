# Étude — API France Travail « Offres d'emploi v2 »

> Tests réels du 2026-09-26 (identifiants de production). Ce fichier est la référence.

France Travail en direct complète La Bonne Alternance : sur les 9 départements, l'API renvoie **2 673 offres en apprentissage** (tous métiers), avec une vraie pagination. Avec les mêmes filtres que LBA, elle ajoute **6 offres pertinentes** que LBA ne voit pas (16 au total contre 10 avec LBA seule).

## Accès et authentification

- Compte sur [francetravail.io](https://francetravail.io), une **application** (ici `botveillealternance`), puis **ajouter l'API « Offres d'emploi v2 »** à l'application.
  - Piège rencontré : sans API ajoutée, le jeton est refusé avec `invalid_client`, même avec des identifiants corrects.
- Le formulaire exige une URL de site : l'URL du dépôt GitHub privé du projet a été acceptée (les IP locales et `localhost` sont refusées).
- Identifiants dans `.env` : `FT_CLIENT_ID` (forme `PAR_<application>_<64 hex>`) et `FT_CLIENT_SECRET` (64 hex).
- OAuth2 « client credentials » :
  - `POST https://entreprise.francetravail.fr/connexion/oauth2/access_token?realm=/partenaire`
  - corps : `grant_type=client_credentials`, `client_id`, `client_secret`, `scope=api_offresdemploiv2 o2dsoffre`
  - réponse : `access_token`, `expires_in: 1499` (~25 min). Le client le renouvelle 60 s avant expiration.

## Recherche

`GET https://api.francetravail.io/partenaire/offresdemploi/v2/offres/search`, en-tête `Authorization: Bearer <jeton>`.

| Paramètre | Constaté |
| --- | --- |
| `departement` | Un code, ou jusqu'à 5 séparés par des virgules (`75,92,93,94,78` fonctionne) |
| `natureContrat` | `E2` = apprentissage, `FS` = professionnalisation |
| `range` | `debut-fin`, **150 résultats maximum** par appel (`0-200` → HTTP 400) ; index maximum ~3 150 |
| `motsCles` | Fonctionne (« informatique » à Paris : 19 offres) — non utilisé : on filtre en Python |
| `codeROME` | Fonctionne ; les offres FT portent encore des codes ROME v3 (M1810, M1805…) |
| `publieeDepuis` | Accepté (`1` à Paris : 142 offres) |

Codes HTTP : **206** page partielle, **200** dernière page, **204** aucun résultat. En-tête `Content-Range: offres 0-149/844` = total.

Quota : en-têtes `X-Ratelimit-*` ; 10 appels/s par application. Une collecte complète = ~22 appels.

## Volumes (apprentissage, 2026-09-26)

| Département | 75 | 92 | 94 | 93 | 78 | 91 | 77 | 95 | 45 | Total |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Offres | 844 | 512 | 257 | 215 | 201 | 196 | 191 | 151 | 106 | 2 673 |

## Structure d'une offre (champs utilisés)

`id`, `intitule`, `description`, `dateCreation`, `lieuTravail.{libelle, codePostal}`, `romeCode`, `entreprise.nom`, `natureContrat` (« Contrat apprentissage »), `codeNAF`, `origineOffre.urlOrigine`.

- `lieuTravail.libelle` = « 75 - Paris 12e Arrondissement » (préfixe département retiré à la normalisation) ; 252 offres sur 2 673 sans code postal.
- `codeNAF` absent sur 1 875 offres sur 2 673.

## Recoupement avec La Bonne Alternance

- Une offre FT relayée par LBA a le même identifiant : `France Travail|213JSYX` des deux côtés → la déduplication par identifiant les fusionne. La version FT directe est gardée (collectée en premier) : elle a le nom d'entreprise, souvent absent chez LBA.
- Même clé de contenu (titre normalisé + code postal) des deux côtés.

## Écoles et organismes de formation

Beaucoup d'offres FT sont publiées par des écoles qui recrutent des élèves :

- **ISCOD : 504 offres sur 2 673 (19 %)**, sans code NAF ;
- **360 offres en NAF 85 (enseignement)** : GROUPE IGF (191), ALL TECHNICS, E2M FORMATION, OPUS FORMATION…

Décision (école déjà trouvée) : exclusion par préfixe NAF `85` + liste noire par nom (`[filtres_ecoles]` de `search.toml`).

## Bruit spécifique rencontré

- `reseau` seul en mot-clé de titre : « réseaux sociaux », « Voiries et Réseaux Divers », « réseau ferroviaire », « réseaux électriques » → remplacé par `reseau informatique`, `reseaux informatiques`, `equipe reseau` + exclusions.
- `routage` en mot-clé de description : correspond au **routage postal** (imprimerie, mise sous plis) → remplacé par `routeur`, `protocoles de routage`, `commutation`.

## Sources

- [data.gouv — API Offres d'emploi](https://www.data.gouv.fr/dataservices/api-offres-demploi)
- [francetravail.io — API Offres d'emploi](https://francetravail.io/data/api/offres-emploi)
