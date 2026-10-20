# Sources et traçabilité

## Sources du sujet

- Sujet fourni : `hackathon_mobility-project(6).pdf`, version 0.4.0. Objectif principal : décision d’implantation, prédiction et optimisation sous budget.
- Catalogue public PAN : https://transport.data.gouv.fr/api/datasets ; documentation https://doc.transport.data.gouv.fr/outils/outils-disponibles-sur-le-pan/api
- INSEE Filosofi 2021, carreaux 200 m : https://www.insee.fr/fr/statistiques/8735162 ; publication du 12 février 2026, population de référence 2021.
- INSEE, projections Omphale : https://www.insee.fr/fr/statistiques/6652134 — identifiée, non utilisée dans cette version.
- IGN : https://geoservices.ign.fr/adminexpress — identifiée, non utilisée dans cette version.
- Réseau piéton OSM : https://download.geofabrik.de/europe/france.html — identifié, non utilisé pour les distances de cette version.
- Catalogue GBFS mondial : https://github.com/MobilityData/gbfs/blob/master/systems.csv — consulté ; la collecte opérationnelle utilise le catalogue PAN.

## Sources réellement exploitées

- Carroyage Filosofi INSEE 2021, identifiant EPSG:3035. Transformation des centres de carreaux en latitude/longitude avec pyproj, ajout de 100 m aux coordonnées N/E du coin sud-ouest.
- Diffusion Parquet sur data.gouv.fr du même millésime pour contrôle de complétude et reprise après interruption du ZIP national : https://www.data.gouv.fr/datasets/revenus-pauvrete-et-niveau-de-vie-donnees-carroyees-2019-et-2021-dispositif-fichier-localise-social-et-fiscal-filosofi
- Noms des communes : https://geo.api.gouv.fr/departements/06/communes?fields=nom,code&format=json
- GTFS : réseaux urbains Lignes d’Azur, Envibus, Palmbus, Sillages, Zest ; ZOU Proximité et Express, trains régionaux ZOU et Transdev Rail Sud Intermétropole. Les URL des ressources effectivement téléchargées figurent dans `data/collection_log.json`.
- GBFS : tous les flux Citiz régionaux identifiés par leur titre dans le catalogue PAN, plus Clem. Stations fixes issues de `station_information` ; une disponibilité nulle ne supprime pas la station.
- Getaround : https://fr.getaround.com/gbfs/manifest?country_code=FR ; sélection des jeux communaux du département 06 par correspondance de nom normalisé ; véhicules non rattachés à une station issus de `vehicle_status` ; déduplication par identifiant. Tous les opérateurs possibles ne sont pas couverts.
- Les trois cartes HTML fournies ont été inspectées : elles permettent de constater que la population initialement affichée était filtrée. Elles ne servent pas à créer les valeurs de population ou à entraîner le modèle.

Les données sont des instantanés : conserver la date, le journal et les CSV pour une soutenance reproductible. Les empreintes SHA-256 et versions des bibliothèques sont dans `data/provenance.json`. Les grands fichiers sources ne sont pas inclus dans l’archive livrée. Consulter les licences de chaque jeu source avant une redistribution élargie ; leur mention figure dans le catalogue PAN conservé.

## Références techniques

- GTFS : https://gtfs.org/documentation/schedule/reference/
- GBFS 3.0 : https://gbfs.org/documentation/reference/ — décrit l’offre à l’instant considéré, pas un historique de locations.
- KMeans : https://scikit-learn.org/stable/modules/generated/sklearn.cluster.KMeans.html
- GroupKFold : https://scikit-learn.org/stable/modules/generated/sklearn.model_selection.GroupKFold.html
- RandomForestRegressor : https://scikit-learn.org/stable/modules/generated/sklearn.ensemble.RandomForestRegressor.html

## Décisions méthodologiques

Distances haversine en mètres ; aucune distance euclidienne calculée directement en degrés. Rayon 400 m à vol d’oiseau, exclusion Citiz 800 m, espacement 800 m. Les frontières de communes ne contraignent pas les rayons de couverture, mais la population hors département n'est pas incluse. L’addition est faite sur des carreaux uniques, jamais sur des populations communales répliquées à chaque point.

Les coûts, poids et quota communal sont des **hypothèses utilisateur**, pas des données collectées. KMeans est évalué descriptivement par silhouette. Aucune métrique de fréquentation prédictive n’est publiée en l’absence de cible historique.
