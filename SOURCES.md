# Sources de données

Toutes les sources sont publiques, sauf mention contraire. Les dates sont celles de la collecte ou du millésime.

## Population et territoire

| Source | Millésime | Usage | Licence |
|---|---|---|---|
| [INSEE Filosofi, carreaux de 200 m](https://www.insee.fr/fr/statistiques/8735162) | 2021 (publié en 2026) | Population, âges, ménages, niveau de vie au carreau | Licence Ouverte |
| [INSEE, projections Omphale 2022](https://www.insee.fr/fr/statistiques/6652134) | 2018-2070 | Population et structure par âge du 06 en 2030-2040 (3 scénarios) | Licence Ouverte |
| [INSEE, logement 2022, base communale](https://www.insee.fr/fr/statistiques/8581474) | 2022 | Résidences secondaires (tourisme) | Licence Ouverte |
| [INSEE, logement 2021, base infracommunale](https://www.insee.fr/fr/statistiques/8268838) | 2021 | Ménages sans voiture par commune | Licence Ouverte |
| [INSEE, population par âge 2023](https://www.insee.fr/fr/statistiques/9006235) | 2023 | Démographie des villes du Sud (notebooks) | Licence Ouverte |
| [INSEE, emploi 2022](https://www.insee.fr/fr/statistiques) et capacité d'hébergement 2025 | 2022, 2025 | Profil des communes du 06 | Licence Ouverte |
| [API Géo](https://geo.api.gouv.fr) (etalab) | 2026 | Communes, contours, intercommunalités | Licence Ouverte |
| [france-geojson](https://github.com/gregoiredavid/france-geojson) (dérivé d'IGN Admin Express) | — | Contours des départements | Licence Ouverte |
| [OpenStreetMap](https://www.openstreetmap.org) via osmnx | octobre 2026 | Réseau piéton, distances à pied | ODbL |

## Offre de mobilité

| Source | Date | Usage |
|---|---|---|
| [Arrêts de transport en France](https://www.data.gouv.fr/datasets/arrets-de-transport-en-france) (agrégat GTFS national) | export du 13/01/2026 | Arrêts et gares, France métropolitaine |
| GTFS du 06 via [transport.data.gouv.fr](https://transport.data.gouv.fr/datasets?type=public-transit) : Lignes d'Azur, Envibus, Palmbus, Sillages, Zest, ZOU Express et Proximité, trains régionaux ZOU | octobre 2026 | Passages par jour ouvré à chaque arrêt |
| GBFS Citiz (15 réseaux régionaux) via [transport.data.gouv.fr](https://transport.data.gouv.fr/datasets?type=vehicles-sharing&q=citiz) | 19-20/10/2026 | Stations et véhicules Citiz |
| Relevés `vehicle_status` Citiz toutes les 15 min, collectés dans **Microsoft Fabric** | 19/10 14 h 30 au 20/10 12 h 40 (UTC) | Occupation des stations (proxy d'usage) |
| GBFS Clem', Optymo, Leo&Go, Rémi+, Communauto | 19-20/10/2026 | Concurrence en autopartage |
| [GBFS Getaround](https://fr.getaround.com/gbfs/manifest?country_code=FR) | 19-20/10/2026 | Voitures partagées entre particuliers |
| GBFS Lime, Pony, Yego, Dott | 20/10/2026 | Free-floating dans le 06 |
| GBFS des vélos en libre-service (catalogue PAN) | 20/10/2026 | Stations VLS nationales (zones free-floating écartées) |

Chaque jeu de données du catalogue PAN a sa propre licence (le plus souvent Licence Ouverte ou ODbL) : voir la fiche
du jeu avant toute redistribution.

## Hypothèses économiques et carbone

Toutes les valeurs, fourchettes et fiabilités sont dans [decision/parametres.json](decision/parametres.json). Les
principales sources :
- chiffre d'affaires Citiz du 1er semestre 2024 : [Le Journal des Entreprises](https://www.lejournaldesentreprises.com/article/la-cooperative-dautopartage-citiz-affiche-une-forte-croissance-au-premier-semestre-2024-2104866) ;
- coût d'un vélo en libre-service : enquête GART citée par la [Banque des Territoires](https://www.banquedesterritoires.fr/velos-en-libre-service-un-bilan-coutsavantages-juge-globalement-equilibre) ;
- places d'autopartage : [Que Choisir](https://www.quechoisir.org/actualite-autopartage-a-paris-des-solutions-subsistent-n167464/) ;
- arrêts de bus : tableaux de bord communaux belges (aucun barème français public trouvé) ;
- effets de l'autopartage : Enquête nationale sur l'autopartage, 6t-bureau de recherche pour l'ADEME ;
- facteurs d'émission : ADEME, Base Empreinte.

## Contexte de marché

Presse économique et institutionnelle sur Auto Bleue, Mobilize Share, Getaround et la Métropole Nice Côte d'Azur,
Modulauto : liens dans les notebooks d'analyse de marché (retirés du dépôt, disponibles dans l'historique Git).
