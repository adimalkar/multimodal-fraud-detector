from backend.risk_scorer import EntityCollusionDetector


def test_collusion_detector_isolated_entity():
    detector = EntityCollusionDetector()
    detector.register_entity(
        "user_1", {"ip": "10.0.0.1", "device_id": "dev_1"}, base_risk=0.20
    )

    neighbors, shared = detector.get_neighbors("user_1")
    assert len(neighbors) == 0
    assert len(shared) == 0

    rings = detector.detect_collusion_rings()
    assert len(rings) == 0

    risk_prof = detector.compute_propagated_risk("user_1")
    assert risk_prof["base_risk"] == 0.20
    assert risk_prof["propagated_risk"] == 0.20
    assert risk_prof["network_risk_boost"] == 0.0
    assert not risk_prof["syndicate_flagged"]


def test_collusion_ring_detection_two_nodes():
    detector = EntityCollusionDetector()
    # user_a and user_b share an IP and a device fingerprint
    detector.register_entity(
        "user_a", {"ip": "192.168.1.100", "device_fp": "fp_alpha"}, base_risk=0.85
    )
    detector.register_entity(
        "user_b", {"ip": "192.168.1.100", "device_fp": "fp_alpha"}, base_risk=0.15
    )

    neighbors_a, shared_a = detector.get_neighbors("user_a")
    assert neighbors_a == {"user_b"}
    assert "device_fp:fp_alpha" in shared_a
    assert "ip:192.168.1.100" in shared_a

    rings = detector.detect_collusion_rings()
    assert len(rings) == 1
    ring = rings[0]
    assert ring["size"] == 2
    assert ring["entities"] == ["user_a", "user_b"]
    assert ring["max_base_risk"] == 0.85
    assert ring["is_syndicate"] is True
    assert ring["syndicate_risk_penalty"] > 0.0


def test_propagated_risk_elevation():
    detector = EntityCollusionDetector(damping_factor=0.30)
    # user_innocent has low base risk 0.10, but shares credentials with a critical fraudster (0.90)
    detector.register_entity(
        "fraudster",
        {"device_fp": "bad_dev", "bank_hash": "routing_xyz"},
        base_risk=0.90,
    )
    detector.register_entity(
        "innocent_proxy",
        {"device_fp": "bad_dev", "bank_hash": "routing_xyz"},
        base_risk=0.10,
    )

    risk_innocent = detector.compute_propagated_risk("innocent_proxy")
    assert risk_innocent["base_risk"] == 0.10
    assert risk_innocent["propagated_risk"] > 0.10
    assert risk_innocent["network_risk_boost"] > 0.0
    assert risk_innocent["syndicate_flagged"] is True


def test_multi_node_cluster_ring():
    detector = EntityCollusionDetector()
    detector.register_entity("node_1", {"ip": "1.1.1.1"}, base_risk=0.40)
    detector.register_entity(
        "node_2", {"ip": "1.1.1.1", "device": "d2"}, base_risk=0.50
    )
    detector.register_entity("node_3", {"device": "d2"}, base_risk=0.75)

    rings = detector.detect_collusion_rings()
    assert len(rings) == 1
    ring = rings[0]
    assert ring["size"] == 3
    assert ring["entities"] == ["node_1", "node_2", "node_3"]
    assert ring["is_syndicate"] is True


def test_unregistered_entity_query():
    detector = EntityCollusionDetector()
    risk_prof = detector.compute_propagated_risk("ghost_user")
    assert risk_prof["entity_id"] == "ghost_user"
    assert risk_prof["propagated_risk"] == 0.0
    assert risk_prof["neighbor_count"] == 0
