# Pipeline de décision : où ajouter de la mobilité partagée dans les Alpes-Maritimes ?

Ce dossier est **la référence** pour les trois objectifs du sujet. Il remplace, pour la recommandation finale, les
classements exploratoires de l'équipe (`vingt_stations_azur` et `citiz_azur/top10`, gardés dans `donnees/anciens_classements/`).
Il les reprend et les corrige : modèle validé hors échantillon, coûts différenciés, budget, équité, distances à pied.

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
./decision/run_all.sh            # ~5 min hors téléchargements ; résultats dans decision/resultats/
open decision/resultats/carte_decision_06.html
```

Prérequis non versionnés (trop volumineux) : `data_insee/carreaux_200m_2021.zip`
([INSEE Filosofi 2021, carreaux 200 m](https://www.insee.fr/fr/statistiques/8735162)) et
`data_insee/logement_2022.zip` ([INSEE, logement 2022, base communale](https://www.insee.fr/fr/statistiques/8581474)).
Les GTFS du 06, les projections Omphale et le réseau OSM sont téléchargés automatiquement dans `data/raw/`.

## Les étapes

| Étape | Script | Ce qu'elle fait | Sortie principale |
|---|---|---|---|
| 0 | `00_frequences_gtfs.py` | Passages par jour ouvré de chaque arrêt (10 flux GTFS du 06), pôles à 30 m | `donnees/poles_arrets_06.csv` |
| 1 | `01_cible_usage.py` | Occupation des stations Citiz d'après les relevés Fabric, nettoyée | `donnees/usage_stations.csv`, `resultats/qualite_cible.json` |
| 2 | `02_variables.py` | **Mêmes** variables pour les 1 402 stations Citiz (apprentissage) et les 16 831 carreaux du 06 (prédiction) | `donnees/variables_stations.csv`, `donnees/candidats_06.csv.gz` |
| 3 | `03_modele_usage.py` | Peut-on prédire l'occupation à court terme ? Validation par réseau laissé de côté | `resultats/modele_usage.json` |
| 4 | `04_modele_implantation.py` | Modèle de potentiel d'implantation, validé hors échantillon et contre l'usage observé | `resultats/modele_implantation.json` |
| 5 | `05_accessibilite_06.py` | Objectifs 1 et 2 : options à 5 min par habitant, habitants desservis par chaque point d'accès | `resultats/population_par_point_acces_06.csv`, `resultats/equite_acces_06.json` |
| 6 | `06_projections.py` | Projections INSEE Omphale (2030-2040, trois scénarios) | `resultats/projections_06.csv` |
| 6b | `06b_flotte.py` | Nombre et type de véhicules par station : pratique Citiz, ruptures mesurées dans Fabric, occupation par type à lieu égal | `resultats/flotte_analyse.json`, `resultats/flotte_types.csv` |
| 7 | `07_optimisation.py` | Objectif 3 : listes priorisées sous budget (Citiz, arrêts de bus, stations vélo), sensibilité | `resultats/stations_citiz_recommandees.csv`, `resultats/synthese_decision.json` |
| 8 | `08_isochrones.py` | Habitants à 400 m **à pied** sur le réseau OSM, pour chaque site retenu | `resultats/isochrones_sites.csv` |
| 9 | `09_carte.py` | Carte unique de démonstration (3 objectifs, couches activables) | `resultats/carte_decision_06.html` |

Toutes les hypothèses chiffrées (coûts, budgets, carbone, quota d'équité) sont dans `parametres.json`, avec une
fourchette, une source et une fiabilité. On les modifie là, puis on relance `07_optimisation.py`.

## Résultats et ce qu'ils valent

### Le modèle d'usage à court terme n'est pas validé, et nous le disons

L'occupation observée (relevés Fabric du 19 au 20/10, moins d'une journée) n'est **pas prévisible** mieux qu'une
moyenne : gain de MAE de 1,7 % (IC 90 % : 0,8 à 3,2 %), R² hors échantillon ≈ 0. L'ancien modèle de l'équipe
(population + motorisation communale, R² = 0,03 mesuré sur ses propres données) ne fait pas mieux.
La règle fixée avant le calcul (gain ≥ 3 % et rang positif dans ≥ 70 % des réseaux) n'est pas remplie : ce modèle
ne sert donc pas à classer. Cause principale : la fenêtre de mesure. Il faut **plusieurs semaines** de relevés.

### Le modèle de potentiel d'implantation est validé

Question posée : « ce carreau ressemble-t-il aux lieux où Citiz tient une station depuis des années ? ».
- 1 427 carreaux avec station et 40 000 sans, dans 303 communes et 15 réseaux.
- **AUC 0,92 hors échantillon**, en prédisant chaque réseau sans l'avoir vu (contre 0,86 pour la densité seule).
  71 % des stations tombent dans les 10 % de carreaux les mieux notés de leur réseau.
- **Validation externe par l'usage** : aux stations existantes, le potentiel prédit hors échantillon est lié à
  l'occupation observée dans Fabric (Spearman 0,17, p < 10⁻⁹). Occupation de 16 % dans le quintile le plus faible
  contre 23-24 % dans les deux plus forts, avec des intervalles qui ne se recouvrent pas.
- Variables qui comptent : ménages d'une personne, densité à 400 m, logement collectif, faible part de propriétaires,
  desserte TC, motorisation de la commune.

### Recommandation Citiz (budget de 500 k€ la première année)

21 stations, 42 véhicules (491 k€ la première année), environ 176 000 habitants nouvellement desservis à 400 m à
vol d'oiseau, soit **environ 81 000 à 5 minutes à pied** sur le réseau OSM (46 %). Trois sites ne touchent à pied que
11 à 29 % des habitants comptés à vol d'oiseau (Costabella, Mirasol / Pessicart, Carlone) : ils sont à revoir en
priorité. Les stations sont en majorité à Nice (15), avec Antibes (2), Cagnes-sur-Mer, Cannes, Menton et Grasse.

**Flotte** (`06b_flotte.py`) : **2 véhicules par station au lancement**, un 3e seulement si la station est
entièrement réservée plus de 15 % du temps de journée pendant 2 semaines. C'est la pratique de Citiz dans les grandes
villes du Sud (77 % des stations à 2 véhicules à Marseille, 84 % à Toulouse). Dans Fabric, une station est
entièrement réservée 21 % du temps avec 1 véhicule, 5,7 % avec 2 et 3,7 % avec 3 : le 3e véhicule apporte peu.
Type : **2 citadines hybrides** (catégorie Toyota Yaris / Renault Clio hybride, les modèles les plus courants de la
flotte). À lieu égal, les citadines sont réservées 3,7 points de plus que la moyenne de leur station, les hybrides
2,5 points de plus (l'âge des véhicules, non publié, peut en expliquer une part). Électrique : à tester dans 1 ou 2
stations proches de bornes publiques, l'écart n'étant pas significatif. Grand volume : pas au lancement (−5,1 points
en semaine, week-end non mesuré). La règle de l'équipe (3 véhicules au-delà de 9 000 habitants) est abandonnée : elle
ne correspondait pas à la pratique de Citiz et reposait sur des taux de rupture mal lus.
**Rentabilité : un seuil, pas une prédiction.** Sans les recettes ni les réservations par station, le résultat
d'exploitation n'est pas prédictible : selon les coûts et l'occupation retenus (`parametres.json`), il va de −93 k€ à
+164 k€ par an pour les 42 véhicules. L'information utile est le seuil : avec 8 700 € de charges par véhicule et
par an (central), une station est à l'équilibre à **21 % d'occupation**, la moyenne actuelle du réseau Citiz ; à
15 % si la Métropole offre le stationnement (6 000 €), à 26 % avec des coûts hauts (10 500 €).
De 140 à 360 t de CO₂ évitées par an (ordre de grandeur). 67 % des stations sont dans les quartiers des 40 %
d'habitants les plus modestes.

**Sensibilité** (`resultats/sensibilite_citiz.csv`) : avec l'ancien critère « population seule », seuls 15 des 21
sites sont communs. Le potentiel change donc réellement la décision, en échange d'environ 4 % d'habitants desservis
en moins. Doubler le budget garde les 21 premiers sites.

### Arrêts de bus et stations vélo

- **Arrêts de bus** : 10 arrêts sur des lignes existantes (142 k€), environ 9 000 habitants qui gagnent un arrêt
  actif à 400 m à vol d'oiseau, environ 2 800 à pied (valeur pessimiste : le point testé est le centre d'un carreau
  périurbain, pas un arrêt placé sur la ligne). Le reste des 97 000 habitants sans arrêt actif vit trop loin d'une
  ligne : il faudrait une nouvelle ligne, ce qui est hors périmètre.
- **Stations vélo** : 9 stations en réseau dans le centre de Nice, rabattues sur les pôles les plus desservis
  (281 k€/an), environ 100 600 habitants à 400 m à vol d'oiseau, 40 300 à pied. Le 06 n'a plus de vélos en libre-service en station, seulement du free-floating.

### Accès aujourd'hui (objectifs 1 et 2)

8,7 % des habitants du 06 n'ont aucun arrêt actif à 400 m. Le niveau de service décroît avec le niveau de vie du
quartier : 91 % des quartiers modestes ont un service TC correct ou fort, contre 56 % des plus aisés, qui sont moins
denses et plus motorisés. L'enjeu d'équité principal est donc la densité, pas le revenu.

## Limites qui restent

- **Usage** : moins d'une journée de relevés, sans week-end ni saison touristique ; `is_reserved` n'est pas un trajet.
  Le potentiel décrit où Citiz réussit à s'implanter, pas un nombre de locations.
- **Extrapolation** : 9 des 21 stations sont hors du domaine d'apprentissage. Quatre sites niçois sont plus denses que
  toutes les stations Citiz existantes, quatre sites de Cannes, Antibes et Menton ont plus de résidences
  secondaires, et le site de Grasse a une desserte inhabituelle. Ils sont signalés dans la carte et le CSV.
- **Biais du modèle** : il apprend aussi les contraintes de Citiz (stationnement, partenariats). Les stations fermées
  ne sont pas observées.
- **Coûts et recettes** : fiabilité faible à moyenne (`parametres.json`), à remplacer par les chiffres réels de Citiz
  et de l'autorité organisatrice. La recette de 8 700 € par véhicule est une moyenne nationale d'un réseau mûr : elle
  ignore la montée en charge d'une nouvelle station et la durée réelle des locations. Les colonnes `resultat_eur_an_*`
  de `stations_citiz_recommandees.csv` ne font varier que l'occupation, à coûts centraux : ce ne sont pas des
  prévisions.
- **Carbone** : ordre de grandeur fondé sur les enquêtes 6t-ADEME, pas une mesure.
- **Distances à pied** : calculées sur les sites retenus seulement, pas sur tous les candidats ; le classement
  repose encore sur le vol d'oiseau. Pour les arrêts de bus, le point testé est le centre d'un carreau périurbain,
  souvent loin de la route : la valeur à pied (≈ 2 800 habitants) est pessimiste, il faut placer l'arrêt sur la ligne.
- **Population** : résidents Filosofi 2021. Le tourisme n'entre que par la part de résidences secondaires de la
  commune. Les projections Omphale ne changent que les volumes (−3 % pour la cible 25-54 ans en 2035, scénario
  central), pas le classement.
- **Périmètre** : Alpes-Maritimes, choisi parce que Citiz y est absent alors que les échecs passés (Auto Bleue,
  Mobilize Share) montrent qu'une demande existe. Les DROM ne sont pas traités.
