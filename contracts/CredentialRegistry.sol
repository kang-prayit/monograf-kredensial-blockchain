// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

/// @title CredentialRegistry — registri jangkar hash kredensial mikro (prototipe monograf)
/// @notice Menyimpan hanya hash (bytes32) kredensial; dokumen kredensial lengkap disimpan di luar rantai.
contract CredentialRegistry {
    struct Issuer { string name; bool active; uint64 registeredAt; uint64 deactivatedAt; }
    struct Record { address issuer; uint64 issuedAt; uint64 revokedAt; bytes32 subjectRef; }

    address public admin;
    mapping(address => Issuer) public issuers;
    mapping(bytes32 => Record) private records;
    mapping(bytes32 => address) public batchRoots; // akar Merkle -> penerbit

    event IssuerAdded(address indexed issuer, string name);
    event IssuerDeactivated(address indexed issuer);
    event CredentialIssued(bytes32 indexed credHash, address indexed issuer, bytes32 subjectRef);
    event CredentialRevoked(bytes32 indexed credHash, address indexed issuer, string reason);
    event BatchAnchored(bytes32 indexed root, address indexed issuer, uint256 size);

    error NotAdmin(); error NotActiveIssuer(); error AlreadyExists(); error UnknownCredential();
    error NotOriginalIssuer(); error AlreadyRevoked();

    modifier onlyAdmin() { if (msg.sender != admin) revert NotAdmin(); _; }
    modifier onlyIssuer() { if (!issuers[msg.sender].active) revert NotActiveIssuer(); _; }

    constructor() { admin = msg.sender; }

    function addIssuer(address issuer, string calldata name) external onlyAdmin {
        issuers[issuer] = Issuer(name, true, uint64(block.timestamp), 0);
        emit IssuerAdded(issuer, name);
    }

    function deactivateIssuer(address issuer) external onlyAdmin {
        issuers[issuer].active = false;
        issuers[issuer].deactivatedAt = uint64(block.timestamp); // v3: catat waktu penonaktifan
        emit IssuerDeactivated(issuer);
    }

    function issue(bytes32 credHash, bytes32 subjectRef) external onlyIssuer {
        if (records[credHash].issuedAt != 0) revert AlreadyExists();
        records[credHash] = Record(msg.sender, uint64(block.timestamp), 0, subjectRef);
        emit CredentialIssued(credHash, msg.sender, subjectRef);
    }

    function issueBatch(bytes32[] calldata hashes, bytes32 subjectRef) external onlyIssuer {
        for (uint256 i = 0; i < hashes.length; i++) {
            if (records[hashes[i]].issuedAt != 0) revert AlreadyExists();
            records[hashes[i]] = Record(msg.sender, uint64(block.timestamp), 0, subjectRef);
            emit CredentialIssued(hashes[i], msg.sender, subjectRef);
        }
    }

    /// @notice Menjangkarkan akar Merkle sekelompok kredensial (satu transaksi untuk banyak kredensial).
    function anchorBatchRoot(bytes32 root, uint256 size) external onlyIssuer {
        if (batchRoots[root] != address(0)) revert AlreadyExists();
        batchRoots[root] = msg.sender;
        emit BatchAnchored(root, msg.sender, size);
    }

    function revoke(bytes32 credHash, string calldata reason) external {
        Record storage r = records[credHash];
        if (r.issuedAt == 0) revert UnknownCredential();
        if (r.issuer != msg.sender) revert NotOriginalIssuer();
        if (r.revokedAt != 0) revert AlreadyRevoked();
        r.revokedAt = uint64(block.timestamp);
        emit CredentialRevoked(credHash, msg.sender, reason);
    }

    function verify(bytes32 credHash) external view returns (
        bool exists, address issuer, bool issuerActive, uint64 issuedAt, bool revoked, uint64 revokedAt
    ) {
        Record memory r = records[credHash];
        exists = r.issuedAt != 0;
        issuer = r.issuer;
        // v3: penerbit dianggap sah bila masih aktif ATAU kredensial terbit sebelum penerbit dinonaktifkan
        // (penonaktifan tidak lagi membatalkan kredensial lama secara retroaktif).
        Issuer memory i = issuers[r.issuer];
        issuerActive = exists && (i.active || (i.deactivatedAt != 0 && r.issuedAt < i.deactivatedAt));
        issuedAt = r.issuedAt;
        revoked = r.revokedAt != 0;
        revokedAt = r.revokedAt;
    }

    /// @notice Verifikasi bukti keanggotaan Merkle (pasangan diurutkan) terhadap akar yang dijangkarkan.
    function verifyInBatch(bytes32 leaf, bytes32[] calldata proof, bytes32 root) external view returns (bool) {
        if (batchRoots[root] == address(0)) return false;
        bytes32 h = leaf;
        for (uint256 i = 0; i < proof.length; i++) {
            bytes32 p = proof[i];
            h = h < p ? keccak256(abi.encodePacked(h, p)) : keccak256(abi.encodePacked(p, h));
        }
        return h == root;
    }
}
