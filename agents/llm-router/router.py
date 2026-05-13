"""
LLMRouter — cascade multi-layer routing with quality evaluation.

Two public entry points:

  router.agent_run(...)   — full agentic loop (tool calls, websocket callbacks).
                            Used by workspace-agent, docker-agent, orchestrator.

  router.text_complete()  — simple text Q&A, includes Ollama as Layer 1.
                            Used for plain chat without tools.
"""

import json
import os
from pathlib import Path
from typing import Callable, Optional

import yaml

from classifier import PreClassifier
from evaluator  import SignalDetector, MiniJudge
from layers     import OllamaLayer, AnthropicLayer

_DEFAULT_CFG = Path(__file__).parent / "router.yaml"
_SINGLETON: "LLMRouter | None" = None


def get_router(config_path: str | Path = _DEFAULT_CFG) -> "LLMRouter":
    """Return the process-level singleton router."""
    global _SINGLETON
    if _SINGLETON is None:
        _SINGLETON = LLMRouter(config_path)
    return _SINGLETON


class LLMRouter:

    def __init__(self, config_path: str | Path = _DEFAULT_CFG):
        with open(config_path) as f:
            self._cfg = yaml.safe_load(f)

        api_key = os.environ.get("ANTHROPIC_API_KEY", "")

        self._all_layers = []
        for lcfg in self._cfg.get("layers", []):
            if not lcfg.get("enabled", True):
                continue
            if lcfg["type"] == "ollama":
                self._all_layers.append(OllamaLayer(lcfg))
            elif lcfg["type"] == "anthropic":
                self._all_layers.append(AnthropicLayer(lcfg, api_key))

        self._by_name     = {l.name: l for l in self._all_layers}
        self._classifier  = PreClassifier(self._cfg.get("complexity", {}))
        self._signals     = SignalDetector(self._cfg.get("routing", {}).get("signal_threshold", 1))
        self._judge_toks  = self._cfg.get("routing", {}).get("judge_max_tokens", 50)
        self._write_tools = set(self._cfg.get("write_tools", []))

    # ── helpers ────────────────────────────────────────────────────────────────

    def _last_user_msg(self, messages: list) -> str:
        for m in reversed(messages):
            if m.get("role") == "user":
                c = m.get("content", "")
                if isinstance(c, str):
                    return c
                if isinstance(c, list):
                    for b in c:
                        if isinstance(b, dict) and b.get("type") == "text":
                            return b.get("text", "")
        return ""

    def _evaluate(self, response: str, prompt: str, layer) -> bool:
        """Return True if response is good enough (no escalation needed)."""
        if self._signals.ok(response, prompt):
            return True
        judge_name = layer.judge
        if not judge_name or judge_name == "user":
            return False  # caller handles user-judge
        judge = self._by_name.get(judge_name)
        if judge and judge.is_available():
            return MiniJudge(judge, self._judge_toks).ok(prompt, response)
        return True  # judge unavailable → accept

    def _tool_layers(self) -> list:
        """Layers that support tool calls, in order, available only."""
        return [l for l in self._all_layers if l.supports_tools and l.is_available()]

    def _text_layers(self) -> list:
        """All layers available for text completion."""
        return [l for l in self._all_layers if l.is_available()]

    # ── public: simple text ────────────────────────────────────────────────────

    def text_complete(self, system: str, messages: list) -> str:
        """
        Route a plain text completion through layers.
        Includes Ollama (Layer 1) if available.
        Escalates on bad signal or judge rejection.
        """
        prompt    = self._last_user_msg(messages)
        available = self._text_layers()
        if not available:
            raise RuntimeError("No LLM layers available")

        start = min(self._classifier.classify(prompt), len(available) - 1)
        last  = ""

        for i in range(start, len(available)):
            layer = available[i]
            try:
                last = layer.text_complete(system, messages)
            except Exception:
                continue

            if not last.strip():
                continue

            if self._evaluate(last, prompt, layer):
                return last

            if layer.judge == "user":
                break  # caller handles user-judge; return best we have

        return last

    # ── public: agentic loop ───────────────────────────────────────────────────

    def agent_run(
        self,
        system:   str,
        messages: list,
        tools:    list,
        tool_executor: Callable,
        *,
        on_text:        Optional[Callable[[str], None]]        = None,
        on_tool_call:   Optional[Callable[[object], None]]     = None,
        on_tool_result: Optional[Callable[[object, any], None]]= None,
        user_judge_callback: Optional[Callable[[str], tuple[bool, str]]] = None,
    ) -> tuple[str, list]:
        """
        Run a complete agentic loop (tool-call capable) with layer routing.

        - Pre-classifies prompt → picks Haiku or Sonnet as start layer.
        - Runs full while-True tool loop with selected layer.
        - Post-evaluates final response via SignalDetector → MiniJudge.
        - Escalates to next layer if quality is poor AND no write tools ran.
        - If at Layer 3 (Sonnet) and still poor → fires user_judge_callback.

        Returns (final_response_text, updated_history).
        """
        prompt    = self._last_user_msg(messages)
        available = self._tool_layers()
        if not available:
            raise RuntimeError("No tool-capable LLM layers available")

        # For tool-based calls always start at Haiku minimum (index 0 in tool layers)
        raw_start = self._classifier.classify(prompt)
        # tool layers list only has Anthropic layers; map classifier index
        start = min(max(raw_start - 1, 0), len(available) - 1)

        base_messages = list(messages)  # snapshot before tool calls
        last_response = ""

        for layer_idx in range(start, len(available)):
            layer            = available[layer_idx]
            history          = list(base_messages)
            write_ops        = False
            last_response    = ""

            # ── tool loop ──────────────────────────────────────────────────────
            while True:
                try:
                    resp = layer.messages_create(system, tools, history)
                except Exception as e:
                    last_response = f"[Layer {layer.name} error: {e}]"
                    break

                tool_calls  = [b for b in resp.content if b.type == "tool_use"]
                text_blocks = [b for b in resp.content if b.type == "text"]

                for b in text_blocks:
                    if b.text.strip() and on_text:
                        on_text(b.text)

                if resp.stop_reason == "end_turn" or not tool_calls:
                    last_response = " ".join(b.text for b in text_blocks).strip()
                    if last_response:
                        history.append({"role": "assistant", "content": last_response})
                    break

                history.append({"role": "assistant", "content": resp.content})
                results = []
                for b in tool_calls:
                    if on_tool_call:
                        on_tool_call(b)
                    if b.name in self._write_tools:
                        write_ops = True
                    result = tool_executor(b.name, b.input)
                    if on_tool_result:
                        on_tool_result(b, result)
                    results.append({
                        "type":        "tool_result",
                        "tool_use_id": b.id,
                        "content":     json.dumps(result),
                    })
                history.append({"role": "user", "content": results})

            # ── evaluate ───────────────────────────────────────────────────────
            if self._signals.ok(last_response, prompt):
                messages[:] = history
                return last_response, history

            # Signal detected — call judge
            judge_name  = layer.judge
            judge_layer = self._by_name.get(judge_name) if judge_name != "user" else None

            if judge_name == "user":
                # ── human judge ────────────────────────────────────────────────
                if user_judge_callback:
                    satisfied, feedback = user_judge_callback(last_response)
                    if satisfied:
                        messages[:] = history
                        return last_response, history
                    # Retry same layer with feedback injected (safe — no new writes yet)
                    feedback_messages = list(base_messages) + [
                        {"role": "assistant", "content": last_response},
                        {"role": "user",      "content":
                            f"That wasn't quite right. Here's what was missing or wrong:\n"
                            f"{feedback}\nPlease try again with this in mind."},
                    ]
                    # one retry with enriched context
                    try:
                        retry_resp = layer.messages_create(system, tools, feedback_messages)
                        retry_text = " ".join(
                            b.text for b in retry_resp.content if b.type == "text"
                        ).strip()
                        if retry_text and on_text:
                            on_text(retry_text)
                        history.append({"role": "assistant", "content": retry_text or last_response})
                        last_response = retry_text or last_response
                    except Exception:
                        pass
                messages[:] = history
                return last_response, history

            # ── llm judge ─────────────────────────────────────────────────────
            judge_ok = True
            if judge_layer and judge_layer.is_available():
                judge_ok = MiniJudge(judge_layer, self._judge_toks).ok(prompt, last_response)

            if judge_ok:
                messages[:] = history
                return last_response, history

            # Judge rejected — escalate only if no write side-effects
            if write_ops:
                # Unsafe to re-run — return what we have
                messages[:] = history
                return last_response, history

            # Safe to escalate → next iteration with next layer

        messages[:] = history
        return last_response, history
