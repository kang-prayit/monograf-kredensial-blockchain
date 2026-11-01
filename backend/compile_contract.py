"""Kompilasi kontrak Solidity menjadi artefak ABI+bytecode (backend/build/CredentialRegistry.json)."""
import json, pathlib, solcx
ROOT = pathlib.Path(__file__).resolve().parent
SRC = ROOT.parent / "contracts" / "CredentialRegistry.sol"
VER = "0.8.24"

def compile_contract():
    if VER not in [str(v) for v in solcx.get_installed_solc_versions()]:
        solcx.install_solc(VER)
    out = solcx.compile_files([str(SRC)], output_values=["abi", "bin"], solc_version=VER, optimize=True, optimize_runs=200)
    key = [k for k in out if k.endswith(":CredentialRegistry")][0]
    art = {"abi": out[key]["abi"], "bytecode": "0x" + out[key]["bin"], "solc": VER}
    (ROOT / "build").mkdir(exist_ok=True)
    (ROOT / "build" / "CredentialRegistry.json").write_text(json.dumps(art, indent=1))
    return art

if __name__ == "__main__":
    a = compile_contract(); print("bytecode bytes:", len(a["bytecode"]) // 2 - 1)
