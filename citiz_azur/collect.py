"""Collecte traçable : catalogue PAN, GTFS, GBFS, INSEE. Python 3.11+."""
from pathlib import Path
import json, re, io, zipfile, hashlib, datetime, unicodedata
from concurrent.futures import ThreadPoolExecutor, as_completed
import requests
import pandas as pd
import numpy as np
from pyproj import Transformer

ROOT = Path(__file__).resolve().parent
DATA = ROOT/'data'; DATA.mkdir(exist_ok=True)
CACHE = DATA/'cache'; CACHE.mkdir(exist_ok=True)
LOG=[]
INSEE='https://www.insee.fr/fr/statistiques/fichier/8735162/Filosofi2021_carreaux_200m_csv.zip'

def get(url, refresh=False):
    p=CACHE/(hashlib.sha256(url.encode()).hexdigest()+'.bin')
    if p.exists() and not refresh: return p.read_bytes()
    r=requests.get(url,timeout=(15,90)); r.raise_for_status()
    p.write_bytes(r.content)
    return r.content

def js(url): return json.loads(get(url))
def plain(value):
    if isinstance(value,list): return next((x.get('text','') for x in value if x.get('language')=='fr'), value[0].get('text','') if value else '')
    return str(value)
def slug(s): return re.sub('[^a-z0-9]+','-',unicodedata.normalize('NFKD',s).encode('ascii','ignore').decode().lower()).strip('-')
def bounds(df, margin=.03):
    # Zone de travail : Alpes-Maritimes. Marge pour les effets de bord.
    return df[df.lat.between(43.40-margin,44.40+margin)&df.lon.between(6.60-margin,7.75+margin)].copy()

def gbfs(url, operator, depth=0):
    if depth>2: raise ValueError('Trop de niveaux GBFS')
    data=js(url)['data']
    if 'feeds' not in data:
        data=next((v for v in data.values() if isinstance(v,dict) and 'feeds' in v),data)
    feeds={x['name']:x['url'] for x in data.get('feeds',[])}
    rows=[]
    if 'station_information' in feeds:
        for x in js(feeds['station_information'])['data']['stations']:
            if x.get('lat') is not None and x.get('lon') is not None:
                rows.append(dict(id=str(x['station_id']),operator=operator,kind='station',lat=x['lat'],lon=x['lon'],name=plain(x.get('name','')),source=url))
    # Ne pas additionner les véhicules attachés à une station déjà comptée.
    vf=feeds.get('vehicle_status') or feeds.get('free_bike_status')
    if vf:
        v=js(vf)['data']; vehicles=v.get('vehicles',v.get('bikes',[]))
        for x in vehicles:
            if x.get('station_id') and rows: continue
            if x.get('lat') is not None and x.get('lon') is not None:
                rows.append(dict(id=str(x.get('vehicle_id',x.get('bike_id',''))),operator=operator,kind='vehicle',lat=x['lat'],lon=x['lon'],name='Véhicule mobile observé',source=url))
    return rows

def gtfs(url,title):
    z=zipfile.ZipFile(io.BytesIO(get(url)))
    f=next(n for n in z.namelist() if n.endswith('stops.txt'))
    d=pd.read_csv(z.open(f),dtype={'stop_id':str,'parent_station':str},low_memory=False)
    d=d.rename(columns={'stop_lat':'lat','stop_lon':'lon','stop_name':'name'})
    d['lat']=pd.to_numeric(d.lat,errors='coerce');d['lon']=pd.to_numeric(d.lon,errors='coerce')
    d=bounds(d.dropna(subset=['lat','lon']))
    # Arrêts/quais uniquement, pas entrées et nœuds de cheminement.
    if 'location_type' in d: d=d[pd.to_numeric(d.location_type,errors='coerce').fillna(0).eq(0)]
    d['network']=title; d['source']=url
    # Parents et quais opposés de même nom sont fusionnés au stade spatial.
    d['id']=title+':'+hashlib.sha256(url.encode()).hexdigest()[:8]+':'+d.stop_id
    return d[['id','name','lat','lon','network','source']]

def collect_services():
    catalogue=json.loads((DATA/'catalogue.json').read_text()) if (DATA/'catalogue.json').exists() else js('https://transport.data.gouv.fr/api/datasets')
    (DATA/'catalogue.json').write_text(json.dumps(catalogue,ensure_ascii=False))
    communes=js('https://geo.api.gouv.fr/departements/06/communes?fields=nom,code&format=json')
    (DATA/'communes.json').write_text(json.dumps(communes,ensure_ascii=False))
    tasks=[]
    for d in catalogue:
        title=d['title']
        for r in d.get('resources',[]):
            u=r.get('original_url',r['url']); fmt=r.get('format','').lower()
            if fmt=='gtfs' and re.search(r"Lignes d.Azur|ENVIBUS|Palmbus|Sillages|Zest|Proximité ZOU|Express ZOU|Trains régionaux ZOU",title,re.I): tasks.append(('gtfs',u,title))
            if fmt=='gbfs' and re.search(r'Citiz|Autopartage Clem',title,re.I): tasks.append(('gbfs',u,title))
    manifest=js('https://fr.getaround.com/gbfs/manifest?country_code=FR')
    names={slug(x['nom']) for x in communes}
    for ds in manifest['data']['datasets']:
        if ds['system_id'].removeprefix('getaround_').replace('_','-') in names:
            tasks.append(('gbfs',ds['versions'][-1]['url'],'Getaround'))
    stations=[]; stops=[]
    with ThreadPoolExecutor(max_workers=8) as pool:
        futures={pool.submit(gtfs if typ=='gtfs' else gbfs,u,t):(typ,u,t) for typ,u,t in tasks}
        for fut in as_completed(futures):
            typ,u,t=futures[fut]
            try:
                rows=fut.result()
                (stops if typ=='gtfs' else stations).append(rows)
                LOG.append(dict(type=typ,url=u,title=t,status='ok',rows=len(rows)))
                print('OK',t,len(rows),flush=True)
            except Exception as e:
                LOG.append(dict(type=typ,url=u,title=t,status='error',error=str(e)))
                print('ERREUR',t,str(e)[:100],flush=True)
    pd.DataFrame([row for batch in stations for row in batch]).drop_duplicates(['operator','kind','id']).to_csv(DATA/'sharing.csv',index=False)
    pd.concat(stops,ignore_index=True).drop_duplicates(['id']).to_csv(DATA/'stops_raw.csv',index=False)
    (DATA/'collection_log.json').write_text(json.dumps({'collected_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'sources':LOG},ensure_ascii=False,indent=2))

def population():
    p=DATA/'filosofi.zip'
    if not p.exists(): p.write_bytes(get(INSEE))
    z=zipfile.ZipFile(p)
    print(z.namelist())
    f=next(n for n in z.namelist() if 'met' in n.lower() and n.endswith('.csv'))
    # pandas reconnaît le séparateur après lecture de l'en-tête.
    header=z.open(f).readline().decode('utf-8-sig'); sep=';' if ';' in header else ','
    selected=[]
    for c in pd.read_csv(z.open(f),sep=sep,chunksize=100000,dtype=str):
        c.columns=c.columns.str.lower()
        code=c['lcog_geo'].fillna('')
        c=c[code.str.contains(r'(?<!\d)06\d{3}(?!\d)',regex=True)].copy()
        if len(c): selected.append(c)
    d=pd.concat(selected,ignore_index=True)
    # Inspire N/E indique le coin sud-ouest du carreau, +100m -> centre.
    en=d.idcar_200m.str.extract(r'N(\d+)E(\d+)').astype(float)
    if en.isna().any().any(): raise ValueError('Identifiant INSEE non reconnu')
    lon,lat=Transformer.from_crs(3035,4326,always_xy=True).transform(en[1]+100,en[0]+100)
    d['lon']=lon;d['lat']=lat
    d['population']=pd.to_numeric(d.ind.str.replace(',','.'),errors='raise')
    d['code_commune']=d.lcog_geo.str.extract(r'(06\d{3})')[0]
    names={x['code']:x['nom'] for x in json.loads((DATA/'communes.json').read_text())}
    d['commune']=d.code_commune.map(names).fillna(d.code_commune)
    d=d.rename(columns={'idcar_200m':'id'})
    d[['id','lat','lon','population','commune','code_commune','i_est_200']].to_csv(DATA/'population.csv',index=False)
    print('Population',len(d),d.population.sum())

if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('--population',action='store_true');p.add_argument('--refresh',action='store_true');a=p.parse_args()
    if a.refresh:
        for cache_file in CACHE.glob('*.bin'): cache_file.unlink()
        (DATA/'catalogue.json').unlink(missing_ok=True)
    population() if a.population else collect_services()
