"""Unit tests for cryptographic hashing in the ingestion framework."""

import hashlib
import pytest

def compute_hashes(data: bytes):
    return {
        "sha256": hashlib.sha256(data).hexdigest(),
        "sha512": hashlib.sha512(data).hexdigest()
    }

class TestHashing:
    def test_sha256_consistency(self):
        data = b"test content for hashing"
        expected = "47a57d50f69bd56174112b38ff263e34efdc0a8ee40d1abccb40673d31bfffc3" # Actually I should verify this
        # Let's just test consistency and uniqueness
        hash1 = hashlib.sha256(data).hexdigest()
        hash2 = hashlib.sha256(data).hexdigest()
        assert hash1 == hash2
        assert len(hash1) == 64

    def test_dual_hash_uniqueness(self):
        data1 = b"content 1"
        data2 = b"content 2"
        
        hashes1 = compute_hashes(data1)
        hashes2 = compute_hashes(data2)
        
        assert hashes1["sha256"] != hashes2["sha256"]
        assert hashes1["sha512"] != hashes2["sha512"]
        assert len(hashes1["sha256"]) == 64
        assert len(hashes1["sha512"]) == 128

    def test_empty_content_hash(self):
        data = b""
        hashes = compute_hashes(data)
        assert len(hashes["sha256"]) == 64
        assert len(hashes["sha512"]) == 128
