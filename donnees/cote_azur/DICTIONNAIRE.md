# Secteur Côte d'Azur (Alpes-Maritimes, 06) : dictionnaire des données

Produit par `collecte/collect_cote_azur.py` (relevé en ligne + nettoyage). Le détail du dernier relevé est dans `RAPPORT_COLLECTE.md`.
**Périmètre** : les 163 communes du département des Alpes-Maritimes (06).

## Charger les données dans un notebook

```python
import pandas as pd
from pathlib import Path
CA = Path("donnees/cote_azur")              # depuis la racine du dépôt

communes   = pd.read_csv(CA / "communes_cote_azur.csv", dtype={"code": str})
vehicules  = pd.read_csv(CA / "concurrents_vehicules.csv", dtype={"commune_code": str})
stations   = pd.read_csv(CA / "concurrents_stations.csv", dtype={"commune_code": str})
operateurs = pd.read_csv(CA / "concurrents_operateurs.csv")
arrets     = pd.read_csv(CA / "arrets_transport.csv", dtype={"commune_code": str})
carreaux   = pd.read_csv(CA / "carreaux_200m_cote_azur.csv", dtype={"commune_code": str})
# contours des communes (pour une carte) : CA / "communes_cote_azur.geojson"
```

Tous les fichiers partagent la clé **`commune_code`** (code INSEE ; `code` dans `communes_cote_azur.csv`) et ont des coordonnées **`lat` / `lon`** en WGS84.

## 1. `concurrents_operateurs.csv` : qui sont les concurrents ?

Une ligne par opérateur, **y compris ceux sans flux ouvert, arrêtés ou absents** (sources en colonne `url`).

| Colonne | Description |
|---|---|
| `operateur`, `groupe` | Nom commercial et groupe propriétaire |
| `modele` | Type de service (autopartage en boucle, entre particuliers, free-floating…) |
| `statut` | actif, arrêté (avec date), absent, appel à opérateurs |
| `vehicules_releves_06` | Véhicules relevés dans le 06 au moment de la collecte (0 si pas de flux) |
| `source_flotte`, `precision`, `url` | D'où vient l'information, contexte chiffré, lien vers la source |

## 2. `concurrents_vehicules.csv` : où sont-ils ? (position exacte de chaque véhicule)

Une ligne par véhicule visible au moment du relevé (flux GBFS en temps réel).

| Colonne | Description |
|---|---|
| `operateur`, `service` | Getaround, Lime, Pony, Yego (Dott absent du 06 au relevé) |
| `categorie` | autopartage (Getaround) ou micromobilité en free-floating |
| `type_vehicule` | car, bicycle, moped (scooter), scooter_standing (trottinette) |
| `motorisation` | combustion, combustion_diesel, hybrid, electric, electric_assist, human (vide si non publié) |
| `modele` | Getaround : marque et modèle déduits de l'annonce (ex. « renault clio ») |
| `id`, `lat`, `lon` | Identifiant et position du véhicule |
| `reserve`, `indisponible` | État au moment du relevé |
| `commune_code`, `commune_nom` | Commune où se trouve le véhicule |
| `url` | Annonce Getaround |
| `source`, `date_releve` | Flux d'origine, date et heure du relevé |

⚠️ **Photo à un instant T** : un véhicule loué ou masqué n'apparaît pas. Pour Getaround, ce sont surtout des voitures de particuliers.

## 3. `concurrents_stations.csv` : implantations fixes

| Colonne | Description |
|---|---|
| `operateur`, `service`, `categorie` | Ici : **zones de stationnement recommandées** de Pony et Lime (473 + 2). Aucune station Citiz ni autre autopartage en station dans le 06 |
| `nom`, `lat`, `lon`, `capacite` | Nom, position, capacité si publiée |
| `commune_code`, `commune_nom` | Commune |

Les 38 anciennes stations Mobilize Share (arrêtées en juin 2026) n'ont pas de liste publique d'adresses ; les 86 bornes reprises par la Métropole sont dans le réseau public de recharge « Prise de Nice ».

## 4. `communes_cote_azur.csv` : population et activité du secteur

Une ligne par commune (163).

| Groupe | Colonnes | Source |
|---|---|---|
| Identité | `code`, `nom`, `codes_postaux`, `epci`, `lat_centre`, `lon_centre`, `surface_km2` | API Géo |
| Population | `pop`, `densite_hab_km2`, `p0_17`, `p18_26`, `p27_34`, `p35_44`, `p45_54`, `p55_64`, `p65_plus`, `p25_44` (effectifs) | INSEE recensement 2023 |
| Ménages | `menages`, `sans_voiture` (part), `menages_sans_voiture`, `part_locataires`, `part_appart` | INSEE logement 2022 |
| Activité | `emplois_au_lieu_de_travail`, `actifs_occupes_15_64`, `chomeurs_15_64`, `etudiants_15_64`, `retraites_15_64`, `ratio_emplois_actifs` (> 1 : pôle d'emploi qui attire des actifs) | INSEE emploi 2022 |
| Tourisme | `chambres_hotels`, `lits_hebergements_collectifs`, `emplacements_campings`, `lits_touristiques_marchands` (2 lits/chambre, 3/emplacement), `residences_secondaires`, `part_residences_secondaires`, `lits_touristiques_par_habitant` (marchands + 5 lits par résidence secondaire) | INSEE tourisme 2025, logement 2022 |
| Offre de mobilité | `veh_Getaround`, `veh_Lime`, `veh_Pony`, `veh_Yego`, `getaround_pour_10000_hab`, `zones_free_floating`, `stations_velos`, `citiz_vehicules`, `arrets_tc`, `gares` | relevés GBFS, GTFS |

## 5. `carreaux_200m_cote_azur.csv` : population fine (pour placer une station)

Une ligne par carreau habité de 200 m x 200 m (16 831 carreaux), INSEE Filosofi 2021.

| Colonne | Description |
|---|---|
| `idcar_200m`, `lat`, `lon` | Identifiant INSEE et centre du carreau |
| `i_est_200` | 1 = valeurs imputées (moins de 11 ménages) : à manier avec prudence |
| `ind`, `men` | Habitants, ménages |
| `ind_0_17`, `ind_18_24`, `ind_25_39`, `ind_40_54`, `ind_55_64`, `ind_65_plus` | Habitants par âge |
| `men_pauv`, `men_prop`, `men_coll`, `log_soc` | Ménages pauvres, propriétaires, en logement collectif ; logements sociaux |
| `niveau_vie_moyen` | Niveau de vie moyen par habitant (€/an) |
| `commune_code`, `commune_nom` | Commune principale du carreau |

## 6. `arrets_transport.csv` : transports en commun

6 022 arrêts uniques (bus, tram, car, train), dédoublonnés à partir de l'agrégat national GTFS (janvier 2026). `mode` = « train » pour les 44 arrêts ferroviaires.

## Sources

- Flux GBFS : [transport.data.gouv.fr](https://transport.data.gouv.fr/datasets?type=vehicles-sharing) (Getaround, Lime Nice et CASA, Pony Nice, Yego Nice, Dott)
- Arrêts : [Arrêts de transport en France](https://www.data.gouv.fr/datasets/arrets-de-transport-en-france)
- INSEE : [population 2023](https://www.insee.fr/fr/statistiques/9006235), [logement 2022](https://www.insee.fr/fr/statistiques/8581474), [emploi 2022](https://www.insee.fr/fr/statistiques/8581444), [capacité touristique 2025](https://www.insee.fr/fr/statistiques/2021703), [carreaux 200 m Filosofi 2021](https://www.insee.fr/fr/statistiques/8735162)
- Contours et intercommunalités : [API Géo](https://geo.api.gouv.fr)
- Opérateurs sans flux : presse et sites des collectivités (liens dans `concurrents_operateurs.csv`)
