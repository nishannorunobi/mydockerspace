"""
Generate architecture PDF for the Multi-Layer LLM Router system.
Run: python3 generate_architecture_pdf.py
Output: llm_router_architecture.pdf
"""

from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.lib import colors
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    HRFlowable, KeepTogether
)
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_JUSTIFY
from pathlib import Path
import datetime

OUT = Path(__file__).parent / "llm_router_architecture.pdf"

# ── Colour palette ────────────────────────────────────────────────────────────
C_BG        = colors.HexColor("#0d1117")
C_BLUE      = colors.HexColor("#58a6ff")
C_GREEN     = colors.HexColor("#3fb950")
C_YELLOW    = colors.HexColor("#d29922")
C_RED       = colors.HexColor("#f85149")
C_PURPLE    = colors.HexColor("#d2a8ff")
C_BORDER    = colors.HexColor("#30363d")
C_TEXT      = colors.HexColor("#c9d1d9")
C_TEXT2     = colors.HexColor("#8b949e")
C_BG2       = colors.HexColor("#161b22")
C_BG3       = colors.HexColor("#21262d")
C_WHITE     = colors.white
C_BLACK     = colors.black

W, H = A4
MARGIN = 18 * mm

# ── Styles ────────────────────────────────────────────────────────────────────
styles = getSampleStyleSheet()

def style(name, **kw):
    s = ParagraphStyle(name, **kw)
    return s

S_TITLE = style("Title2",
    fontName="Helvetica-Bold", fontSize=22, textColor=C_WHITE,
    alignment=TA_CENTER, spaceAfter=4)

S_SUBTITLE = style("Subtitle2",
    fontName="Helvetica", fontSize=11, textColor=C_TEXT2,
    alignment=TA_CENTER, spaceAfter=2)

S_DATE = style("Date",
    fontName="Helvetica", fontSize=9, textColor=C_TEXT2,
    alignment=TA_CENTER, spaceAfter=16)

S_SECTION = style("Section",
    fontName="Helvetica-Bold", fontSize=13, textColor=C_BLUE,
    spaceBefore=14, spaceAfter=6)

S_BODY = style("Body2",
    fontName="Helvetica", fontSize=9.5, textColor=C_TEXT,
    leading=15, spaceAfter=6, alignment=TA_JUSTIFY)

S_MONO = style("Mono",
    fontName="Courier", fontSize=8.5, textColor=C_GREEN,
    leading=13, spaceAfter=4)

S_LABEL = style("Label",
    fontName="Helvetica-Bold", fontSize=9, textColor=C_WHITE)

S_SMALL = style("Small",
    fontName="Helvetica", fontSize=8, textColor=C_TEXT2, leading=12)

S_NOTE = style("Note",
    fontName="Helvetica-Oblique", fontSize=8.5, textColor=C_YELLOW,
    spaceAfter=4)

S_BOLD = style("Bold2",
    fontName="Helvetica-Bold", fontSize=9.5, textColor=C_WHITE)

# ── Helper builders ───────────────────────────────────────────────────────────

def section(title):
    return [
        Spacer(1, 4*mm),
        HRFlowable(width="100%", thickness=1, color=C_BORDER),
        Spacer(1, 2*mm),
        Paragraph(title, S_SECTION),
    ]

def body(text):
    return Paragraph(text, S_BODY)

def note(text):
    return Paragraph(f"⚡ {text}", S_NOTE)

def mono(text):
    return Paragraph(text, S_MONO)

def sp(h=4):
    return Spacer(1, h*mm)

def layer_table(rows, col_colors):
    """Render a styled layer comparison table."""
    col_w = [(W - 2*MARGIN) / len(rows[0])] * len(rows[0])
    t = Table(rows, colWidths=col_w, repeatRows=1)
    style_cmds = [
        ("BACKGROUND",  (0,0), (-1,0),  C_BG3),
        ("TEXTCOLOR",   (0,0), (-1,0),  C_BLUE),
        ("FONTNAME",    (0,0), (-1,0),  "Helvetica-Bold"),
        ("FONTSIZE",    (0,0), (-1,-1), 8.5),
        ("ROWBACKGROUNDS", (0,1), (-1,-1), [C_BG, C_BG2]),
        ("TEXTCOLOR",   (0,1), (-1,-1), C_TEXT),
        ("GRID",        (0,0), (-1,-1), 0.5, C_BORDER),
        ("ALIGN",       (0,0), (-1,-1), "CENTER"),
        ("VALIGN",      (0,0), (-1,-1), "MIDDLE"),
        ("PADDING",     (0,0), (-1,-1), 5),
    ]
    for col_idx, col_color in enumerate(col_colors):
        if col_color:
            style_cmds.append(("TEXTCOLOR", (col_idx,1), (col_idx,-1), col_color))
    t.setStyle(TableStyle(style_cmds))
    return t

def flow_table(rows):
    """Render a flow/decision table."""
    col_w = [(W - 2*MARGIN) / len(rows[0])] * len(rows[0])
    t = Table(rows, colWidths=col_w)
    t.setStyle(TableStyle([
        ("BACKGROUND",  (0,0), (-1,-1), C_BG2),
        ("TEXTCOLOR",   (0,0), (-1,-1), C_TEXT),
        ("FONTNAME",    (0,0), (-1,-1), "Courier"),
        ("FONTSIZE",    (0,0), (-1,-1), 8),
        ("GRID",        (0,0), (-1,-1), 0.5, C_BORDER),
        ("ALIGN",       (0,0), (-1,-1), "LEFT"),
        ("VALIGN",      (0,0), (-1,-1), "TOP"),
        ("PADDING",     (0,0), (-1,-1), 6),
    ]))
    return t

def box_table(content_rows, bg=C_BG2, border=C_BORDER):
    t = Table(content_rows, colWidths=[W - 2*MARGIN])
    t.setStyle(TableStyle([
        ("BACKGROUND",  (0,0), (-1,-1), bg),
        ("TEXTCOLOR",   (0,0), (-1,-1), C_TEXT),
        ("FONTNAME",    (0,0), (-1,-1), "Helvetica"),
        ("FONTSIZE",    (0,0), (-1,-1), 9),
        ("BOX",         (0,0), (-1,-1), 1, border),
        ("PADDING",     (0,0), (-1,-1), 8),
        ("ALIGN",       (0,0), (-1,-1), "LEFT"),
        ("VALIGN",      (0,0), (-1,-1), "TOP"),
    ]))
    return t


# ── Page background ───────────────────────────────────────────────────────────

def on_page(canvas, doc):
    canvas.saveState()
    canvas.setFillColor(C_BG)
    canvas.rect(0, 0, W, H, fill=1, stroke=0)
    # footer
    canvas.setFont("Helvetica", 7)
    canvas.setFillColor(C_TEXT2)
    canvas.drawString(MARGIN, 10*mm, "Multi-Layer LLM Router — Architecture Document")
    canvas.drawRightString(W - MARGIN, 10*mm, f"Page {doc.page}")
    canvas.restoreState()


# ── Content ───────────────────────────────────────────────────────────────────

def build_content():
    story = []

    # ── Cover ──────────────────────────────────────────────────────────────────
    story += [
        sp(12),
        Paragraph("Multi-Layer LLM Router", S_TITLE),
        Paragraph("Cascade Intelligence Architecture", S_SUBTITLE),
        Paragraph(f"Generated {datetime.date.today().strftime('%B %d, %Y')}", S_DATE),
        HRFlowable(width="100%", thickness=1, color=C_BLUE),
        sp(4),
        body(
            "This document defines the architecture for a cost-efficient, "
            "multi-layer LLM routing system. Prompts are routed through progressively "
            "more capable (and expensive) models. Each layer's output is judged by the "
            "next layer up — not by a fixed external judge. If all models fail, "
            "the <b>user becomes the final judge</b>, providing feedback that is fed "
            "back into the pipeline."
        ),
        sp(2),
    ]

    # ── 1. System Overview ─────────────────────────────────────────────────────
    story += section("1. System Overview")
    story += [
        body(
            "The system has three LLM layers and one human layer. Each layer executes "
            "the prompt using its assigned model. The <b>next layer up acts as judge</b> — "
            "it evaluates whether the response fully answered the user's intent. "
            "Escalation only happens when the judge deems the response insufficient."
        ),
        sp(3),
        layer_table(
            [
                ["Layer", "Role", "Model (default)", "Judge", "Cost"],
                ["1 — Local",  "First attempt",     "Ollama / qwen2.5:7b",        "Layer 2 (Haiku)",  "Free"],
                ["2 — Fast",   "Fallback",          "Claude Haiku 4.5",            "Layer 3 (Sonnet)", "Low"],
                ["3 — Smart",  "Complex tasks",     "Claude Sonnet 4.6",           "User (human)",     "Medium"],
                ["4 — Human",  "Ultimate fallback", "You",                         "—",                "Free"],
            ],
            [None, None, C_GREEN, C_YELLOW, C_BLUE]
        ),
        sp(2),
        note("All models and judge assignments are configurable in router.yaml — swap any layer without touching code."),
    ]

    # ── 2. Cascade Judge Design ────────────────────────────────────────────────
    story += section("2. Cascade Judge Design  (Key Innovation)")
    story += [
        body(
            "The judge is <b>not fixed</b>. Each layer is evaluated by the model one step "
            "above it. This means a stronger model always evaluates a weaker model's work — "
            "which is both cheaper and more reliable than using a fixed external judge for everything."
        ),
        sp(3),
        flow_table([
            ["Layer executes",         "Judge",               "Judge prompt (simplified)"],
            ["Layer 1  →  response",   "Layer 2 (Haiku)",     '"Did this fully answer the question? YES / NO"'],
            ["Layer 2  →  response",   "Layer 3 (Sonnet)",    '"Did this fully answer the question? YES / NO"'],
            ["Layer 3  →  response",   "User (human)",        "Dashboard shows response + asks: Satisfied? Yes / No"],
            ["User gives feedback",    "—  (loop closes)",    "Feedback injected into Layer 3 as additional context"],
        ]),
        sp(3),
        body(
            "<b>Why this works:</b> Haiku is smart enough to know when a 7B local model missed the point. "
            "Sonnet is smart enough to know when Haiku was too shallow. The user is the only one who "
            "truly knows if Sonnet's answer solved their real problem. Each judge has exactly the "
            "right level of intelligence for what it is evaluating."
        ),
    ]

    # ── 3. Full Decision Flow ──────────────────────────────────────────────────
    story += section("3. Full Decision Flow")
    story += [
        mono(
            "USER PROMPT\n"
            "    │\n"
            "    ▼\n"
            "PreClassifier  →  scan keywords  →  pick start layer\n"
            "    │                    simple → L1 · medium → L2 · complex → L3\n"
            "    ▼\n"
            "┌─────────────────────────────────────────────────────┐\n"
            "│  Layer N executes prompt                            │\n"
            "│      │                                              │\n"
            "│      ▼                                              │\n"
            "│  SignalDetector  (free — scans response text)       │\n"
            "│      ├── bad signals?  NO  → skip judge → RETURN   │\n"
            "│      └── bad signals?  YES → call judge             │\n"
            "│                                │                    │\n"
            "│                    Judge = Layer N+1                │\n"
            "│                    (or User if N = 3)               │\n"
            "│                                │                    │\n"
            "│                    ┌───────────┴──────────┐        │\n"
            "│                  PASS                    FAIL       │\n"
            "│                    │                       │        │\n"
            "│                 RETURN               ESCALATE       │\n"
            "│                                     to Layer N+1    │\n"
            "└─────────────────────────────────────────────────────┘\n"
            "    │\n"
            "    ▼\n"
            "If Layer 3 fails  →  User Judge\n"
            "    User sees response in dashboard\n"
            "    User clicks  ✓ Good  or  ✗ Not helpful\n"
            "        ✓ Good   →  RETURN\n"
            "        ✗ Not helpful  →  ask  'What was missing?'\n"
            "                         feedback + original prompt\n"
            "                         → retry Layer 3 with context\n"
        ),
    ]

    # ── 4. Signal Detector ─────────────────────────────────────────────────────
    story += section("4. Signal Detector  (Free Quality Gate)")
    story += [
        body(
            "Before calling the judge (which costs tokens), the signal detector scans "
            "the raw response text for failure markers. This costs nothing and catches "
            "obvious failures instantly."
        ),
        sp(2),
        layer_table(
            [
                ["Signal Type",       "Pattern / Condition",                         "Confidence"],
                ["Uncertainty",       '"i don\'t know"  "i\'m not sure"  "i cannot"',  "High"],
                ["No access",         '"i don\'t have access"  "i\'m unable to"',      "High"],
                ["Too short",         "response < 60 words for non-trivial prompt",    "Medium"],
                ["Question back",     "response ends with a question (model confused)", "Medium"],
                ["Tool failure",      "tool call returned error or empty result",       "High"],
                ["No answer",         "response contains only acknowledgement, no content", "High"],
            ],
            [None, C_YELLOW, C_GREEN]
        ),
        sp(2),
        note("Signal detector runs first — judge only called if signals are found. Most good responses never reach the judge."),
    ]

    # ── 5. Pre-Classifier ─────────────────────────────────────────────────────
    story += section("5. Pre-Classifier  (Routing Without LLM)")
    story += [
        body(
            "Before any model is called, the pre-classifier estimates prompt complexity "
            "from keywords. This determines the starting layer — avoiding wasted calls "
            "to Layer 1 for tasks that are obviously complex."
        ),
        sp(2),
        layer_table(
            [
                ["Start Layer",  "Trigger Keywords",                                     "Rationale"],
                ["Layer 1",  "list · show · status · what is · check · describe · ping", "Lookup / factual — local model handles fine"],
                ["Layer 2",  "write · fix · create · explain · compare · summarise · find", "Generation task — needs reliable output"],
                ["Layer 3",  "architect · debug · refactor · design · review · why does · analyse", "Reasoning / multi-step — needs full power"],
            ],
            [C_GREEN, C_YELLOW, C_BLUE]
        ),
        sp(2),
        note("Keywords are fully configurable in router.yaml. Add your own domain-specific trigger words."),
    ]

    # ── 6. User-as-Judge ──────────────────────────────────────────────────────
    story += section("6. User as Ultimate Judge")
    story += [
        body(
            "When Layer 3 (Sonnet) fails the signal check, the response is shown to the user "
            "with two actions in the dashboard. The user's feedback is never discarded — "
            "it is injected as additional context for the retry, making the next attempt smarter."
        ),
        sp(2),
        flow_table([
            ["Step", "What happens"],
            ["1. Show",     "Dashboard renders Layer 3 response + shows  ✓ Good  /  ✗ Not helpful  buttons"],
            ["2. Accept",   "User clicks  ✓ Good  →  response is accepted, conversation continues normally"],
            ["3. Reject",   "User clicks  ✗ Not helpful  →  dashboard shows text field: 'What was missing?'"],
            ["4. Feedback", "User types feedback  →  appended to original prompt as additional context"],
            ["5. Retry",    "Layer 3 (Sonnet) re-runs with enriched prompt  →  response shown again"],
            ["6. Loop",     "Steps 2–5 repeat until user accepts or abandons the prompt"],
        ]),
        sp(2),
        note("User feedback is also saved to the agent's memory — improving future pre-classifier routing for similar prompts."),
    ]

    # ── 7. Configuration ───────────────────────────────────────────────────────
    story += section("7. Configuration  (router.yaml)")
    story += [
        body("Everything is controlled from a single YAML file. No code changes needed to swap models, "
             "disable layers, or change thresholds."),
        sp(2),
        mono(
            "layers:\n"
            "  - name: local\n"
            "    type: ollama\n"
            "    model: qwen2.5:7b\n"
            "    enabled: true\n"
            "    max_tokens: 1024\n"
            "    judge: fast          # judged by the 'fast' layer\n"
            "\n"
            "  - name: fast\n"
            "    type: anthropic\n"
            "    model: claude-haiku-4-5-20251001\n"
            "    enabled: true\n"
            "    max_tokens: 2048\n"
            "    judge: smart         # judged by the 'smart' layer\n"
            "\n"
            "  - name: smart\n"
            "    type: anthropic\n"
            "    model: claude-sonnet-4-6\n"
            "    enabled: true\n"
            "    max_tokens: 4096\n"
            "    judge: user          # judged by the human\n"
            "\n"
            "routing:\n"
            "  signal_threshold: 1   # bad signals before calling judge\n"
            "  judge_max_tokens: 50  # judge only outputs YES/NO\n"
            "\n"
            "complexity:\n"
            "  layer1_keywords: [list, show, status, check, what, describe]\n"
            "  layer2_keywords: [write, fix, create, explain, compare, find]\n"
            "  layer3_keywords: [architect, debug, refactor, design, review, why]\n"
        ),
    ]

    # ── 8. File Structure ─────────────────────────────────────────────────────
    story += section("8. File Structure")
    story += [
        mono(
            "agents/\n"
            "├── llm-router/               ← shared module (all agents import this)\n"
            "│   ├── router.py             ← LLMRouter  — main entry point\n"
            "│   ├── classifier.py         ← PreClassifier  — keyword routing\n"
            "│   ├── evaluator.py          ← SignalDetector + MiniJudge\n"
            "│   ├── router.yaml           ← all config lives here\n"
            "│   └── layers/\n"
            "│       ├── base.py           ← abstract BaseLayer\n"
            "│       ├── ollama.py         ← Ollama HTTP client\n"
            "│       └── anthropic.py      ← Anthropic SDK + prompt caching\n"
            "│\n"
            "├── workspace-agent/          ← imports LLMRouter\n"
            "├── docker-manager-agent/     ← imports LLMRouter\n"
            "├── agent-orchestrator/       ← imports LLMRouter\n"
            "└── docs/\n"
            "    └── llm_router_architecture.pdf   ← this document\n"
        ),
    ]

    # ── 9. Cost Comparison ────────────────────────────────────────────────────
    story += section("9. Cost Comparison")
    story += [
        body("Assuming 100 user prompts per day across all agents:"),
        sp(2),
        layer_table(
            [
                ["Scenario",              "Distribution",                    "Est. monthly cost"],
                ["No routing (Sonnet all)", "100% Sonnet",                  "~$45 / month"],
                ["Simple routing",        "60% Haiku · 40% Sonnet",         "~$18 / month"],
                ["With Ollama layer",     "50% Local · 30% Haiku · 20% Sonnet", "~$7 / month"],
                ["This architecture",    "40% Local · 35% Haiku · 25% Sonnet", "~$5 / month"],
            ],
            [None, C_TEXT2, C_GREEN]
        ),
        sp(2),
        note("Estimates based on Anthropic pricing May 2026. Actual savings depend on prompt length and tool call frequency."),
        sp(4),
        HRFlowable(width="100%", thickness=1, color=C_BORDER),
        sp(2),
        Paragraph("Built for the myworkspace agents project  ·  Nishan  ·  2026", S_DATE),
    ]

    return story


# ── Build ─────────────────────────────────────────────────────────────────────

def generate():
    OUT.parent.mkdir(parents=True, exist_ok=True)
    doc = SimpleDocTemplate(
        str(OUT),
        pagesize=A4,
        leftMargin=MARGIN, rightMargin=MARGIN,
        topMargin=MARGIN,  bottomMargin=16*mm,
        title="Multi-Layer LLM Router Architecture",
        author="Nishan",
    )
    doc.build(build_content(), onFirstPage=on_page, onLaterPages=on_page)
    print(f"✓ PDF written → {OUT}")


if __name__ == "__main__":
    generate()
