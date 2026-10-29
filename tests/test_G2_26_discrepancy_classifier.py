from normalizer.G2_26_discrepancy_classifier import DiscrepancyClassifier, DiscrepancyCategory

def test_classify_dynamic_noise():
    classifier = DiscrepancyClassifier()
    diff = {"path": "headers.date", "message": "Header value mismatch", "category": "HEADER"}
    assert classifier.classify(diff) == DiscrepancyCategory.DYNAMIC_NOISE

def test_classify_breaking_change():
    classifier = DiscrepancyClassifier()
    diff = {"path": "users.id", "message": "Type mismatch at $.users[0].id", "category": "TYPE_MISMATCH"}
    assert classifier.classify(diff) == DiscrepancyCategory.API_CONTRACT_BREAKING_CHANGE