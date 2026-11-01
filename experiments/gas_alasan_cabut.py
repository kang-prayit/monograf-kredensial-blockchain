"""Gas revoke() vs panjang alasan pencabutan (alasan hanya dipancarkan di event). eth-tester dalam proses; n=10 per panjang."""
import os, sys, json, tempfile, pathlib, statistics as st, time
os.environ.setdefault("DATA_DIR", tempfile.mkdtemp()); sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "backend"))
from chain import Chain; from eth_utils import keccak
ch = Chain(); out = {}
for L in [0, 16, 64, 128, 256, 512]:
    g = []
    for i in range(10):
        h = keccak(f"r{L}-{i}".encode()); ch.send(ch.c.functions.issue(h, keccak(b"s")), ch.issuer)
        g.append(ch.send(ch.c.functions.revoke(h, "x" * L), ch.issuer).gasUsed)
    out[L] = {"n": 10, "median": st.median(g), "min": min(g), "max": max(g)}
json.dump({"tanggal": time.strftime("%Y-%m-%d %H:%M:%S %Z"), "chain": ch.mode, "hasil": out}, open(pathlib.Path(__file__).parent / "hasil/gas_alasan_cabut.json", "w"), indent=1)
print(out)
