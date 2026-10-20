"""Option supervisée à activer seulement avec des usages Citiz réellement observés."""
from pathlib import Path
import numpy as np
import pandas as pd
import joblib
from sklearn.ensemble import RandomForestRegressor
from sklearn.dummy import DummyRegressor
from sklearn.model_selection import GroupKFold
from sklearn.metrics import mean_absolute_error

FEATURES=['population_nouvelle','arrets_400m','stations_concurrentes_400m','vehicules_concurrents_400m']
TARGET='reservations_par_voiture_mois'

def train_usage(csv_path,output_dir='results'):
    """Une ligne par station ; même fenêtre d'observation, features connues avant celle-ci.
    Pour les stations existantes, population_nouvelle doit être calculée AVANT son
    ouverture (ou après retrait de cette station de l'inventaire) : sinon fuite de cible.
    Les caractéristiques doivent provenir du même protocole géographique que model.py.
    """
    d=pd.read_csv(csv_path)
    required=['station_id','commune',TARGET]+FEATURES
    if not set(required).issubset(d):raise ValueError(f'Colonnes nécessaires : {required}')
    if d[required].isna().any().any():raise ValueError('Valeurs manquantes : corriger les données historiques')
    if d.station_id.duplicated().any():raise ValueError('Une seule observation agrégée par station attendue')
    if len(d)<30 or d.commune.nunique()<5:raise ValueError('Prévoir au moins 30 stations dans 5 communes ; davantage est préférable')
    if (d[FEATURES+[TARGET]]<0).any().any():raise ValueError('Valeurs négatives')
    folds=GroupKFold(n_splits=5); rows=[]; preds=np.zeros(len(d));base=np.zeros(len(d))
    for fold,(tr,te) in enumerate(folds.split(d[FEATURES],d[TARGET],d.commune),1):
        m=RandomForestRegressor(n_estimators=300,min_samples_leaf=5,max_depth=12,random_state=42,n_jobs=-1)
        m.fit(d.iloc[tr][FEATURES],d.iloc[tr][TARGET]);preds[te]=m.predict(d.iloc[te][FEATURES])
        b=DummyRegressor(strategy='mean').fit(d.iloc[tr][FEATURES],d.iloc[tr][TARGET]);base[te]=b.predict(d.iloc[te][FEATURES])
        rows.append(dict(fold=fold,n_test=len(te),mae=mean_absolute_error(d.iloc[te][TARGET],preds[te]),mae_baseline=mean_absolute_error(d.iloc[te][TARGET],base[te])))
    metrics=pd.DataFrame(rows);out=Path(output_dir);out.mkdir(exist_ok=True)
    metrics.to_csv(out/'validation_usage.csv',index=False)
    d['prediction_hors_commune']=preds;d['baseline_hors_commune']=base;d.to_csv(out/'predictions_validation.csv',index=False)
    if mean_absolute_error(d[TARGET],preds)>=mean_absolute_error(d[TARGET],base):
        raise ValueError('Le modèle ne bat pas la moyenne : évaluation enregistrée, modèle non validé pour le classement.')
    model=RandomForestRegressor(n_estimators=300,min_samples_leaf=5,max_depth=12,random_state=42,n_jobs=-1).fit(d[FEATURES],d[TARGET])
    joblib.dump({'model':model,'features':FEATURES,'target':TARGET,'feature_min':d[FEATURES].min(),'feature_max':d[FEATURES].max()},out/'modele_usage.joblib')
    return model,metrics
