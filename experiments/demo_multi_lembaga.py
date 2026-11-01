"""Demo multi-lembaga (skenario HIPOTETIS untuk monograf, BUKAN implementasi nyata UMY/ICE Institute).
Dua penerbit contoh dengan kunci terpisah didaftarkan admin registri, menerbitkan kredensial mikro (tunggal & batch Merkle),
diverifikasi, diuji pemalsuan/pencabutan silang, lalu satu kredensial dicabut.
Jalankan di kontainer:  docker compose -p monograf exec app python experiments/demo_multi_lembaga.py
Tanpa node (eth-tester dalam proses):  python experiments/demo_multi_lembaga.py"""
import json, os, sys, time, copy, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "backend"))
from chain import Chain
import vc
from eth_utils import keccak

OUT = pathlib.Path(__file__).resolve().parent / "hasil"; OUT.mkdir(exist_ok=True)
LOG = []
def say(*a):
    s = " ".join(str(x) for x in a); print(s, flush=True); LOG.append(s)

def verify(ch, cred):
    h = vc.cred_hash(cred); checks = {}
    checks["hash_cocok_dengan_proof"] = cred.get("proof", {}).get("anchor", {}).get("hash") == "0x" + h.hex()
    try: signer = vc.recover_signer(cred)
    except Exception: signer = None
    exists, issuer, active, issued_at, revoked, _ = ch.c.functions.verify(h).call()
    checks["tercatat_di_blockchain"] = exists
    checks["tanda_tangan_penerbit_sah"] = bool(signer) and signer == issuer
    checks["did_penerbit_cocok"] = exists and cred["issuer"]["id"].lower().endswith(issuer.lower())
    checks["penerbit_aktif"] = active
    checks["tidak_dicabut"] = not revoked
    return all(checks.values()), checks, issuer

def tx_fails(ch, fn, acct):
    try: ch.send(fn, acct); return False
    except Exception as e: return type(e).__name__

def main():
    t0 = time.time(); ch = Chain(); res = {"mode": ch.mode, "chainId": ch.chain_id, "registry": ch.address}
    say(f"== Demo multi-lembaga (HIPOTETIS) | {ch.mode} | chainId {ch.chain_id} | registri {ch.address}")
    say("[1] Admin registri mendaftarkan dua penerbit contoh (kunci terpisah per lembaga)")
    L = {}
    for key, name in [("umy_contoh", "Universitas Muhammadiyah Yogyakarta (contoh)"), ("ice_contoh", "ICE Institute (contoh)")]:
        acct, gas = ch.ensure_issuer(key, name)
        nm, act, reg, deact = ch.c.functions.issuers(acct.address).call()
        L[key] = (acct, name); say(f"    {name}: {acct.address} | aktif={act} | gas addIssuer={gas if gas else 'sudah terdaftar'}")
        res[f"issuer_{key}"] = {"address": acct.address, "addIssuer_gas": gas, "active": act}
    umy, ice = L["umy_contoh"][0], L["ice_contoh"][0]
    did = lambda a: f"did:pkh:eip155:{ch.chain_id}:{a.address}"
    say("[2] UMY (contoh) menerbitkan 1 kredensial mikro (transaksi tunggal)")
    c = vc.build_credential(umy.address, L["umy_contoh"][1], ch.chain_id, "mhs001@contoh.ac.id", "Mahasiswa Contoh 001",
                            "Kredensial Mikro: Analitik Data Pembelajaran (contoh)", "Contoh capaian 2 SKS", "Lulus asesmen proyek", 2)
    cu = vc.sign(c, umy.key, ch.address, ch.chain_id); hu = vc.cred_hash(cu)
    t = time.perf_counter(); r = ch.send(ch.c.functions.issue(hu, keccak(b"mhs001@contoh.ac.id")), umy); ms = (time.perf_counter() - t) * 1000
    say(f"    hash 0x{hu.hex()[:16]}… | gas {r.gasUsed} | {ms:.1f} ms"); res["umy_issue"] = {"gas": r.gasUsed, "ms": round(ms, 1)}
    say("[3] ICE Institute (contoh) menerbitkan 3 kredensial dalam satu batch Merkle (anchorBatchRoot)")
    ices = [vc.sign(vc.build_credential(ice.address, L["ice_contoh"][1], ch.chain_id, f"peserta{i}@contoh.id", f"Peserta Contoh {i}",
                    "Kredensial Mikro: Keamanan Siber Dasar (contoh)", "Contoh kursus daring", "Nilai akhir >= 70"), ice.key, ch.address, ch.chain_id) for i in range(1, 4)]
    leaves = [vc.cred_hash(x) for x in ices]; root, proofs = vc.merkle_root_and_proofs(leaves)
    r = ch.send(ch.c.functions.anchorBatchRoot(root, len(leaves)), ice)
    okb = [ch.c.functions.verifyInBatch(l, p, root).call() for l, p in zip(leaves, proofs)]
    owner = ch.c.functions.batchRoots(root).call()
    say(f"    akar 0x{root.hex()[:16]}… | gas {r.gasUsed} | bukti Merkle sah {sum(okb)}/{len(okb)} | pemilik akar = ICE: {owner == ice.address}")
    res["ice_batch"] = {"gas": r.gasUsed, "n": len(leaves), "proofs_valid": sum(okb), "root_owner_is_ice": owner == ice.address}
    # salah satu kredensial ICE juga dicatat individual agar dapat diperiksa portal verifikasi
    hi = leaves[0]; ch.send(ch.c.functions.issue(hi, keccak(b"peserta1@contoh.id")), ice)
    say("[4] Verifikasi oleh pemberi kerja (5+1 pemeriksaan)")
    for lab, cr in [("UMY#1", cu), ("ICE#1", ices[0])]:
        ok, ck, iss = verify(ch, cr); say(f"    {lab}: {'SAH' if ok else 'TIDAK SAH'} | penerbit on-chain {iss[:10]}…"); res[f"verify_{lab}"] = ok
    say("[5] Uji lintas lembaga")
    forged = vc.build_credential(umy.address, L["umy_contoh"][1], ch.chain_id, "palsu@contoh.id", "Penerima Palsu",
                                 "Kredensial Mikro Palsu atas nama UMY (contoh)", "-", "-")
    fs = vc.sign(forged, ice.key, ch.address, ch.chain_id); ch.send(ch.c.functions.issue(vc.cred_hash(fs), keccak(b"palsu")), ice)
    ok, ck, _ = verify(ch, fs)
    say(f"    a) ICE menerbitkan dokumen yang mengaku dari UMY -> {'SAH' if ok else 'TIDAK SAH'} (did_penerbit_cocok={ck['did_penerbit_cocok']}, tanda_tangan_sah={ck['tanda_tangan_penerbit_sah']})")
    res["forge_detected"] = not ok
    e = tx_fails(ch, ch.c.functions.revoke(hu, "upaya cabut oleh lembaga lain"), ice)
    say(f"    b) ICE mencoba mencabut kredensial UMY -> ditolak: {bool(e)} ({e})"); res["cross_revoke_rejected"] = bool(e)
    e = tx_fails(ch, ch.c.functions.addIssuer(ice.address, "penerbit liar"), ice)
    say(f"    c) ICE mencoba mendaftarkan penerbit (bukan admin) -> ditolak: {bool(e)} ({e})"); res["non_admin_addissuer_rejected"] = bool(e)
    tam = copy.deepcopy(cu); tam["credentialSubject"]["name"] = "Nama Diubah"; ok, ck, _ = verify(ch, tam)
    say(f"    d) Dokumen UMY diubah nama penerimanya -> {'SAH' if ok else 'TIDAK SAH'}"); res["tamper_detected"] = not ok
    say("[6] UMY mencabut kredensialnya sendiri")
    r = ch.send(ch.c.functions.revoke(hu, "contoh: kesalahan data"), umy); ok, ck, _ = verify(ch, cu)
    say(f"    gas revoke {r.gasUsed} | verifikasi ulang -> {'SAH' if ok else 'TIDAK SAH'} (tidak_dicabut={ck['tidak_dicabut']})")
    res["revoke"] = {"gas": r.gasUsed, "valid_after": ok}; ok, _, _ = verify(ch, ices[0])
    say(f"    kredensial ICE#1 tetap {'SAH' if ok else 'TIDAK SAH'} (pencabutan tidak berdampak lintas lembaga)"); res["ice_still_valid"] = ok
    say("[7] Penonaktifan penerbit tidak retroaktif (perbaikan deactivatedAt)")
    ch.send(ch.c.functions.deactivateIssuer(ice.address), ch.admin)
    ok, ck, _ = verify(ch, ices[0]); e = tx_fails(ch, ch.c.functions.issue(keccak(f"baru{time.time()}".encode()), keccak(b"x")), ice)
    say(f"    ICE dinonaktifkan: kredensial lama -> {'SAH' if ok else 'TIDAK SAH'}; terbit baru ditolak: {bool(e)}")
    res["deactivation"] = {"old_still_valid": ok, "new_issue_rejected": bool(e)}
    ch.send(ch.c.functions.addIssuer(ice.address, L["ice_contoh"][1]), ch.admin); say("    (ICE diaktifkan kembali agar demo dapat diulang)")
    res["durasi_s"] = round(time.time() - t0, 2); res["tanggal"] = time.strftime("%Y-%m-%d %H:%M:%S %z")
    (OUT / "demo_multi_lembaga.json").write_text(json.dumps(res, indent=1)); (OUT / "demo_multi_lembaga.txt").write_text("\n".join(LOG) + "\n")
    say(f"== selesai dalam {res['durasi_s']} s; hasil: experiments/hasil/demo_multi_lembaga.json")

if __name__ == "__main__":
    main()
