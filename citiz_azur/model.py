"""Segmentation ML et optimisation gloutonne de couverture (pas prévision d'usage)."""
from pathlib import Path
import json, html, math
import numpy as np
import pandas as pd
from sklearn.neighbors import BallTree
from sklearn.cluster import KMeans, DBSCAN
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import silhouette_score
import joblib

ROOT=Path(__file__).resolve().parent
R=6371008.8
DEFAULT=dict(radius_m=400,exclude_citiz_m=800,separation_m=800,max_per_commune=2,
             budget_eur=500000,capex_eur=40000,opex_year1_eur=10000,
             weights=[.60,.25,.15],mobile_weight=.25,top_n=10)

def coords(d): return np.radians(d[['lat','lon']].to_numpy(float))
def neighbors(a,b,r):
    if len(b)==0:return [np.array([],dtype=int) for _ in range(len(a))]
    return BallTree(coords(b),metric='haversine').query_radius(coords(a),r=r/R)
def nearest(a,b):
    if len(b)==0:return np.full(len(a),np.nan),np.full(len(a),-1)
    ds,ix=BallTree(coords(b),metric='haversine').query(coords(a),k=1)
    return ds[:,0]*R,ix[:,0]
def dedup_stops(d):
    # Proximité 30m : indicateur de pôles, pas nombre de lignes ni de passages.
    d=d.dropna(subset=['lat','lon']).copy()
    d['group']=DBSCAN(eps=30/R,min_samples=1,metric='haversine',algorithm='ball_tree').fit_predict(coords(d))
    return d.groupby('group',as_index=False).agg(lat=('lat','mean'),lon=('lon','mean'),name=('name','first'),network=('network',lambda x:' | '.join(sorted(set(x)))))
def scale(d):
    x=np.log1p(np.asarray(d,float))
    return x/x.max() if x.max()>0 else np.zeros(len(x))

def build_features(pop,sharing,stops,cfg=None):
    cfg={**DEFAULT,**(cfg or {})};r=cfg['radius_m']
    p=pop.copy().reset_index(drop=True)
    if p.id.duplicated().any() or p.population.isna().any() or (p.population<0).any(): raise ValueError('Population invalide')
    is_citiz=sharing.operator.str.contains('citiz',case=False,na=False)
    c=sharing[is_citiz].reset_index(drop=True)
    rivals=sharing[~is_citiz].reset_index(drop=True)
    fixed=rivals[rivals.kind.eq('station')].reset_index(drop=True)
    mobile=rivals[rivals.kind.eq('vehicle')].reset_index(drop=True)
    if len(stops)==0: raise ValueError('Aucun arrêt collecté : ne pas interpréter comme absence de transport')
    stops=dedup_stops(stops)
    near,_=nearest(p,c)
    if not np.isfinite(near).all(): raise ValueError('Inventaire Citiz vide : ne pas interpréter comme absence')
    p['distance_citiz_m']=near
    p['already_citiz']=near<=r
    # Tous les carreaux habités sont candidats. Coordonnées = centres, à valider sur le terrain.
    a=p[(p.population>0)&(near>=cfg['exclude_citiz_m'])].copy().reset_index(drop=True)
    coverage=neighbors(a,p,r)
    uncovered=(~p.already_citiz).to_numpy()
    values=p.population.to_numpy()
    a['population_400m']=[values[ix].sum() for ix in coverage]
    a['population_nouvelle']=[values[ix][uncovered[ix]].sum() for ix in coverage]
    a['part_population_imputee']=[values[ix][pd.to_numeric(p.iloc[ix].i_est_200).eq(1)].sum()/max(1,values[ix].sum()) for ix in coverage]
    a['arrets_400m']=[len(ix) for ix in neighbors(a,stops,r)]
    a['stations_concurrentes_400m']=[len(ix) for ix in neighbors(a,fixed,r)]
    a['vehicules_concurrents_400m']=[len(ix) for ix in neighbors(a,mobile,r)]
    dist,idx=nearest(a,stops)
    a['distance_arret_m']=dist
    a['arret_proche']=stops.iloc[idx].name.to_numpy() if len(stops) else ''
    a['pression_concurrentielle']=a.stations_concurrentes_400m+cfg['mobile_weight']*a.vehicules_concurrents_400m
    a['s_population']=scale(a.population_nouvelle)
    a['s_transport']=scale(a.arrets_400m)
    a['s_concurrence']=1/(1+a.pression_concurrentielle)
    w=np.asarray(cfg['weights']); assert len(w)==3 and (w>=0).all() and w.sum()>0
    w=w/w.sum()
    a['score']=100*(w[0]*a.s_population+w[1]*a.s_transport+w[2]*a.s_concurrence)
    a['cout_eur']=cfg['capex_eur']+cfg['opex_year1_eur']
    return a,p,coverage,stops

def segment(a,output=None):
    cols=['population_nouvelle','arrets_400m','pression_concurrentielle']
    sc=StandardScaler();x=sc.fit_transform(np.log1p(a[cols]))
    candidates=[]
    for k in range(2,7):
        m=KMeans(n_clusters=k,random_state=42,n_init=10).fit(x)
        s=silhouette_score(x,m.labels_,sample_size=min(1500,len(x)),random_state=42)
        candidates.append((s,k,m))
    score,k,m=max(candidates,key=lambda x:x[0])
    a=a.copy();a['profil_ml']=m.labels_
    metrics={'method':'KMeans','k':k,'silhouette':float(score),'n_candidates':len(a),
             'silhouette_by_k':{str(k):float(s) for s,k,_ in candidates},
             'meaning':'Segmentation descriptive ; aucun taux de réservation prédit.'}
    if output:
        joblib.dump({'scaler':sc,'model':m,'features':cols},Path(output)/'segmentation.joblib')
        (Path(output)/'ml_metrics.json').write_text(json.dumps(metrics,indent=2,ensure_ascii=False))
    return a,metrics

def select(a,p,coverage,cfg=None):
    cfg={**DEFAULT,**(cfg or {})}; cost=cfg['capex_eur']+cfg['opex_year1_eur']
    if cost<=0 or cfg['budget_eur']<0: raise ValueError('Budget/coût invalide')
    available=set(range(len(a)));covered=p.already_citiz.to_numpy().copy();v=p.population.to_numpy()
    selected=[];counts={};budget=cfg['budget_eur']
    # Contrainte spatiale + gain marginal : pas de double compte des habitants.
    proximity=neighbors(a,a,cfg['separation_m'])
    while available and len(selected)<cfg['top_n'] and budget>=cost:
        best=None
        for i in sorted(available):
            row=a.iloc[i]
            if counts.get(row.commune,0)>=cfg['max_per_commune']:continue
            ix=coverage[i];gain=v[ix][~covered[ix]].sum()
            if gain<=0:continue
            utility=row.score*(gain/max(row.population_nouvelle,1))/cost
            if best is None or utility>best[0]:best=(utility,i,gain)
        if best is None:break
        utility,i,gain=best; row=a.iloc[i].to_dict()
        row.update(rang=len(selected)+1,habitants_supplementaires=gain,utilite_marginale=utility,
                   budget_cumule=cfg['budget_eur']-budget+cost)
        selected.append(row);covered[coverage[i]]=True;budget-=cost
        counts[row['commune']]=counts.get(row['commune'],0)+1
        available.difference_update(proximity[i]);available.discard(i)
    return pd.DataFrame(selected)

def export_map(top,a,sharing,stops,output):
    import folium
    m=folium.Map(location=[43.72,7.18],zoom_start=10,tiles='OpenStreetMap')
    title='Top 10 exploratoire · Alpes-Maritimes · Population 2021 · Distances à vol d’oiseau'
    m.get_root().html.add_child(folium.Element('<div style="position:fixed;top:10px;left:55px;z-index:9999;background:white;padding:12px;max-width:600px;font:14px sans-serif"><b>'+title+'</b><br>Score de décision + KMeans ; aucune prévision de réservations.<br>Coûts hypothétiques. Absence Citiz = absence dans les sources collectées.</div>'))
    fg=folium.FeatureGroup(name='Sélection sous budget').add_to(m)
    for _,r in top.iterrows():
        txt=(f"<b>#{int(r.rang)} {html.escape(r.commune)} — près de {html.escape(str(r.arret_proche))}</b>"
             f"<br>Centre du carreau candidat : {r.lat:.5f}, {r.lon:.5f}"
             f"<br>Score individuel : {r.score:.1f}/100 · profil ML {int(r.profil_ml)}"
             f"<br>Habitants dans 400m : {r.population_400m:,.0f}"
             f"<br>Habitants supplémentaires, sans double compte : {r.habitants_supplementaires:,.0f}"
             f"<br>Pôles d'arrêts : {int(r.arrets_400m)} · distance arrêt : {r.distance_arret_m:.0f}m"
             f"<br>Concurrence : {int(r.stations_concurrentes_400m)} stations, {int(r.vehicules_concurrents_400m)} véhicules observés"
             f"<br>Citiz observé le plus proche : {r.distance_citiz_m/1000:.1f}km"
             f"<br>Coût année 1 (hypothèse) : {r.cout_eur:,.0f} €<br>Emplacement de voirie à vérifier.")
        folium.Marker([r.lat,r.lon],tooltip=f"#{int(r.rang)} {r.commune} — {r.arret_proche}",popup=folium.Popup(txt,max_width=440),icon=folium.DivIcon(html=f'<div style="background:#143f63;color:white;border-radius:50%;width:28px;height:28px;text-align:center;line-height:28px;font-weight:bold">{int(r.rang)}</div>')).add_to(fg)
        folium.Circle([r.lat,r.lon],radius=400,color='#167d9a',fill=True,fill_opacity=.08).add_to(fg)
    from collect import bounds
    for label,subset,color in [('Citiz observé',sharing[sharing.operator.str.contains('citiz',case=False)],'#2563eb'),('Concurrents observés',sharing[~sharing.operator.str.contains('citiz',case=False)],'#df7a24')]:
        layer=folium.FeatureGroup(name=label,show=False).add_to(m)
        for _,r in bounds(subset).iterrows():
            folium.CircleMarker([r.lat,r.lon],radius=3,color=color,tooltip=html.escape(f'{r.operator} · {r.kind} · {r["name"]}')).add_to(layer)
    layer=folium.FeatureGroup(name='Pôles d’arrêts GTFS (30m)',show=False).add_to(m)
    for _,r in stops.iterrows():folium.CircleMarker([r.lat,r.lon],radius=2,color='#798b96',tooltip=html.escape(str(r['name']))).add_to(layer)
    folium.LayerControl(collapsed=False).add_to(m);m.save(str(output))
    return m

def run(cfg=None):
    cfg={**DEFAULT,**(cfg or {})};out=ROOT/'results';out.mkdir(exist_ok=True)
    audit=json.loads((ROOT/'data/collection_log.json').read_text())
    if any(x['status']!='ok' for x in audit['sources']): raise ValueError('Collecte incomplète : inspecter collection_log.json')
    pop=pd.read_csv(ROOT/'data/population.csv',dtype={'code_commune':str})
    sharing=pd.read_csv(ROOT/'data/sharing.csv')
    stops=pd.read_csv(ROOT/'data/stops_raw.csv')
    a,p,cov,stops=build_features(pop,sharing,stops,cfg)
    a,metrics=segment(a,out);top=select(a,p,cov,cfg)
    a.to_csv(out/'candidats.csv',index=False);top.to_csv(out/'top10.csv',index=False)
    (out/'config.json').write_text(json.dumps(cfg,indent=2))
    export_map(top,a,sharing,stops,out/'carte_top10.html')
    return top,a,p,cov,metrics

if __name__=='__main__':
    top,*_=run();print(top[['rang','commune','arret_proche','score','habitants_supplementaires']].to_string(index=False))
