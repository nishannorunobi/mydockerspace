class PreClassifier:
    """
    Keyword-based prompt classifier — zero cost, zero latency.
    Returns 0 (local), 1 (fast), or 2 (smart) as the recommended start layer index.
    """

    def __init__(self, cfg: dict):
        self._l1 = set(w.lower() for w in cfg.get("layer1_keywords", []))
        self._l2 = set(w.lower() for w in cfg.get("layer2_keywords", []))
        self._l3 = set(w.lower() for w in cfg.get("layer3_keywords", []))

    def classify(self, prompt: str) -> int:
        words = set(prompt.lower().split())
        # Check most complex first — l3 wins over l2 wins over l1
        if words & self._l3:
            return 2
        if words & self._l2:
            return 1
        return 0
