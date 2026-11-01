"""Koneksi blockchain: RPC lokal (Hardhat/Anvil/Ganache) via CHAIN_RPC, atau eth-tester dalam proses (tanpa instalasi)."""
import json, os, pathlib, time
from web3 import Web3
from eth_account import Account

ROOT = pathlib.Path(__file__).resolve().parent
DATA = pathlib.Path(os.environ.get("DATA_DIR", ROOT.parent / "data"))
DATA.mkdir(parents=True, exist_ok=True)

def load_artifact():
    p = ROOT / "build" / "CredentialRegistry.json"
    if not p.exists():
        from compile_contract import compile_contract
        return compile_contract()
    return json.loads(p.read_text())

def connect():
    rpc = os.environ.get("CHAIN_RPC")
    if rpc:
        w3 = Web3(Web3.HTTPProvider(rpc, request_kwargs={"timeout": 30}))
        for _ in range(60):
            if w3.is_connected():
                break
            time.sleep(1)
        mode = f"rpc:{rpc}"
    else:
        from web3.providers.eth_tester import EthereumTesterProvider
        w3 = Web3(EthereumTesterProvider()); mode = "eth-tester (dalam proses)"
    return w3, mode

def _local_key(name):
    """Kunci khusus pengembangan, dibuat acak saat pertama dijalankan dan disimpan lokal di data/ (JANGAN dipakai di jaringan publik)."""
    p = DATA / f"devkey_{name}.txt"
    if p.exists():
        return p.read_text().strip()
    k = Account.create().key.hex()
    p.write_text(k); return k

class Chain:
    def __init__(self):
        self.w3, self.mode = connect()
        self.art = load_artifact()
        self.chain_id = self.w3.eth.chain_id
        funder = self.w3.eth.accounts[0]
        self.admin = Account.from_key(_local_key("admin"))
        self.issuer = Account.from_key(_local_key("issuer"))
        for a in (self.admin, self.issuer):
            if self.w3.eth.get_balance(a.address) < Web3.to_wei(10, "ether"):
                tx = self.w3.eth.send_transaction({"from": funder, "to": a.address, "value": Web3.to_wei(100, "ether")})
                self.w3.eth.wait_for_transaction_receipt(tx)
        addr_file = DATA / f"contract_{self.chain_id}.txt"
        addr = addr_file.read_text().strip() if addr_file.exists() else None
        if not addr or self.w3.eth.get_code(addr) in (b"", b"\x00"):
            C = self.w3.eth.contract(abi=self.art["abi"], bytecode=self.art["bytecode"])
            rcpt = self.send(C.constructor(), self.admin)
            addr = rcpt.contractAddress; addr_file.write_text(addr)
            self.deploy_gas = rcpt.gasUsed
            self.c = self.w3.eth.contract(address=addr, abi=self.art["abi"])
            self.send(self.c.functions.addIssuer(self.issuer.address, os.environ.get("ISSUER_NAME", "Lembaga Contoh (Prototipe)")), self.admin)
        else:
            self.deploy_gas = None
        self.c = self.w3.eth.contract(address=addr, abi=self.art["abi"])
        self.address = addr

    def ensure_issuer(self, keyname, display_name):
        """v3: siapkan akun penerbit tambahan (kunci terpisah per lembaga) dan daftarkan oleh admin bila belum aktif."""
        acct = Account.from_key(_local_key(keyname))
        if self.w3.eth.get_balance(acct.address) < Web3.to_wei(10, "ether"):
            tx = self.w3.eth.send_transaction({"from": self.w3.eth.accounts[0], "to": acct.address, "value": Web3.to_wei(100, "ether")})
            self.w3.eth.wait_for_transaction_receipt(tx)
        gas = None
        if not self.c.functions.issuers(acct.address).call()[1]:
            gas = self.send(self.c.functions.addIssuer(acct.address, display_name), self.admin).gasUsed
        return acct, gas

    def send(self, fn, acct):
        tx = fn.build_transaction({"from": acct.address, "nonce": self.w3.eth.get_transaction_count(acct.address),
                                   "chainId": self.chain_id})
        if "gas" not in tx:
            tx["gas"] = self.w3.eth.estimate_gas(tx)
        signed = acct.sign_transaction(tx)
        h = self.w3.eth.send_raw_transaction(signed.raw_transaction)
        r = self.w3.eth.wait_for_transaction_receipt(h)
        if r.status != 1:
            raise RuntimeError("transaksi gagal")
        return r
