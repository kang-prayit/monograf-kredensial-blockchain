"""Eksperimen: pengaruh batas hari pengamatan (cutoff) terhadap kinerja prediksi capaian dini pada OULAD,
serta statistik deskriptif klik mingguan per kelompok hasil akhir. Keluaran: experiments/hasil/oulad_cutoff.json"""
import json, pathlib, sys, numpy as np, pandas as pd
from sklearn.model_selection import train_test_split
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import roc_auc_score, f1_score, balanced_accuracy_score
D = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else "analytics/data/oulad"); OUT = pathlib.Path(__file__).resolve().parent / "hasil"
key = ["code_module", "code_presentation", "id_student"]
info = pd.read_csv(D / "studentInfo.csv")
parts = []
for ch in pd.read_csv(D / "studentVle.csv", chunksize=2_000_000, usecols=key + ["date", "sum_click"]):
    ch["week"] = (ch.date // 7).clip(lower=-4)
    parts.append(ch.groupby(key + ["week"]).agg(clicks=("sum_click", "sum"), days=("date", "nunique")))
wk = pd.concat(parts).groupby(level=[0, 1, 2, 3]).sum().reset_index()
lab = info[key + ["final_result"]]
wkl = wk.merge(lab, on=key)
n_by = lab.groupby("final_result").size()
weekly = (wkl[wkl.week.between(-4, 38)].groupby(["final_result", "week"]).clicks.sum() / n_by).unstack(0).fillna(0)
asm = pd.read_csv(D / "assessments.csv"); sa = pd.read_csv(D / "studentAssessment.csv").merge(asm, on="id_assessment")
sa["score"] = pd.to_numeric(sa.score, errors="coerce")
res = {}
for cut in [0, 14, 30, 60, 90, 120, 180]:
    v = wk[wk.week * 7 <= cut].groupby(key).agg(clicks=("clicks", "sum"), days=("days", "sum")).reset_index()
    s = sa[sa.date_submitted <= cut].groupby(key).agg(mean_score=("score", "mean"), n_submit=("score", "count")).reset_index()
    df = info.merge(v, on=key, how="left").merge(s, on=key, how="left").fillna({"clicks": 0, "days": 0, "mean_score": 0, "n_submit": 0})
    df["imd"] = df.imd_band.astype("category").cat.codes; df["edu"] = df.highest_education.astype("category").cat.codes
    X = df[["clicks", "days", "mean_score", "n_submit", "num_of_prev_attempts", "studied_credits", "imd", "edu"]].values
    y = df.final_result.isin(["Pass", "Distinction"]).astype(int).values
    Xtr, Xte, ytr, yte = train_test_split(X, y, test_size=.25, random_state=42, stratify=y)
    m = RandomForestClassifier(n_estimators=200, min_samples_leaf=5, class_weight="balanced", n_jobs=-1, random_state=42).fit(Xtr, ytr)
    p = m.predict_proba(Xte)[:, 1]
    res[cut] = {"auc": roc_auc_score(yte, p), "f1": f1_score(yte, p >= .5), "bacc": balanced_accuracy_score(yte, p >= .5)}
    print(cut, res[cut])
out = {"cutoff": res, "final_result_counts": n_by.to_dict(), "weekly_mean_clicks": {c: weekly[c].round(2).to_dict() for c in weekly.columns},
       "modules": info.groupby("code_module").size().to_dict(), "presentations": sorted(info.code_presentation.unique().tolist())}
(OUT / "oulad_cutoff.json").write_text(json.dumps(out, indent=1, default=str))
