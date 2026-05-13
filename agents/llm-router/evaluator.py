import re

# Patterns that signal the model didn't actually answer
_BAD_PATTERNS = [
    r"i\s+don'?t\s+know",
    r"i'?m\s+not\s+sure",
    r"i\s+cannot\s+(help|answer|provide|do)",
    r"i\s+can'?t\s+(help|answer|provide|do)",
    r"i\s+don'?t\s+have\s+(access|enough|the\s+information)",
    r"i'?m\s+unable\s+to",
    r"i\s+apologize[,\s]+but\s+i",
    r"as\s+an?\s+(ai|language\s+model)",
    r"i\s+don'?t\s+have\s+information\s+about",
    r"i\s+don'?t\s+have\s+the\s+ability",
]

_COMPILED = [re.compile(p, re.IGNORECASE) for p in _BAD_PATTERNS]

_JUDGE_SYSTEM = "You are a strict response quality evaluator. Reply with exactly YES or NO — nothing else."

_JUDGE_PROMPT = (
    "User question:\n{question}\n\n"
    "AI response:\n{response}\n\n"
    "Did the AI response fully and correctly answer the user's question? "
    "Reply YES or NO only."
)


class SignalDetector:
    """
    Free, instant quality gate — scans response text for failure signals.
    Returns True if the response looks satisfactory (no bad signals found).
    """

    def __init__(self, threshold: int = 1):
        self._threshold = threshold

    def ok(self, response: str, prompt: str) -> bool:
        # Too short relative to prompt complexity
        prompt_words   = len(prompt.split())
        response_words = len(response.split())
        if prompt_words > 8 and response_words < 25:
            return False

        # Uncertainty / refusal patterns
        hits = sum(1 for p in _COMPILED if p.search(response))
        if hits >= self._threshold:
            return False

        # Model asked a question back instead of answering (confused)
        stripped = response.strip()
        if stripped.endswith("?"):
            last_sentence = re.split(r"[.!]", stripped)[-1].strip()
            if len(last_sentence.split()) < 20:
                return False

        return True


class MiniJudge:
    """
    Calls the judge layer with a YES/NO prompt.
    Only invoked when SignalDetector finds problems — keeps cost near zero.
    """

    def __init__(self, judge_layer, max_tokens: int = 50):
        self._layer      = judge_layer
        self._max_tokens = max_tokens

    def ok(self, prompt: str, response: str) -> bool:
        question = _JUDGE_PROMPT.format(
            question=prompt[:600],
            response=response[:1200],
        )
        try:
            # Temporarily override max_tokens for this tiny call
            orig = self._layer.max_tokens
            self._layer.max_tokens = self._max_tokens
            verdict = self._layer.text_complete(
                system=_JUDGE_SYSTEM,
                messages=[{"role": "user", "content": question}],
            )
            self._layer.max_tokens = orig
            return verdict.strip().upper().startswith("YES")
        except Exception:
            return True  # judge failed → assume ok to avoid infinite escalation
