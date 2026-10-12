# tests/test_g2_07a_synthetic_oracle_validation.py

import pytest
from normalizer.G2_07_diff_engine import SemanticDiffEngine
from tests.G2_07A_synthetic_oracle_dataset import SYNTHETIC_ORACLE_DATASET
def test_validate_diff_engine_confusion_matrix():
    engine = SemanticDiffEngine()

    tp = 0  # True Positive: Thực tế CÓ diff -> Engine BÁO CÓ diff
    tn = 0  # True Negative: Thực tế KHÔNG diff -> Engine BÁO KHÔNG diff
    fp = 0  # False Positive: Thực tế KHÔNG diff -> Engine BÁO CÓ diff (Báo nhầm)
    fn = 0  # False Negative: Thực tế CÓ diff -> Engine BÁO KHÔNG diff (Bỏ sót)

    for case in SYNTHETIC_ORACLE_DATASET:
        diffs = engine.compare_responses(
            v1_status=case["v1"]["status"],
            v2_status=case["v2"]["status"],
            v1_headers=case["v1"]["headers"],
            v2_headers=case["v2"]["headers"],
            v1_body=case["v1"]["body"],
            v2_body=case["v2"]["body"]
        )

        detected_diff = len(diffs) > 0
        expected_diff = case["expected_has_diff"]

        if expected_diff and detected_diff:
            tp += 1
        elif not expected_diff and not detected_diff:
            tn += 1
        elif not expected_diff and detected_diff:
            fp += 1
        elif expected_diff and not detected_diff:
            fn += 1

    # In kết quả đánh giá ra màn hình
    print("\n==========================================")
    print(" SYNTHETIC ORACLE VALIDATION METRICS (G2-07A)")
    print("==========================================")
    print(f" True Positives  (TP) : {tp}")
    print(f" True Negatives  (TN) : {tn}")
    print(f" False Positives (FP) : {fp}")
    print(f" False Negatives (FN) : {fn}")
    
    total = tp + tn + fp + fn
    accuracy = (tp + tn) / total if total > 0 else 0
    print(f" Accuracy            : {accuracy * 100:.2f}%")
    print("==========================================")

    # Đảm bảo Engine đạt độ chính xác tuyệt đối (100% Accuracy, FP=0, FN=0)
    assert fp == 0, f"False Positives detected: {fp}"
    assert fn == 0, f"False Negatives detected: {fn}"
    assert accuracy == 1.0