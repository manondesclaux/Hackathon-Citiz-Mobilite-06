"""Compare l'âge de la population avec / sans station Citiz à moins de R mètres (Filosofi 2021, métropole).

Trois périmètres : toute la métropole ; départements ayant au moins une station ;
communes ayant au moins une station (le plus comparable : même ville, avec ou sans station à proximité).

Usage :
    python scripts/compare_ages_citiz.py DOSSIER_FLUX carreaux_200m_met.csv [rayon_m=500]
Sorties : comparaison_ages_citiz.png, comparaison_ages_departements.csv
"""
import sys
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd
from pyproj import Transformer
from scipy.spatial import cKDTree

sys.path.insert(0, str(Path(__file__).parent))
from analyse_citiz import charger  # noqa: E402

# tranches Filosofi -> âge central retenu pour estimer l'âge moyen
AGES = {"ind_0_3": 1.5, "ind_4_5": 5, "ind_6_10": 8.5, "ind_11_17": 14.5, "ind_18_24": 21.5,
        "ind_25_39": 32.5, "ind_40_54": 47.5, "ind_55_64": 60, "ind_65_79": 72.5, "ind_80p": 85}
LABELS = {"ind_0_3": "0-3", "ind_4_5": "4-5", "ind_6_10": "6-10", "ind_11_17": "11-17", "ind_18_24": "18-24",
          "ind_25_39": "25-39", "ind_40_54": "40-54", "ind_55_64": "55-64", "ind_65_79": "65-79", "ind_80p": "80+"}


def profil(g: pd.DataFrame) -> pd.Series:
    n = g[list(AGES)].sum()
    part = 100 * n / n.sum()
    part["age_moyen"] = sum(n[k] * a for k, a in AGES.items()) / n.sum()
    part["population"] = n.sum()
    return part


def main(flux: Path, csv: str, rayon: float):
    c = pd.read_csv(csv, usecols=["idcar_200m", "lcog_geo"] + list(AGES), dtype={"lcog_geo": str})
    ext = c.idcar_200m.str.extract(r"RES200mN(\d+)E(\d+)").astype(float)
    c["y"], c["x"] = ext[0] + 100, ext[1] + 100
    c["dep"] = c.lcog_geo.str[:2]

    st, _, _ = charger(flux)
    st = st.drop_duplicates(["lat", "lon"])
    st = st[st.lat.between(41, 52) & st.lon.between(-6, 10)]
    sx, sy = Transformer.from_crs(4326, 3035, always_xy=True).transform(st.lon.values, st.lat.values)
    d, _ = cKDTree(list(zip(sx, sy))).query(c[["x", "y"]].to_numpy())
    c["avec"] = d <= rayon
    # commune / département de la station = celui du carreau le plus proche
    _, idx = cKDTree(c[["x", "y"]].to_numpy()).query(list(zip(sx, sy)))
    communes = set(c.lcog_geo.iloc[idx])
    deps = set(c.dep.iloc[idx])
    c = c[c.ind_18_24.notna()]

    perimetres = {
        "Toute la métropole": c,
        "Départements avec station": c[c.dep.isin(deps)],
        "Communes avec station": c[c.lcog_geo.isin(communes)],
    }
    res = {}
    for nom, df in perimetres.items():
        res[nom] = {"avec": profil(df[df.avec]), "sans": profil(df[~df.avec])}
        a, s = res[nom]["avec"], res[nom]["sans"]
        print(f"\n=== {nom} (rayon {rayon:.0f} m) ===")
        t = pd.DataFrame({"avec station": a, "sans station": s})
        t["écart (pts)"] = t["avec station"] - t["sans station"]
        t.index = [LABELS.get(i, i) for i in t.index]
        print(t.round(1).to_string())

    # par département
    rows = []
    for dep, g in c[c.dep.isin(deps)].groupby("dep"):
        if g.avec.sum() == 0 or (~g.avec).sum() == 0:
            continue
        a, s = profil(g[g.avec]), profil(g[~g.avec])
        rows.append(dict(dep=dep, pop_avec=a.population, pop_sans=s.population, age_avec=a.age_moyen,
                         age_sans=s.age_moyen, ecart=a.age_moyen - s.age_moyen,
                         part_18_24_avec=a["ind_18_24"], part_18_24_sans=s["ind_18_24"],
                         part_65_79_avec=a["ind_65_79"], part_65_79_sans=s["ind_65_79"]))
    dep = pd.DataFrame(rows).sort_values("ecart").round(1)
    dep.to_csv("comparaison_ages_departements.csv", index=False)
    print("\nÉcart d'âge moyen (avec - sans) par département, 5 plus négatifs :\n", dep.head(5)[["dep", "age_avec", "age_sans", "ecart"]].to_string(index=False))
    print("5 plus positifs :\n", dep.tail(5)[["dep", "age_avec", "age_sans", "ecart"]].to_string(index=False))
    print(f"Départements où les zones avec station sont plus jeunes : {(dep.ecart < 0).sum()} / {len(dep)}")

    fig, axes = plt.subplots(1, 3, figsize=(16, 4.8), sharey=True)
    x = range(len(AGES))
    for ax, (nom, r) in zip(axes, res.items()):
        ax.bar([i - 0.2 for i in x], [r["avec"][k] for k in AGES], 0.4, label="avec station", color="#1d4ed8")
        ax.bar([i + 0.2 for i in x], [r["sans"][k] for k in AGES], 0.4, label="sans station", color="#9ca3af")
        ax.set_xticks(list(x), [LABELS[k] for k in AGES], rotation=45)
        ax.set_title(f"{nom}\nâge moyen : {r['avec'].age_moyen:.1f} vs {r['sans'].age_moyen:.1f} ans")
        ax.spines[["top", "right"]].set_visible(False)
    axes[0].set_ylabel("% de la population")
    axes[0].legend(frameon=False)
    fig.suptitle(f"Structure d'âge à moins de {rayon:.0f} m d'une station Citiz ou non (Filosofi 2021)")
    fig.tight_layout()
    fig.savefig("comparaison_ages_citiz.png", dpi=140)
    print("\nGraphique : comparaison_ages_citiz.png | CSV : comparaison_ages_departements.csv")


if __name__ == "__main__":
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    main(Path(sys.argv[1]), sys.argv[2], float(sys.argv[3]) if len(sys.argv) > 3 else 500.0)
