"""Pembentukan kredensial mikro berformat W3C VC 2.0 + Open Badges 3.0 (disederhanakan untuk prototipe)."""
import json, uuid, datetime
from eth_utils import keccak
from eth_account import Account
from eth_account.messages import encode_defunct

CONTEXT = ["https://www.w3.org/ns/credentials/v2",
           "https://purl.imsglobal.org/spec/ob/v3p0/context-3.0.3.json"]

def now_iso():
    return datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")

def build_credential(issuer_addr, issuer_name, chain_id, subject_id, subject_name, ach_name, ach_desc, criteria,
                     ects=None, evidence=None):
    cred = {
        "@context": CONTEXT,
        "id": f"urn:uuid:{uuid.uuid4()}",
        "type": ["VerifiableCredential", "OpenBadgeCredential"],
        "issuer": {"id": f"did:pkh:eip155:{chain_id}:{issuer_addr}", "type": ["Profile"], "name": issuer_name},
        "validFrom": now_iso(),
        "name": ach_name,
        "credentialSubject": {
            "id": subject_id, "type": ["AchievementSubject"], "name": subject_name,
            "achievement": {"id": f"urn:uuid:{uuid.uuid4()}", "type": ["Achievement"], "name": ach_name,
                            "description": ach_desc, "criteria": {"narrative": criteria},
                            **({"creditsAvailable": ects} if ects else {})},
        },
    }
    if evidence:
        cred["evidence"] = [evidence]
    return cred

def canonical_bytes(cred):
    """Kanonikalisasi sederhana: JSON dengan kunci terurut, tanpa spasi, tanpa field 'proof'.
    Catatan: ini BUKAN RDFC/JCS penuh; cukup untuk prototipe."""
    c = {k: v for k, v in cred.items() if k != "proof"}
    return json.dumps(c, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()

def cred_hash(cred) -> bytes:
    return keccak(canonical_bytes(cred))

def sign(cred, key, contract_addr, chain_id):
    h = cred_hash(cred)
    sig = Account.sign_message(encode_defunct(primitive=h), key).signature.hex()
    cred = dict(cred)
    cred["proof"] = {"type": "BlockchainAnchorProof-Prototipe", "created": now_iso(),
                     "proofPurpose": "assertionMethod",
                     "verificationMethod": cred["issuer"]["id"],
                     "anchor": {"chainId": chain_id, "registry": contract_addr, "hash": "0x" + h.hex()},
                     "signatureValue": sig if sig.startswith("0x") else "0x" + sig}
    return cred

def recover_signer(cred):
    h = cred_hash(cred)
    return Account.recover_message(encode_defunct(primitive=h), signature=cred["proof"]["signatureValue"])

def merkle_root_and_proofs(leaves):
    """Merkle tree dengan pasangan terurut (cocok dengan verifyInBatch di kontrak)."""
    def hp(a, b):
        return keccak(a + b) if a < b else keccak(b + a)
    layers = [list(leaves)]
    while len(layers[-1]) > 1:
        cur, nxt = layers[-1], []
        for i in range(0, len(cur), 2):
            nxt.append(hp(cur[i], cur[i + 1]) if i + 1 < len(cur) else cur[i])
        layers.append(nxt)
    proofs = []
    for idx in range(len(leaves)):
        p, i = [], idx
        for layer in layers[:-1]:
            j = i ^ 1
            if j < len(layer):
                p.append(layer[j])
            i //= 2
        proofs.append(p)
    return layers[-1][0], proofs
