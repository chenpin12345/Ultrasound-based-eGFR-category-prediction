from backend.app.core.splitting import CLASS_NAMES, class_for_egfr, detect_label, deterministic_stratified_split


def test_exact_label_and_egfr_boundaries():
    assert detect_label("root/eGFR 30-59/a.jpg")[:2] == (2, "eGFR 30-59")
    assert detect_label("97.8_1.jpg") == (4, "eGFR 90-", 97.8)
    assert detect_label("unknown.jpg", {"matched_eGFR": "14.99"}) == (0, "eGFR -15", 14.99)
    assert [class_for_egfr(value)[0] for value in (14.99, 15, 29.99, 30, 59.99, 60, 89.99, 90)] == [0, 1, 1, 2, 2, 3, 3, 4]


def test_stratified_split_and_folds_are_deterministic():
    samples = [(f"c{label}-{index}", label) for label in range(5) for index in range(20)]
    first = deterministic_stratified_split(samples, seed=123, k_folds=5)
    second = deterministic_stratified_split(reversed(samples), seed=123, k_folds=5)
    assert first == second
    by_id = {item.sample_id: item for item in first}
    for label in range(5):
        assignments = [by_id[f"c{label}-{index}"] for index in range(20)]
        assert {item.split for item in assignments} == {"train", "validation", "test"}
        assert {item.fold for item in assignments} == {0, 1, 2, 3, 4}


def test_duplicate_hash_group_never_crosses_split_or_fold():
    samples = [
        ("original", 2, "same-sha256"),
        ("duplicate", 2, "same-sha256"),
        *((f"other-{index}", 2, f"hash-{index}") for index in range(12)),
    ]
    assignments = {item.sample_id: item for item in deterministic_stratified_split(samples, seed=9, k_folds=3)}
    assert assignments["original"].split == assignments["duplicate"].split
    assert assignments["original"].fold == assignments["duplicate"].fold
