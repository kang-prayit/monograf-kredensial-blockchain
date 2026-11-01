"""Melatih model prediksi capaian dini dari OULAD (Kuzilek dkk., 2017; doi 10.1038/sdata.2017.171).
Unduh data: https://archive.ics.uci.edu/dataset/349 (CC BY 4.0) lalu ekstrak ke analytics/data/oulad/.
Jika data tidak ada, gunakan --synthetic (DATA SINTETIS, bukan OULAD)."""
import argparse, json, pathlib, time
import numpy as np, pandas as pd, joblib
from sklearn.model_selection import train_test_split
from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import accuracy_score, f1_score, roc_auc_score, confusion_matrix, roc_curve, balanced_accuracy_score

HERE = pathlib.Path(__file__).resolve().parent
CUTOFF = 60  # hari sejak awal presentasi modul: prediksi "dini"

def features(d, cutoff=CUTOFF):
    info = pd.read_csv(d / "studentInfo.csv")
    key = ["code_module", "code_presentation", "id_student"]
    clicks = []
    for ch in pd.read_csv(d / "studentVle.csv", chunksize=2_000_000):
        ch = ch[ch.date <= cutoff]
        clicks.append(ch.groupby(key).agg(clicks=("sum_click", "sum"), days=("date", "nunique")))
    vle = pd.concat(clicks).groupby(level=[0, 1, 2]).sum().reset_index()
    asm = pd.read_csv(d / "assessments.csv"); sa = pd.read_csv(d / "studentAssessment.csv")
    sa = sa.merge(asm, on="id_assessment")
    sa = sa[(sa.date_submitted <= cutoff)]
    sa["score"] = pd.to_numeric(sa.score, errors="coerce")
    sc = sa.groupby(key).agg(mean_score=("score", "mean"), n_submit=("score", "count")).reset_index()
    df = info.merge(vle, on=key, how="left").merge(sc, on=key, how="left")
    df[["clicks", "days", "n_submit"]] = df[["clicks", "days", "n_submit"]].fillna(0)
    df["mean_score"] = df["mean_score"].fillna(0)
    df["y"] = df.final_result.isin(["Pass", "Distinction"]).astype(int)
    df["imd"] = df.imd_band.astype("category").cat.codes
    df["age"] = df.age_band.astype("category").cat.codes
    df["edu"] = df.highest_education.astype("category").cat.codes
    df["disab"] = (df.disability == "Y").astype(int)
    return df

FEATS = ["clicks", "days", "mean_score", "n_submit", "num_of_prev_attempts", "studied_credits", "imd", "age", "edu", "disab"]

def synthetic(n=5000, seed=7):
    r = np.random.default_rng(seed)
    df = pd.DataFrame({"clicks": r.gamma(2, 300, n), "days": r.integers(0, 60, n), "mean_score": r.uniform(0, 100, n),
                       "n_submit": r.integers(0, 4, n), "num_of_prev_attempts": r.integers(0, 3, n),
                       "studied_credits": r.choice([30, 60, 90, 120], n), "imd": r.integers(0, 10, n),
                       "age": r.integers(0, 3, n), "edu": r.integers(0, 5, n), "disab": r.integers(0, 2, n)})
    z = 0.002 * df.clicks + 0.03 * df.mean_score + 0.5 * df.n_submit - 3
    df["y"] = (r.uniform(size=n) < 1 / (1 + np.exp(-z))).astype(int)
    df["id_student"] = np.arange(n); df["code_module"] = "SINTETIS"; df["code_presentation"] = "-"
    return df

def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--data", default=str(HERE / "data" / "oulad")); ap.add_argument("--synthetic", action="store_true")
    a = ap.parse_args(); d = pathlib.Path(a.data)
    src = "SINTETIS" if a.synthetic or not (d / "studentInfo.csv").exists() else "OULAD"
    t0 = time.time(); df = synthetic() if src == "SINTETIS" else features(d)
    X, y = df[FEATS].values, df.y.values
    Xtr, Xte, ytr, yte, itr, ite = train_test_split(X, y, df.index.values, test_size=0.25, random_state=42, stratify=y)
    models = {"Regresi logistik": make_pipeline(StandardScaler(), LogisticRegression(max_iter=1000, class_weight="balanced")),
              "Random forest": RandomForestClassifier(n_estimators=300, min_samples_leaf=5, class_weight="balanced", n_jobs=-1, random_state=42)}
    res, curves = {}, {}
    for n, m in models.items():
        m.fit(Xtr, ytr); p = m.predict_proba(Xte)[:, 1]; yh = (p >= .5).astype(int)
        res[n] = {"accuracy": accuracy_score(yte, yh), "balanced_accuracy": balanced_accuracy_score(yte, yh),
                  "f1": f1_score(yte, yh), "roc_auc": roc_auc_score(yte, p), "confusion": confusion_matrix(yte, yh).tolist()}
        fpr, tpr, _ = roc_curve(yte, p); curves[n] = {"fpr": fpr[::max(1, len(fpr)//200)].tolist(), "tpr": tpr[::max(1, len(tpr)//200)].tolist()}
    rf = models["Random forest"]
    imp = dict(sorted(zip(FEATS, rf.feature_importances_.tolist()), key=lambda x: -x[1]))
    df["p_lulus"] = rf.predict_proba(X)[:, 1]
    out = HERE / "out"; out.mkdir(exist_ok=True)
    joblib.dump({"model": rf, "feats": FEATS, "source": src}, out / "model.joblib")
    sample = df.loc[ite].sort_values("p_lulus", ascending=False)
    sample[["id_student", "code_module", "code_presentation", "p_lulus", "y"] + FEATS].head(300).to_csv(out / "prediksi_sampel.csv", index=False)
    meta = {"source": src, "cutoff_day": CUTOFF, "n_rows": int(len(df)), "n_train": int(len(Xtr)), "n_test": int(len(Xte)),
            "positive_rate": float(y.mean()), "metrics": res, "importance": imp, "roc": curves, "seconds": round(time.time() - t0, 1)}
    (out / "metrics.json").write_text(json.dumps(meta, indent=1))
    print(json.dumps({k: v for k, v in meta.items() if k != "roc"}, indent=1))

if __name__ == "__main__":
    main()
