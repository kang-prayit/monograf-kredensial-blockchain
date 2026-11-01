"""Unit test smart contract CredentialRegistry (pytest + eth-tester, tanpa node eksternal)."""
import sys, pathlib, pytest
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "backend"))
from web3 import Web3
from web3.providers.eth_tester import EthereumTesterProvider
from web3.exceptions import ContractLogicError as _CLE
from eth_tester.exceptions import TransactionFailed
ContractLogicError = (_CLE, TransactionFailed)
from eth_utils import keccak
from chain import load_artifact
import vc

@pytest.fixture
def env():
    w3 = Web3(EthereumTesterProvider()); a = w3.eth.accounts; art = load_artifact()
    C = w3.eth.contract(abi=art["abi"], bytecode=art["bytecode"])
    addr = w3.eth.wait_for_transaction_receipt(C.constructor().transact({"from": a[0]})).contractAddress
    c = w3.eth.contract(address=addr, abi=art["abi"])
    c.functions.addIssuer(a[1], "Polines (uji)").transact({"from": a[0]})
    return w3, c, a

H = keccak(b"kredensial-1"); S = keccak(b"peserta")

def test_admin_and_issuer(env):
    w3, c, a = env
    assert c.functions.admin().call() == a[0]
    assert c.functions.issuers(a[1]).call()[1] is True

def test_only_admin_adds_issuer(env):
    w3, c, a = env
    with pytest.raises(ContractLogicError):
        c.functions.addIssuer(a[2], "liar").transact({"from": a[2]})

def test_issue_and_verify(env):
    w3, c, a = env
    c.functions.issue(H, S).transact({"from": a[1]})
    ex, iss, act, t, rev, _ = c.functions.verify(H).call()
    assert ex and iss == a[1] and act and t > 0 and not rev

def test_non_issuer_cannot_issue(env):
    w3, c, a = env
    with pytest.raises(ContractLogicError):
        c.functions.issue(H, S).transact({"from": a[3]})

def test_no_duplicate(env):
    w3, c, a = env
    c.functions.issue(H, S).transact({"from": a[1]})
    with pytest.raises(ContractLogicError):
        c.functions.issue(H, S).transact({"from": a[1]})

def test_revoke_only_original_issuer(env):
    w3, c, a = env
    c.functions.addIssuer(a[2], "lain").transact({"from": a[0]})
    c.functions.issue(H, S).transact({"from": a[1]})
    with pytest.raises(ContractLogicError):
        c.functions.revoke(H, "x").transact({"from": a[2]})
    c.functions.revoke(H, "salah data").transact({"from": a[1]})
    assert c.functions.verify(H).call()[4] is True
    with pytest.raises(ContractLogicError):
        c.functions.revoke(H, "lagi").transact({"from": a[1]})

def test_unknown_credential(env):
    w3, c, a = env
    assert c.functions.verify(keccak(b"tidak-ada")).call()[0] is False

def test_deactivated_issuer(env):
    """v3 (deactivatedAt): kredensial lama tetap sah setelah penerbit dinonaktifkan; penerbitan baru ditolak."""
    w3, c, a = env
    c.functions.issue(H, S).transact({"from": a[1]})
    c.functions.deactivateIssuer(a[1]).transact({"from": a[0]})
    assert c.functions.verify(H).call()[2] is True
    assert c.functions.issuers(a[1]).call()[3] > 0
    with pytest.raises(ContractLogicError):
        c.functions.issue(keccak(b"k2"), S).transact({"from": a[1]})

def test_reactivated_issuer_resets_deactivation(env):
    w3, c, a = env
    c.functions.deactivateIssuer(a[1]).transact({"from": a[0]})
    c.functions.addIssuer(a[1], "Polines (aktif lagi)").transact({"from": a[0]})
    assert c.functions.issuers(a[1]).call()[3] == 0
    c.functions.issue(H, S).transact({"from": a[1]})
    assert c.functions.verify(H).call()[2] is True

def test_multi_issuer_isolation(env):
    """Dua lembaga: masing-masing hanya dapat mencabut kredensialnya sendiri; non-admin tak dapat menambah penerbit."""
    w3, c, a = env
    c.functions.addIssuer(a[2], "Lembaga B (uji)").transact({"from": a[0]})
    hA, hB = keccak(b"A-1"), keccak(b"B-1")
    c.functions.issue(hA, S).transact({"from": a[1]}); c.functions.issue(hB, S).transact({"from": a[2]})
    assert c.functions.verify(hA).call()[1] == a[1] and c.functions.verify(hB).call()[1] == a[2]
    with pytest.raises(ContractLogicError):
        c.functions.revoke(hA, "x").transact({"from": a[2]})
    with pytest.raises(ContractLogicError):
        c.functions.addIssuer(a[3], "liar").transact({"from": a[1]})
    c.functions.revoke(hB, "uji").transact({"from": a[2]})
    assert c.functions.verify(hB).call()[4] is True and c.functions.verify(hA).call()[4] is False

def test_forged_issuer_claim_detected():
    """Lembaga B menandatangani dokumen yang mengaku diterbitkan Lembaga A: DID tak cocok dengan penanda tangan."""
    from eth_account import Account
    A, B = Account.create(), Account.create()
    cred = vc.build_credential(A.address, "Lembaga A", 1, "s@x", "S", "Capaian", "d", "k")
    forged = vc.sign(cred, B.key, "0x0", 1)
    signer = vc.recover_signer(forged)
    assert signer == B.address and not forged["issuer"]["id"].lower().endswith(signer.lower())

def test_merkle_batch(env):
    w3, c, a = env
    leaves = [keccak(f"k{i}".encode()) for i in range(7)]
    root, proofs = vc.merkle_root_and_proofs(leaves)
    c.functions.anchorBatchRoot(root, 7).transact({"from": a[1]})
    assert all(c.functions.verifyInBatch(l, p, root).call() for l, p in zip(leaves, proofs))
    assert not c.functions.verifyInBatch(keccak(b"palsu"), proofs[0], root).call()

def test_vc_signature_and_tamper():
    from eth_account import Account
    acct = Account.create()
    cred = vc.build_credential(acct.address, "Uji", 1, "s@x", "S", "Capaian", "d", "k")
    signed = vc.sign(cred, acct.key, "0x0", 1)
    assert vc.recover_signer(signed) == acct.address
    signed["credentialSubject"]["name"] = "Diubah"
    assert vc.recover_signer(signed) != acct.address
