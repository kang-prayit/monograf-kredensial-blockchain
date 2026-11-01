"""Uji end-to-end & pengukuran: penerbitan, verifikasi, pencabutan, perusakan, batch/Merkle.
Prasyarat: backend berjalan di BASE (default http://localhost:8000) dan CHAIN_RPC menunjuk node yang sama."""
import json, os, sys, time, statistics as st, pathlib, platform, copy, requests
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "backend"))
BASE = os.environ.get("BASE", "http://localhost:8000"); N = int(os.environ.get("N", "50"))
OUT = pathlib.Path(__file__).resolve().parent / "hasil"; OUT.mkdir(exist_ok=True)

def summ(xs):
    xs = sorted(xs); return {"n": len(xs), "mean": st.mean(xs), "median": st.median(xs), "p95": xs[int(.95 * (len(xs) - 1))], "min": xs[0], "max": xs[-1]}

def main():
    s = requests.get(BASE + "/api/status").json(); stu = [r["id_student"] for r in requests.get(BASE + "/api/analytics").json().get("sample", [])]
    iss, e2e_i, gas_i, creds = [], [], [], []
    for i in range(N):
        body = {"subject_id": f"peserta{i:03d}@contoh.ac.id", "subject_name": f"Peserta {i}", "achievement": "Kredensial Mikro: Dasar Analitik Data",
                "description": "uji", "criteria": "lulus", "credits": 2, "oulad_student": stu[i % len(stu)] if stu else None}
        t = time.perf_counter(); r = requests.post(BASE + "/api/issue", json=body).json(); e2e_i.append((time.perf_counter() - t) * 1000)
        iss.append(r["latencyMs"]); gas_i.append(r["gasUsed"]); creds.append(r)
    ver, e2e_v, ok = [], [], 0
    for r in creds:
        t = time.perf_counter(); v = requests.post(BASE + "/api/verify-json", json=r["credential"]).json(); e2e_v.append((time.perf_counter() - t) * 1000)
        ver.append(v["latencyMs"]); ok += v["valid"]
    tam_detect = 0
    for r in creds[:20]:
        c = copy.deepcopy(r["credential"]); c["credentialSubject"]["name"] += " (diubah)"
        tam_detect += not requests.post(BASE + "/api/verify-json", json=c).json()["valid"]
    rev, gas_r, rev_detect = [], [], 0
    for r in creds[:10]:
        x = requests.post(BASE + "/api/revoke", json={"hash": r["hash"], "reason": "uji pencabutan"}).json(); rev.append(x["latencyMs"]); gas_r.append(x["gasUsed"])
        v = requests.post(BASE + "/api/verify-json", json=r["credential"]).json(); rev_detect += (not v["valid"]) and (not v["checks"]["tidak_dicabut"])
    # batch & Merkle langsung ke kontrak
    os.environ.setdefault("DATA_DIR", "/tmp/kd_exp")
    from chain import Chain; import vc
    from eth_utils import keccak
    ch = Chain(); batch = {}
    for k in [1, 2, 5, 10, 20, 50, 100]:
        hs = [keccak(f"batch{k}-{j}-{time.time()}".encode()) for j in range(k)]
        g_ind = ch.send(ch.c.functions.issueBatch(hs, keccak(b"x")), ch.issuer).gasUsed
        hs2 = [keccak(f"merk{k}-{j}-{time.time()}".encode()) for j in range(k)]
        root, proofs = vc.merkle_root_and_proofs(hs2)
        g_root = ch.send(ch.c.functions.anchorBatchRoot(root, k), ch.issuer).gasUsed
        okm = all(ch.c.functions.verifyInBatch(h, p, root).call() for h, p in zip(hs2, proofs))
        batch[k] = {"issueBatch_gas": g_ind, "issueBatch_gas_per_cred": g_ind / k, "merkle_root_gas": g_root, "merkle_gas_per_cred": g_root / k,
                    "merkle_proof_len": len(proofs[0]), "merkle_all_verified": okm}
    res = {"tanggal": time.strftime("%Y-%m-%d %H:%M:%S %Z"), "lingkungan": {"python": platform.python_version(), "os": platform.platform(), "chain": s["mode"], "chainId": s["chainId"]},
           "deploy_gas": ch.deploy_gas, "N": N, "issue_gas": summ(gas_i), "issue_chain_ms": summ(iss), "issue_e2e_ms": summ(e2e_i),
           "verify_ms": summ(ver), "verify_e2e_ms": summ(e2e_v), "valid_count": ok, "tamper_tests": 20, "tamper_detected": tam_detect,
           "revoke_gas": summ(gas_r), "revoke_ms": summ(rev), "revoke_detected": rev_detect, "batch": batch,
           "raw": {"issue_e2e_ms": e2e_i, "verify_e2e_ms": e2e_v}}
    (OUT / "hasil_e2e.json").write_text(json.dumps(res, indent=1))
    print(json.dumps({k: v for k, v in res.items() if k != "raw"}, indent=1))

if __name__ == "__main__":
    main()
