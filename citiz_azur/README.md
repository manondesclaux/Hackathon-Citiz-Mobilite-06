# Citiz — où ouvrir dans les Alpes-Maritimes ?

Un prototype Python/Jupyter exécutable, avec de vraies données ouvertes, une segmentation KMeans entraînée et une sélection de dix secteurs sous budget. **Le score est une règle de décision explicable. Ce n'est pas une prédiction de réservations ni de rentabilité.**

## Ouvrir le projet

Décompresser l'archive, ouvrir un terminal dans `citiz_azur`, puis :

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
jupyter lab Citiz_Cote_Azur.ipynb
```

Dans VS Code : ouvrir le même dossier, sélectionner le Python de `.venv`, puis ouvrir le notebook. Exécuter les cellules de haut en bas. Les CSV nécessaires sont inclus : aucun appel API requis pour reproduire les résultats. Le fond de carte et Leaflet nécessitent Internet.

Pour voir immédiatement les propositions, ouvrir `results/carte_top10.html` dans un navigateur. Les graphiques sont aussi dans le notebook exécuté. Pour relancer sans notebook : `python model.py`.

## Ce que fait le projet

1. Récupère les sources du PDF : catalogue transport.data.gouv.fr, GTFS, GBFS et carroyage INSEE Filosofi 2021.
2. Place des candidats au centre des carreaux habités de 200 m dans le département 06. Ce sont des **secteurs à étudier**, pas des places de stationnement déjà disponibles.
3. Exclut les centres à moins de 800 m d'un point Citiz publié, même si aucune voiture n'y est disponible à cet instant.
4. Compte dans un rayon de 400 m les habitants, les pôles d'arrêts et les offres concurrentes. Les habitants sont affectés au centre de leur carreau : approximation géographique, pas mesure porte-à-porte.
5. Entraîne KMeans sur population, transports et concurrence pour décrire les profils. Choisit le nombre de groupes entre 2 et 6 par silhouette. Un numéro de groupe n'est pas un niveau de qualité.
6. Calcule un score explicable : 60 % population nouvelle pour Citiz, 25 % proximité des transports (nombre de pôles), 15 % faible concurrence. Les poids sont des hypothèses à discuter. La demande réelle n'est pas observée.
7. Sélectionne jusqu'à dix secteurs : budget, espacement de 800 m, maximum deux secteurs par commune et gain marginal de population. Ce dernier évite le double compte d'un habitant couvert par plusieurs nouvelles stations.

**Périmètre : Alpes-Maritimes**, partie orientale de la Côte d'Azur. Le Var et Monaco ne font pas partie du classement. Ce choix est explicite pour limiter le périmètre du hackathon. Étendre au Var demande de modifier la collecte de population, les réseaux et les bornes dans `collect.py`, puis de reconstruire les données. Un simple changement de zoom ne suffit pas.

## Comprendre le score et le budget

`P = log(1 + population_nouvelle) / max(log(1 + population_nouvelle))`

`T = log(1 + nombre_arrets) / max(log(1 + nombre_arrets))`

`C = 1 / (1 + stations_concurrentes + 0.25 × vehicules_concurrents)`

`score = 100 × (0.60 P + 0.25 T + 0.15 C)`

Ce score est relatif aux candidats retenus, entre 0 et 100 ; 90/100 ne signifie pas 90 % de chances de réussite. Les voitures Getaround sont des observations mobiles, **pas des stations**. Leur coefficient 0.25 est une hypothèse, pas une conversion en parts de marché. Une station concurrente peut aussi signaler de la demande : tester les poids est indispensable.

À chaque choix, on maximise `score × population_encore_non_couverte / population_nouvelle / coût`. C'est une heuristique gloutonne, pas une garantie d'optimum global. Le rang de sélection peut donc différer du tri par score individuel. Le quota de deux par commune est une décision de diversification explicite, désactivable avec `max_per_commune=100`.

Le scénario par défaut prévoit **40 000 € d'investissement + 10 000 € de fonctionnement pour la première année par station**, budget total **500 000 €**. Ce sont exclusivement des hypothèses de démonstration, ni des devis Citiz ni des coûts issus d'une API. Elles n'intègrent pas de recettes. Modifier les valeurs dans `CONFIG` du notebook. Avec un coût identique partout, le budget fixe surtout le nombre de stations : il ne départage pas les lieux.

## Le vrai modèle supervisé, quand les données existent

Le fichier `supervised.py` contient une Random Forest pour prédire des **réservations par voiture et par mois**. Il n'a pas été entraîné avec des cibles inventées. Fournir `data/historique_usage.csv` avec les colonnes :

`station_id,commune,population_nouvelle,arrets_400m,stations_concurrentes_400m,vehicules_concurrents_400m,reservations_par_voiture_mois`

Une ligne agrégée par station, une fenêtre d'observation comparable et des variables connues avant cette fenêtre. La population autour d'une station existante doit être calculée avant son ouverture ou en retirant cette station de l'inventaire : sinon sa propre présence crée une fuite méthodologique. Prévoir au moins 30 stations et 5 communes (garde technique minimale, pas preuve de représentativité).

L'entraînement sépare les communes avec GroupKFold, mesure l'erreur absolue moyenne et compare à une prédiction constante. Un modèle qui ne bat pas cette référence n'est pas sauvegardé comme validé. Même s'il la bat, examiner le transfert vers la Côte d'Azur, la saisonnalité et l'écart entre territoires. Les prédictions sont présentées séparément et ne remplacent pas automatiquement le classement.

```python
from supervised import train_usage
modele, evaluation = train_usage('data/historique_usage.csv')
```

## Actualiser les API

```bash
python collect.py --refresh
python collect.py --population
python model.py
```

Sans `--refresh`, les caches sont réutilisés. L'archive livrée contient les données dérivées et le journal de collecte, mais pas les archives nationales volumineuses ni les caches. Le premier rafraîchissement retélécharge les sources. Les API peuvent changer et la collecte peut durer plusieurs minutes. Vérifier `data/collection_log.json` et les erreurs avant de relancer le modèle. Le notebook affiche ce contrôle.

`collect.py --population` télécharge la source INSEE nationale puis sélectionne les carreaux concernés. Un ZIP incomplet provoque une erreur ; il ne doit jamais être interprété comme une population nulle.

## Limites à expliquer à l'oral

- 400 m **à vol d'oiseau** sont un proxy d'environ cinq minutes de marche, pas une isochrone piétonne. Relief, autoroute, voie ferrée et accès fermés peuvent modifier fortement le résultat. Calculer des isochrones OSM sur les secteurs retenus avant une décision d'investissement.
- Population résidente Filosofi **2021**, pas population 2026 ni fréquentation touristique. Les carreaux imputés sont signalés ; les totaux peuvent être décimaux. Aucun calcul de rentabilité, de baisse de CO₂ ou de fréquentation réelle n'est revendiqué.
- Population des carreaux touchant le 06 ; le rattachement communal suit la première commune 06 présente dans la liste INSEE. Les carreaux à cheval sur une limite peuvent affecter le libellé communal et le quota. La population au-delà du département n'est pas additionnée.
- Les GTFS décrivent une offre théorique. On fusionne les coordonnées à moins de 30 m ; on ne compte ni les lignes ni les fréquences. Les calendriers d'activité ne sont pas filtrés : certains arrêts peuvent n'être desservis que certains jours. La proximité des transports est utilisée comme complémentarité avec l'autopartage.
- Citiz : flux régionaux présents dans le catalogue ; stations identifiées par leurs informations, pas par le nombre de voitures disponibles. Absence dans les flux n'est pas une certification d'absence terrain.
- Concurrence : Clem et Getaround collectés ; d'autres opérateurs, locations traditionnelles et offres non publiées peuvent manquer. Les résultats ne prouvent pas l'absence de concurrents. Getaround est dédupliqué par identifiant de véhicule entre flux communaux.
- Un stock GBFS ne mesure pas les réservations. Une voiture absente peut avoir été louée, déplacée ou retirée.
- Le modèle KMeans apprend des profils, mais le classement dépend des poids choisis. Il privilégie les zones denses ; une politique d'équité ou de service rural nécessite d'autres objectifs explicites.
- Le PDF demande un outil de prédiction et une optimisation. Ce prototype couvre la segmentation et l'optimisation exploratoire ; la prévision d'usage supervisée reste conditionnée aux historiques. Les projections démographiques et les distances piétonnes ne sont pas encore intégrées.

## Fichiers

- `Citiz_Cote_Azur.ipynb` : explications, code, graphiques, paramètres, résultats.
- `collect.py` : connecteurs et transformations.
- `model.py` : segmentation, score et sélection.
- `supervised.py` : entraînement sur usage réel lorsqu'il est disponible.
- `data/*.csv` : données traitées incluses pour rejouer l'analyse.
- `data/collection_log.json`, `data/provenance.json` : sources et contrôles.
- `results/top10.csv`, `results/candidats.csv` : classement et candidats.
- `results/carte_top10.html` : carte interactive.
- `results/segmentation.joblib` : modèle KMeans entraîné, à charger seulement depuis cette archive de confiance.
- `results/ml_metrics.json`, `results/sensibilite.csv` : qualité descriptive et sensibilité.
- `SOURCES.md` : sources, dates et rôle de chaque jeu.

## Contrôle particulier de la source population

Le téléchargement du ZIP INSEE a été interrompu après la partie sud du CSV. Avant utilisation, les 477 401 identifiants des carreaux nationaux au sud de N=2 400 000 (EPSG:3035) ont été comparés au fichier Parquet complet diffusé sur data.gouv.fr : aucun identifiant manquant et mêmes populations. Les 16 873 carreaux du périmètre étudié sont tous dans cet ensemble vérifié. Le détail est dans `data/population_verification.json`. Le ZIP incomplet n’est pas livré.
