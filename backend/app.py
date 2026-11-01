"""Prototipe Sistem Informasi Kredensial Mikro Terverifikasi Blockchain (FastAPI + web3.py)."""
import io, json, os, pathlib, sqlite3, time, base64
import qrcode
from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.responses import HTMLResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from chain import Chain, DATA
import vc

ROOT = pathlib.Path(__file__).resolve().parent
ANALYTICS = ROOT.parent / "analytics" / "out"
app = FastAPI(title="Prototipe Kredensial Mikro Blockchain")
CH = Chain()
DB = sqlite3.connect(DATA / f"kredensial_{CH.chain_id}.db", check_same_thread=False)
DB.execute("CREATE TABLE IF NOT EXISTS cred (hash TEXT PRIMARY KEY, subject TEXT, name TEXT, json TEXT, created REAL, revoked INTEGER DEFAULT 0, gas INTEGER, ms REAL)")
DB.commit()

class IssueReq(BaseModel):
    subject_id: str; subject_name: str; achievement: str; description: str = ""; criteria: str = ""
    credits: float | None = None; oulad_student: int | None = None

class RevokeReq(BaseModel):
    hash: str; reason: str = "dicabut oleh penerbit"

def evidence_for(student_id):
    p = ANALYTICS / "prediksi_sampel.csv"
    if student_id is None or not p.exists():
        return None
    import pandas as pd
    df = pd.read_csv(p); row = df[df.id_student == student_id]
    if row.empty:
        return None
    r = row.iloc[0]; meta = json.loads((ANALYTICS / "metrics.json").read_text())
    return {"id": f"urn:analitik:{meta['source']}:{int(r.id_student)}", "type": ["Evidence"],
            "name": "Bukti analitik pembelajaran (prototipe)",
            "description": f"Probabilitas lulus {r.p_lulus:.2f} (model random forest, data {meta['source']}, hari ke-{meta['cutoff_day']}); "
                           f"klik VLE {int(r.clicks)}, rerata skor {r.mean_score:.1f}."}

@app.get("/api/status")
def status():
    return {"mode": CH.mode, "chainId": CH.chain_id, "block": CH.w3.eth.block_number, "registry": CH.address,
            "issuer": CH.issuer.address, "issuerName": CH.c.functions.issuers(CH.issuer.address).call()[0]}

@app.post("/api/issue")
def issue(req: IssueReq):
    c = vc.build_credential(CH.issuer.address, status()["issuerName"], CH.chain_id, req.subject_id, req.subject_name,
                            req.achievement, req.description, req.criteria, req.credits, evidence_for(req.oulad_student))
    signed = vc.sign(c, CH.issuer.key, CH.address, CH.chain_id)
    h = vc.cred_hash(signed); sref = vc.keccak(req.subject_id.encode())
    t = time.perf_counter(); r = CH.send(CH.c.functions.issue(h, sref), CH.issuer); ms = (time.perf_counter() - t) * 1000
    DB.execute("INSERT INTO cred VALUES (?,?,?,?,?,0,?,?)", ("0x" + h.hex(), req.subject_id, req.achievement, json.dumps(signed), time.time(), r.gasUsed, ms)); DB.commit()
    return {"hash": "0x" + h.hex(), "gasUsed": r.gasUsed, "latencyMs": round(ms, 1), "tx": r.transactionHash.hex(), "credential": signed}

def _verify(cred):
    t = time.perf_counter(); checks = {}
    h = vc.cred_hash(cred); hx = "0x" + h.hex()
    checks["hash_cocok_dengan_proof"] = cred.get("proof", {}).get("anchor", {}).get("hash") == hx
    try:
        signer = vc.recover_signer(cred)
    except Exception:
        signer = None
    exists, issuer, active, issued_at, revoked, revoked_at = CH.c.functions.verify(h).call()
    checks["tercatat_di_blockchain"] = exists
    checks["tanda_tangan_penerbit_sah"] = bool(signer) and signer == issuer
    did = str(cred.get("issuer", {}).get("id", "") if isinstance(cred.get("issuer"), dict) else cred.get("issuer", ""))
    checks["did_penerbit_cocok"] = bool(exists) and did.lower().endswith(str(issuer).lower())  # v3: cegah klaim nama lembaga lain
    checks["penerbit_aktif"] = active
    checks["tidak_dicabut"] = not revoked
    ok = all(checks.values())
    return {"valid": ok, "hash": hx, "checks": checks, "issuer": issuer, "issuedAt": issued_at, "revokedAt": revoked_at,
            "latencyMs": round((time.perf_counter() - t) * 1000, 2)}

@app.post("/api/verify")
async def verify(file: UploadFile = File(...)):
    try:
        cred = json.loads((await file.read()).decode())
    except Exception:
        raise HTTPException(400, "Berkas bukan JSON kredensial yang sah")
    return _verify(cred)

@app.post("/api/verify-json")
def verify_json(cred: dict):
    return _verify(cred)

@app.get("/api/verify-hash/{h}")
def verify_hash(h: str):
    row = DB.execute("SELECT json FROM cred WHERE hash=?", (h,)).fetchone()
    if not row:
        raise HTTPException(404, "Kredensial tidak dikenal oleh portal ini")
    return _verify(json.loads(row[0]))

@app.post("/api/revoke")
def revoke(req: RevokeReq):
    t = time.perf_counter(); r = CH.send(CH.c.functions.revoke(bytes.fromhex(req.hash[2:]), req.reason), CH.issuer)
    DB.execute("UPDATE cred SET revoked=1 WHERE hash=?", (req.hash,)); DB.commit()
    return {"gasUsed": r.gasUsed, "latencyMs": round((time.perf_counter() - t) * 1000, 1)}

@app.get("/api/wallet/{subject}")
def wallet(subject: str):
    rows = DB.execute("SELECT hash,name,json,created,revoked FROM cred WHERE subject=? ORDER BY created DESC", (subject,)).fetchall()
    return [{"hash": h, "name": n, "credential": json.loads(j), "created": c, "revoked": bool(rv)} for h, n, j, c, rv in rows]

@app.get("/api/credentials")
def all_creds():
    rows = DB.execute("SELECT hash,subject,name,created,revoked,gas,ms FROM cred ORDER BY created DESC LIMIT 100").fetchall()
    return [dict(zip(["hash", "subject", "name", "created", "revoked", "gas", "ms"], r)) for r in rows]

@app.get("/api/qr/{h}")
def qr(h: str, base: str = "http://localhost:8000"):
    img = qrcode.make(f"{base}/#verifikasi/{h}"); b = io.BytesIO(); img.save(b, "PNG")
    return Response(b.getvalue(), media_type="image/png")

@app.get("/api/analytics")
def analytics():
    p = ANALYTICS / "metrics.json"
    if not p.exists():
        return {"available": False}
    m = json.loads(p.read_text()); m["available"] = True
    import pandas as pd
    s = pd.read_csv(ANALYTICS / "prediksi_sampel.csv").head(15)
    m["sample"] = s[["id_student", "code_module", "code_presentation", "p_lulus", "clicks", "mean_score"]].round(3).to_dict("records")
    return m

app.mount("/", StaticFiles(directory=ROOT / "static", html=True), name="static")
