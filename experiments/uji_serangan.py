"""Uji skenario serangan/kesalahan + contoh terhitung (hash, tanda tangan, Merkle) — dijalankan NYATA pada kontrak prototipe.
Default: eth-tester dalam proses (tanpa Node). Set CHAIN_RPC untuk Hardhat."""
import os, sys, json, copy, time, pathlib, platform, tempfile
os.environ.setdefault("DATA_DIR", tempfile.mkdtemp(prefix="kd_serangan_"))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "backend"))
from fastapi.testclient import TestClient
import app as A, vc
from eth_account import Account
from eth_utils import keccak
OUT = pathlib.Path(__file__).resolve().parent / "hasil"; OUT.mkdir(exist_ok=True)
cl = TestClient(A.app); CH = A.CH; N = 20
stu = [r["id_student"] for r in cl.get("/api/analytics").json().get("sample", [])]
def issue(i, tag):
    return cl.post("/api/issue", json={"subject_id": f"{tag}{i:03d}@contoh.ac.id", "subject_name": f"Peserta {tag} {i}", "achievement": "Kredensial Mikro: Dasar Analitik Data",
                   "description": "Memahami dan menerapkan analitik data dasar", "criteria": "Nilai akhir >= 70 dan menyelesaikan proyek", "credits": 2, "oulad_student": stu[i % len(stu)] if stu else None}).json()
def ver(c): return cl.post("/api/verify-json", json=c).json()
def tx_reverts(fn, acct):
    try: CH.send(fn, acct); return False
    except Exception as e: return True
res = {}; creds = [issue(i, "s") for i in range(N)]
def run(name, mut, base=None):
    gagal = {}; det = 0
    for r in (base or creds):
        c = mut(copy.deepcopy(r["credential"])); v = ver(c); det += not v["valid"]
        for k, ok in v["checks"].items():
            if not ok: gagal[k] = gagal.get(k, 0) + 1
    res[name] = {"n": len(base or creds), "ditolak": det, "pemeriksaan_gagal": gagal}
run("S1 kredensial asli (kontrol)", lambda c: c)
def m_name(c): c["credentialSubject"]["name"] += " (diubah)"; return c
def m_ach(c): c["credentialSubject"]["achievement"]["name"] = "Kredensial Mikro: Analitik Data Lanjut"; return c
def m_date(c): c["validFrom"] = "2020-01-01T00:00:00Z"; return c
def m_cred(c): c["credentialSubject"]["achievement"]["creditsAvailable"] = 4; return c
def m_evid(c):
    if "evidence" in c: c["evidence"][0]["description"] = c["evidence"][0]["description"].replace("Probabilitas lulus", "Probabilitas lulus 0.99; asli")
    return c
def m_issname(c): c["issuer"]["name"] = "Universitas Lain"; return c
run("S2 nama peserta diubah", m_name); run("S3 nama capaian diubah", m_ach); run("S4 tanggal validFrom diubah", m_date)
run("S5 SKS/creditsAvailable diubah 2->4", m_cred); run("S6 deskripsi bukti analitik diubah", m_evid); run("S7 nama penerbit diubah", m_issname)
att = Account.create()
def m_sig(c):
    h = vc.cred_hash(c); from eth_account.messages import encode_defunct
    c["proof"]["signatureValue"] = "0x" + Account.sign_message(encode_defunct(primitive=h), att.key).signature.hex().removeprefix("0x"); return c
run("S8 tanda tangan diganti tanda tangan penyerang (isi sama)", m_sig)
def m_proofswap(c, other=[None]):
    c["proof"] = copy.deepcopy(creds[(creds.index(next(x for x in creds if x['credential']['id']==c['id']))+1) % N]["credential"]["proof"]); return c
run("S9 proof disalin dari kredensial lain", m_proofswap)
# S10 kredensial palsu buatan penyerang (tidak dijangkarkan), mengaku sebagai penerbit
fake = []
for i in range(N):
    c = vc.build_credential(CH.issuer.address, "Lembaga Contoh (Prototipe)", CH.chain_id, f"palsu{i}@x.id", f"Palsu {i}", "Kredensial Mikro: Dasar Analitik Data", "x", "x", 2)
    fake.append({"credential": vc.sign(c, att.key, CH.address, CH.chain_id)})
run("S10 kredensial palsu tidak terdaftar (ditandatangani penyerang)", lambda c: c, fake)
# kontrak: akses tidak sah
fund = CH.w3.eth.accounts[0]; CH.w3.eth.wait_for_transaction_receipt(CH.w3.eth.send_transaction({"from": fund, "to": att.address, "value": 10**19}))
h0 = bytes.fromhex(creds[0]["hash"][2:])
res["S11 akun tak terdaftar memanggil issue()"] = {"n": N, "ditolak": sum(tx_reverts(CH.c.functions.issue(keccak(f"a{i}".encode()), keccak(b"s")), att) for i in range(N))}
res["S12 akun lain mencabut kredensial penerbit"] = {"n": N, "ditolak": sum(tx_reverts(CH.c.functions.revoke(bytes.fromhex(r["hash"][2:]), "x"), att) for r in creds)}
res["S13 penerbitan ulang hash yang sama"] = {"n": N, "ditolak": sum(tx_reverts(CH.c.functions.issue(bytes.fromhex(r["hash"][2:]), keccak(b"s")), CH.issuer) for r in creds)}
res["S14 penyerang memanggil deactivateIssuer()"] = {"n": 1, "ditolak": int(tx_reverts(CH.c.functions.deactivateIssuer(CH.issuer.address), att))}
# Merkle
leaves = [keccak(f"m{j}".encode()) for j in range(16)]; root, proofs = vc.merkle_root_and_proofs(leaves); CH.send(CH.c.functions.anchorBatchRoot(root, 16), CH.issuer)
root2, proofs2 = vc.merkle_root_and_proofs([keccak(f"z{j}".encode()) for j in range(16)])
res["S15 Merkle: daun diubah"] = {"n": 16, "ditolak": sum(not CH.c.functions.verifyInBatch(keccak(l + b"!"), p, root).call() for l, p in zip(leaves, proofs))}
res["S16 Merkle: bukti dari kelompok lain"] = {"n": 16, "ditolak": sum(not CH.c.functions.verifyInBatch(l, p2, root).call() for l, p2 in zip(leaves, proofs2))}
res["S17 Merkle: akar tidak dijangkarkan"] = {"n": 16, "ditolak": sum(not CH.c.functions.verifyInBatch(l, p, root2).call() for l, p in zip(leaves, proofs2))}
res["S18 Merkle: daun asli + bukti asli (kontrol)"] = {"n": 16, "diterima": sum(CH.c.functions.verifyInBatch(l, p, root).call() for l, p in zip(leaves, proofs))}
# pencabutan & penonaktifan penerbit
for r in creds[:10]: cl.post("/api/revoke", json={"hash": r["hash"], "reason": "uji"})
run("S19 kredensial dicabut", lambda c: c, creds[:10])
run("S20 kredensial lain tetap sah setelah pencabutan (kontrol)", lambda c: c, creds[10:])
CH.send(CH.c.functions.deactivateIssuer(CH.issuer.address), CH.admin)
run("S21 penerbit dinonaktifkan admin", lambda c: c, creds[10:])
CH.send(CH.c.functions.addIssuer(CH.issuer.address, "Lembaga Contoh (Prototipe)"), CH.admin)
run("S22 penerbit diaktifkan kembali (kontrol)", lambda c: c, creds[10:])
# contoh terhitung
ex = issue(99, "contoh"); c = ex["credential"]; cb = vc.canonical_bytes(c)
small = [keccak(f"kredensial-{k}".encode()) for k in "ABCD"]; r4, p4 = vc.merkle_root_and_proofs(small)
hp = lambda a, b: keccak(a + b) if a < b else keccak(b + a)
steps = []; h = small[2]
for p in p4[2]: n = hp(h, p); steps.append({"saat_ini": "0x" + h.hex(), "saudara": "0x" + p.hex(), "urutan": "saat_ini||saudara" if h < p else "saudara||saat_ini", "hasil": "0x" + n.hex()}); h = n
contoh = {"vc": c, "canonical_len_bytes": len(cb), "canonical_prefix": cb[:160].decode(), "hash": ex["hash"], "gas": ex["gasUsed"],
          "abc": "0x" + keccak(b"abc").hex(), "abd": "0x" + keccak(b"abd").hex(),
          "merkle4": {"daun": {k: "0x" + x.hex() for k, x in zip("ABCD", small)}, "akar": "0x" + r4.hex(), "bukti_C": ["0x" + x.hex() for x in p4[2]], "langkah_C": steps,
                      "onchain_ok": None}}
CH.send(CH.c.functions.anchorBatchRoot(r4, 4), CH.issuer); contoh["merkle4"]["onchain_ok"] = CH.c.functions.verifyInBatch(small[2], p4[2], r4).call()
meta = {"tanggal": time.strftime("%Y-%m-%d %H:%M:%S %Z"), "python": platform.python_version(), "os": platform.platform(), "chain": CH.mode, "chainId": CH.chain_id}
json.dump({"meta": meta, "skenario": res}, open(OUT / "uji_serangan.json", "w"), indent=1, ensure_ascii=False)
json.dump({"meta": meta, **contoh}, open(OUT / "contoh_terhitung.json", "w"), indent=1, ensure_ascii=False)
print(json.dumps(res, indent=1, ensure_ascii=False)); print(json.dumps(meta))
