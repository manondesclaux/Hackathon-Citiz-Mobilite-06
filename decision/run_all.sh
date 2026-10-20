#!/usr/bin/env bash
# Rejoue tout le pipeline de décision, de la cible d'usage à la carte finale (~5 min, hors téléchargements).
# Prérequis : data_insee/carreaux_200m_2021.zip et data_insee/logement_2022.zip (voir decision/README.md).
set -euo pipefail
cd "$(dirname "$0")"
PY="${PYTHON:-../.venv/bin/python}"
for etape in 00_frequences_gtfs 01_cible_usage 02_variables 03_modele_usage 04_modele_implantation \
             05_accessibilite_06 06_projections 06b_flotte 07_optimisation 08_isochrones 09_carte; do
  echo "=== $etape"
  "$PY" -W ignore "$etape.py"
done
