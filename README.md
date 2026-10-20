# Hackathon Mobilité × Citiz : où ajouter de la mobilité partagée ?

Outil d'aide à la décision construit sur des données ouvertes (GTFS, GBFS, INSEE, OSM) et sur des relevés d'usage
Citiz collectés dans **Microsoft Fabric**. Territoire d'application : **Alpes-Maritimes**, où Citiz est absent alors
que deux opérateurs y ont déjà échoué (Auto Bleue, Mobilize Share).

**Démo** : ouvrir `decision/resultats/carte_decision_06.html` dans un navigateur.

## Réponse aux trois objectifs du sujet

| Objectif | Où | En bref |
|---|---|---|
| 1. Carte de l'accès à la mobilité | `decision/05_accessibilite_06.py`, couche 1 de la carte | Options à 5 min de marche pour 1 000 habitants, du plus froid au plus chaud ; passages TC par jour (GTFS) |
| 2. Qui est concerné | `decision/resultats/population_par_point_acces_06.csv`, couche 2 | Habitants à 400 m de chaque arrêt, gare, zone free-floating, véhicule partagé |
| 3. Où s'implanter, à quel coût | `decision/07_optimisation.py`, couche 3 | 21 stations Citiz à 2 véhicules (491 k€), 10 arrêts de bus (142 k€), 9 stations vélo (281 k€/an), sous budget |

La méthode, les résultats chiffrés et les limites sont détaillés dans **[decision/README.md](decision/README.md)**.

## Installation

```bash
python3 -m venv .venv
source .venv/bin/activate          # Windows : .venv\Scripts\activate
pip install -r requirements.txt
./decision/run_all.sh
```

Données nationales à placer dans `data_insee/` (non versionnées, voir `decision/README.md`).

## Organisation du dépôt

| Dossier | Rôle |
|---|---|
| `decision/` | **Pipeline de référence** : cible d'usage, modèles validés, objectifs 1-2-3, carte finale |
| `fabric/`, `releves_fabric/` | Collecte toutes les 15 min des flux Citiz dans Microsoft Fabric (Lakehouse, Delta) et relevés exportés |
| `citiz_azur/` | Premier prototype autonome (score explicable, KMeans, top 10) ; garde son propre README |
| `scripts/` | Collecte, nettoyage et analyses exploratoires (France entière, âges, motorisation, concurrence) |
| `DATA clean/` | Données nettoyées (Citiz, concurrents, communes, secteur Côte d'Azur, arrêts et stations vélo nationaux) |
| `sorties/` | Cartes et tableaux des analyses exploratoires |
| `01_*.ipynb`, `02_*.ipynb` | Notebooks d'analyse de marché (implantation, concurrence, démographie du Sud) |
| `SOURCES.md` | Liste des sources utilisées, licences, dates |

Les scripts `scripts/vingt_stations_azur.py`, `ordre_installation.py` et `flotte_recommandee.py` sont conservés pour
l'historique. Leur modèle d'usage (R² = 0,03, sans validation) ne permet pas de distinguer les sites ; la
recommandation de référence est celle de `decision/`.

## Pourquoi Microsoft Fabric, et pourquoi Python en local

Fabric sert à ce qu'il fait de mieux ici : une collecte planifiée et durable (notebook Python toutes les 15 min,
table Delta dans un Lakehouse). C'est la seule source d'usage réel du projet, et elle doit continuer à tourner
plusieurs semaines. Les modèles et l'optimisation tournent en Python local (scikit-learn, osmnx), parce qu'ils doivent
être rejoués à l'identique par le jury et par Citiz, sans compte Fabric. Le code ne dépend pas de l'environnement :
`decision/` peut être exécuté tel quel dans un notebook Fabric.
