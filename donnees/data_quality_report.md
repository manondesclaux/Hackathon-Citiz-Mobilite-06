# Rapport de qualité des données

*Généré le 20/10/2026 08:56.*

## 1. Stations Citiz

Fichier : `citiz_stations_2026-10-20.csv` — **1615 lignes** brutes, 15 réseaux régionaux.

- coordonnées manquantes ou hors France : **0**
- doublons de lieu (mêmes coordonnées à 10 m près, p. ex. Lyon présent dans deux flux) : **11** supprimés
- stations « Flex » (zone d'usage à part, non assimilables à une station classique) : **23** conservées, marquées `flex`
- stations sans véhicule rattaché : **96** conservées, marquées `sans_vehicule` (à exclure du comptage de flotte, utiles pour l'emprise)
- géocodage inverse : 1604 nouveaux points (API Géo)
- rattachement à une commune : 1604/1604 (échecs : 0)

**Résultat : 1604 stations, 2624 véhicules** → `data/clean/citiz_stations.csv` (11 lignes écartées au total).

## 2. Concurrents (Clem', Optymo, Leo&Go)

Fichier : `competitors_2026-10-20.csv` — **794 lignes** brutes.

- coordonnées aberrantes : **0**
- Clem' publie une station par place : 459 stations pour 325 sites distincts → **regroupées par site** (un site = plusieurs véhicules)
- Optymo : 31 stations sans véhicule disponible au moment du relevé (conservées, `n_vehicles = 0`)
- Leo&Go : véhicules en free-floating, **photo à un instant T** (pas une implantation fixe)
- géocodage inverse : 602 nouveaux points (API Géo)

**Résultat : 654 sites, 763 véhicules** → `data/clean/competitor_sites.csv`.

## 3. Getaround

Cache : `getaround_2026-10-19` — **1803/3753 flux** (48%), 110,678 lignes brutes.

- doublons entre flux voisins (un véhicule apparaît dans plusieurs villes) : **101,499** supprimés
- coordonnées aberrantes : **0**
- hors territoire (mer, pays frontaliers) : **0** écartés

**Résultat : 9,179 véhicules uniques** → `data/clean/getaround_vehicles.csv`. ⚠️ **Collecte partielle (48% des flux)** : les volumes Getaround sont des planchers.

## 4. Limites qui ne se corrigent pas par le nettoyage

- **Photo à un instant T** : aucune mesure d'usage (locations, taux d'occupation) dans les flux ouverts.
- **Opérateurs sans flux GBFS** (Modulauto, Zity, Free2Move, Ubeeqo, Marcel, Mobilize Share) : absents.
- **Getaround** : voitures de particuliers, pas comparables une à une à des véhicules Citiz.
- **Fichiers datés en double** (19 et 20 octobre) : seul le plus récent est utilisé ; les anciens sont conservés dans `data/raw/`.
