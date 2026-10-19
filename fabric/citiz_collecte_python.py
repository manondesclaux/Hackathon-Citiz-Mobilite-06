# Notebook Fabric en runtime PYTHON (pas PySpark) : collecte Citiz -> table Delta citiz_releves.
# Cellule 1 (si deltalake n'est pas déjà installé) :  %pip install -q deltalake
# Cellule 2 : tout ce qui suit. Notebook attaché au lakehouse. Planifier toutes les 5 minutes.
import requests
import pandas as pd
import pyarrow as pa
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from deltalake import write_deltalake

CATALOGUE = "https://transport.data.gouv.fr/api/datasets"
S = requests.Session()
S.headers["User-Agent"] = "citiz-surveillance/1.0"


def texte(v):
    return None if v is None else str(v)


def flux_gbfs():
    jeux = S.get(CATALOGUE, timeout=120).json()
    return {j["slug"]: next(r["url"] for r in j["resources"] if r["format"] == "gbfs")
            for j in jeux
            if "citiz" in j["title"].lower() and any(r["format"] == "gbfs" for r in j["resources"])}


def vehicle_status(item):
    jeu, url = item
    try:
        feeds = {f["name"]: f["url"] for f in S.get(url, timeout=30).json()["data"]["feeds"]}
        vs = S.get(feeds["vehicle_status"], timeout=30).json()["data"]["vehicles"]
    except Exception as e:  # un jeu en panne ne doit pas bloquer les autres
        print(f"{jeu}: ERREUR {e}")
        return []
    return [dict(jeu=jeu, vehicle_id=str(v["vehicle_id"]), lat=v.get("lat"), lon=v.get("lon"),
                 station_id=texte(v.get("station_id")), home_station_id=texte(v.get("home_station_id")),
                 vehicle_type_id=texte(v.get("vehicle_type_id")),
                 is_reserved=v.get("is_reserved"), is_disabled=v.get("is_disabled"),
                 fuel_pct=v.get("current_fuel_percent"), range_m=v.get("current_range_meters"),
                 last_reported=v.get("last_reported")) for v in vs]


releve = datetime.now(timezone.utc)
with ThreadPoolExecutor(8) as ex:
    lignes = [r for res in ex.map(vehicle_status, flux_gbfs().items()) for r in res]
if not lignes:
    raise RuntimeError("Aucun véhicule récupéré : flux indisponibles ?")

df = pd.DataFrame(lignes)
df["last_reported"] = pd.to_datetime(df["last_reported"], utc=True, errors="coerce").dt.floor("us")
df["releve_utc"] = pd.Timestamp(releve)

ts = pa.timestamp("us", tz="UTC")
schema = pa.schema([
    ("jeu", pa.string()), ("vehicle_id", pa.string()),
    ("lat", pa.float64()), ("lon", pa.float64()),
    ("station_id", pa.string()), ("home_station_id", pa.string()), ("vehicle_type_id", pa.string()),
    ("is_reserved", pa.bool_()), ("is_disabled", pa.bool_()),
    ("fuel_pct", pa.float64()), ("range_m", pa.float64()),
    ("last_reported", ts), ("releve_utc", ts),
])
table = pa.Table.from_pandas(df, schema=schema, preserve_index=False, safe=False)

# écriture directe dans OneLake (le montage /lakehouse/default interdit le renommage de fichiers)
import notebookutils
ctx = notebookutils.runtime.context
TABLE_URI = (f"abfss://{ctx['currentWorkspaceId']}@onelake.dfs.fabric.microsoft.com/"
             f"{ctx['defaultLakehouseId']}/Tables/citiz_releves")
write_deltalake(
    TABLE_URI, table, mode="append",
    storage_options={"bearer_token": notebookutils.credentials.getToken("storage"),
                     "use_fabric_endpoint": "true"},
)
print(f"{len(df)} véhicules, {df.jeu.nunique()} jeux -> citiz_releves")
