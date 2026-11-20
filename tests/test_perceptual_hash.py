from backend.risk_scorer import PerceptualHashCollisionDetector


def test_hamming_distance_and_similarity():
    h1 = 0x8F3C4E2A1B9D7056
    # Exact match
    assert PerceptualHashCollisionDetector.hamming_distance(h1, h1) == 0
    assert PerceptualHashCollisionDetector.compute_similarity(h1, h1) == 1.0

    # Flip 3 bits
    h2 = h1 ^ (1 << 3) ^ (1 << 18) ^ (1 << 45)
    assert PerceptualHashCollisionDetector.hamming_distance(h1, h2) == 3
    expected_sim = round(1.0 - (3.0 / 64.0), 4)
    assert PerceptualHashCollisionDetector.compute_similarity(h1, h2) == expected_sim

    # Hex string input support
    assert (
        PerceptualHashCollisionDetector.hamming_distance("0x8f3c4e2a1b9d7056", hex(h2))
        == 3
    )


def test_unique_document_registration():
    detector = PerceptualHashCollisionDetector()
    res = detector.register_and_scan("user_alpha", "img_001", 0x1122334455667788)
    assert res["entity_id"] == "user_alpha"
    assert res["duplicate_detected"] is False
    assert res["collision_count"] == 0
    assert res["severity_tier"] == "LOW_RISK"
    assert res["duplicate_risk_score"] == 0.0
    assert res["collision_flag"] == "UNIQUE_DOCUMENT"


def test_identical_document_reuse_across_accounts():
    detector = PerceptualHashCollisionDetector()
    hash_val = 0xAABBCCDDEEFF0011

    # User 1 registers invoice
    detector.register_and_scan("user_legit", "invoice_001.png", hash_val)

    # User 2 attempts to claim with exact same invoice hash
    res = detector.register_and_scan("user_fraudster", "invoice_copy.png", hash_val)
    assert res["duplicate_detected"] is True
    assert res["collision_count"] == 1
    assert res["nearest_collision_distance"] == 0
    assert res["severity_tier"] == "CRITICAL_FRAUD"
    assert res["duplicate_risk_score"] >= 0.90
    assert "IDENTICAL_DOCUMENT_REUSE_DETECTED" in res["collision_flag"]
    assert res["top_collisions"][0]["matched_entity_id"] == "user_legit"


def test_near_duplicate_perturbed_image():
    detector = PerceptualHashCollisionDetector(max_collision_hamming_distance=10)
    orig_hash = 0x1234567890ABCDEF
    # Simulate slight cropping / compression adding 4 bit flips
    perturbed_hash = orig_hash ^ (1 << 1) ^ (1 << 10) ^ (1 << 25) ^ (1 << 50)

    detector.register_and_scan("merchant_a", "receipt_scan.jpg", orig_hash)
    res = detector.register_and_scan("merchant_b", "receipt_cropped.jpg", perturbed_hash)

    assert res["duplicate_detected"] is True
    assert res["nearest_collision_distance"] == 4
    assert res["severity_tier"] == "HIGH_RISK"
    assert res["duplicate_risk_score"] >= 0.60
    assert "NEAR_DUPLICATE_IMAGE_COLLISION" in res["collision_flag"]


def test_same_entity_retry_upload_is_not_cross_fraud():
    detector = PerceptualHashCollisionDetector()
    hash_val = 0x5555AAAA5555AAAA

    # First attempt
    detector.register_and_scan("user_retry", "doc_v1.png", hash_val)

    # User re-uploads their own document
    res = detector.register_and_scan("user_retry", "doc_v2.png", hash_val)
    assert res["duplicate_detected"] is False
    assert res["collision_count"] == 0
    assert res["severity_tier"] == "SUSPICIOUS"
    assert res["collision_flag"] == "SELF_RETRY_DUPLICATE_UPLOAD"


def test_collision_ranking_order():
    detector = PerceptualHashCollisionDetector(max_collision_hamming_distance=15)
    base_hash = 0x0F0F0F0F0F0F0F0F

    # Register distant match (8 bit flips)
    detector.register_and_scan("user_far", "img_far", base_hash ^ 0xFF)
    # Register closer match (2 bit flips)
    detector.register_and_scan("user_close", "img_close", base_hash ^ 0x03)

    # Query with base hash
    res = detector.register_and_scan("user_query", "img_query", base_hash)
    assert res["collision_count"] == 2
    # Verify closest match is ranked first
    assert res["top_collisions"][0]["matched_entity_id"] == "user_close"
    assert res["top_collisions"][0]["hamming_distance"] == 2
    assert res["top_collisions"][1]["matched_entity_id"] == "user_far"
    assert res["top_collisions"][1]["hamming_distance"] == 8
