# Trame de soutenance (10 minutes + démo)

Chaque diapositive : un message, un chiffre, une source. Les chiffres viennent de `decision/resultats/`. Les relire
après chaque exécution de `decision/run_all.sh`.

## 1. Le problème
Citiz est absent des Alpes-Maritimes (1,1 million d'habitants). Deux opérateurs y ont déjà arrêté : Auto Bleue en
2018, Mobilize Share en 2026. Question : **où ouvrir, pour qui, à quel coût, sans répéter ces échecs ?**

## 2. Notre réponse en une phrase
21 stations et 42 véhicules (2 par station) pour 491 k€ la première année, d'abord à Nice. Environ 81 000 habitants
nouvellement à 5 minutes à pied d'une voiture partagée (réseau piéton OSM ; 176 000 à vol d'oiseau).

## 3. Objectif 1 : qui a accès à quoi aujourd'hui (carte, couche 1)
- 8,7 % des habitants n'ont aucun arrêt de transport actif à 400 m.
- Le service TC est correct ou fort pour 91 % des quartiers modestes, contre 56 % des plus aisés. Les plus aisés
  vivent dans des quartiers moins denses.
- Vocabulaire : « accès plus limité », jamais « quartier mal desservi ».

## 4. Objectif 2 : qui chaque point d'accès dessert (carte, couche 2)
Habitants à 400 m de chacun des 5 830 pôles d'arrêts, des 475 zones free-floating et des 250 voitures Getaround.

## 5. La donnée d'usage, collectée dans Microsoft Fabric
- Un notebook Fabric relève les 2 632 véhicules Citiz toutes les 15 minutes (table Delta).
- Le profil horaire est crédible : 21 % de véhicules réservés la nuit, 42 % entre 10 h et 14 h.
- **Constat honnête** : avec moins d'une journée de relevés, l'occupation d'une station n'est pas prévisible mieux
  qu'une moyenne (gain de 1,7 %, R² ≈ 0). L'ancien modèle de l'équipe ne faisait pas mieux. On l'a abandonné.

## 6. Le modèle qui tient : potentiel d'implantation
- Appris sur 20 ans de choix de Citiz : 1 427 carreaux avec station, 40 000 sans, 15 réseaux.
- **AUC 0,92** en prédisant chaque réseau sans l'avoir vu (contre 0,86 pour la densité seule).
- **Relié à l'usage réel** : 16 % d'occupation dans le quintile de potentiel le plus faible, contre 24 % dans le
  plus fort (Fabric, intervalles disjoints).
- Ce qui compte : ménages d'une personne, densité, logement collectif, locataires, desserte TC.

## 7. Objectif 3 : la liste sous budget (carte, couche 3)
- Méthode : glouton sur « habitants nouveaux × potentiel / coût ». Un habitant ne compte qu'une fois. 800 m entre
  deux stations, plafond par commune, quota d'équité.
- Trois vagues de 7 stations : centre de Nice ; puis Nice, Cagnes-sur-Mer, Antibes et Cannes ; puis Nice, Antibes,
  Menton et Grasse.
- Distances à pied (OSM) : 46 % des habitants comptés à vol d'oiseau sont réellement à 5 minutes. Costabella,
  Mirasol / Pessicart et Carlone tombent à 11-29 % : ce sont les premiers à revoir.
- Flotte (slide 18) : 2 citadines hybrides par station, comme 77 % des stations Citiz à Marseille et 84 % à Toulouse.
  Rupture mesurée dans Fabric : 21 % du temps à 1 véhicule, 5,7 % à 2, 3,7 % à 3. Le 3e véhicule seulement après
  rupture observée. Électrique en test près des bornes ex-Mobilize ; pas de grand volume au lancement.
- Pour l'autorité organisatrice : 10 arrêts de bus (142 k€ ; 9 000 habitants à vol d'oiseau, environ 2 800 à pied)
  et 9 stations vélo à Nice (281 k€/an ; 100 600 habitants à vol d'oiseau, 40 300 à pied).

## 8. Ce que cela rapporte à Citiz
- Pas de résultat chiffré : sans les réservations et recettes par station, il n'est pas prédictible (de −93 k€ à
  +164 k€ par an selon les hypothèses).
- Le seuil de rentabilité : une station est à l'équilibre à **21 % d'occupation**, la moyenne actuelle du réseau
  (8 700 € de charges par véhicule et par an). À 15 % si la Métropole offre le stationnement, à 26 % avec des coûts
  hauts. Nos sites ressemblent à vos stations qui atteignent ce niveau ailleurs.
- Sensibilité : seuls 15 sites sur 21 seraient retenus avec la population seule. Le modèle change donc réellement la
  décision.
- Pourquoi Citiz réussirait là où d'autres ont échoué : modèle coopératif en boucle, flotte hybride, quartiers
  denses et peu motorisés plutôt que toute la métropole.

## 9. Éthique et société
- **Carbone** : 140 à 360 t de CO₂ évitées par an (ordre de grandeur, hypothèses 6t-ADEME).
- **Équité** : 67 % des stations dans les quartiers des 40 % d'habitants les plus modestes. Le quota de 30 % est
  dépassé sans contrainte.
- **Risque de « servir les déjà servis »** : assumé pour Citiz (la densité est la condition de survie, comme
  l'ont montré les échecs). Pour le transport public, les arrêts de bus proposés ciblent au contraire les zones
  périurbaines sans arrêt.
- **Vie privée** : aucune population affichée pour les carreaux imputés par l'INSEE (moins de 11 ménages).

## 10. Limites et suite
- Relevés Fabric à prolonger 4 à 8 semaines, week-ends et été compris, puis réentraîner le modèle d'usage
  (`decision/03_modele_usage.py`, prêt).
- 9 sites sur 21 sont hors du domaine d'apprentissage (densité record, tourisme ou desserte inhabituelle) : à
  valider sur le terrain.
- Coûts à remplacer par ceux de Citiz et de la Métropole (`decision/parametres.json`).
- Extension au Var et à Monaco : changer `DEP` et relancer.

## Démo (2 minutes)
1. Ouvrir `decision/resultats/carte_decision_06.html`.
2. Couche 1 : montrer le contraste entre le centre de Nice et l'arrière-pays.
3. Couche 3 : cliquer sur la station n° 1, puis lire le potentiel et l'intervalle d'occupation, à comparer au seuil
   de 21 %.
4. Modifier `budget_annee1_eur` dans `parametres.json`, relancer `07_optimisation.py` puis `09_carte.py`, et
   recharger la carte.
