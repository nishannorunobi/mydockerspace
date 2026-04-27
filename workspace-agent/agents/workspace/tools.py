import os
import json
import subprocess
from pathlib import Path
from datetime import datetime

WORKSPACE_ROOT = Path(__file__).parent.parent.parent.parent  # workspace/→agents/→workspace-agent/→myworkspace/
AGENT_DIR      = Path(__file__).parent
MEMORY_DIR     = AGENT_DIR / "memory"

IGNORE = {".git", ".venv", "__pycache__", "node_modules", "target",
          ".vscode", "vscode-server-extensions", ".mvn", ".claude"}

TOOL_DEFINITIONS = [
    {
        "name": "scan_workspace",
        "description": (
            "Scan the workspace directory tree up to a given depth. "
            "Returns the folder/file structure. Use to observe the workspace layout."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "max_depth": {"type": "integer", "description": "Max depth to scan (default 4)"},
                "path":      {"type": "string",  "description": "Subpath to scan (default: workspace root)"}
            }
        }
    },
    {
        "name": "read_file",
        "description": "Read any file inside the workspace. Path is relative to workspace root.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "File path relative to workspace root"}
            },
            "required": ["path"]
        }
    },
    {
        "name": "git_log",
        "description": "Get recent git commit history for the workspace or a specific project.",
        "input_schema": {
            "type": "object",
            "properties": {
                "n":    {"type": "integer", "description": "Number of commits (default 20)"},
                "path": {"type": "string",  "description": "Subpath (defaults to workspace root)"}
            }
        }
    },
    {
        "name": "git_status",
        "description": "Get current git working tree status (uncommitted changes).",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Subpath (defaults to workspace root)"}
            }
        }
    },
    {
        "name": "git_diff",
        "description": "Get diff of recent changes or a specific commit.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path":   {"type": "string", "description": "Subpath (defaults to workspace root)"},
                "commit": {"type": "string", "description": "Specific commit hash (optional)"},
                "stat":   {"type": "boolean","description": "Show only stats, not full diff (default true)"}
            }
        }
    },
    {
        "name": "write_memory",
        "description": "Save an observation, note, or structured data to the agent memory store.",
        "input_schema": {
            "type": "object",
            "properties": {
                "filename": {"type": "string", "description": "Memory file name (e.g. projects.md, concerns.md)"},
                "content":  {"type": "string", "description": "Content to write"},
                "append":   {"type": "boolean","description": "Append to existing file instead of overwriting (default false)"}
            },
            "required": ["filename", "content"]
        }
    },
    {
        "name": "read_memory",
        "description": "Read a memory file by name.",
        "input_schema": {
            "type": "object",
            "properties": {
                "filename": {"type": "string", "description": "Memory file name to read"}
            },
            "required": ["filename"]
        }
    },
    {
        "name": "list_memory",
        "description": "List all files currently stored in agent memory.",
        "input_schema": {"type": "object", "properties": {}}
    },
    {
        "name": "update_meta",
        "description": (
            "Update the structured meta.json file that other agents can consume. "
            "Contains workspace structure, project list, active concerns, and key facts."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "meta": {
                    "type": "object",
                    "description": "Structured metadata dict to merge into meta.json"
                }
            },
            "required": ["meta"]
        }
    }
]


def _run(cmd: list, cwd=None) -> str:
    try:
        result = subprocess.run(
            cmd, cwd=str(cwd or WORKSPACE_ROOT),
            capture_output=True, text=True, timeout=15
        )
        return (result.stdout + result.stderr).strip()
    except subprocess.TimeoutExpired:
        return "Command timed out"
    except Exception as e:
        return f"Error: {e}"


def _tree(root: Path, depth: int, max_depth: int, prefix="") -> list[str]:
    if depth > max_depth:
        return []
    lines = []
    try:
        entries = sorted(root.iterdir(), key=lambda p: (p.is_file(), p.name))
    except PermissionError:
        return []
    for i, entry in enumerate(entries):
        if entry.name in IGNORE or entry.name.startswith("."):
            continue
        connector = "└── " if i == len(entries) - 1 else "├── "
        lines.append(f"{prefix}{connector}{entry.name}{'/' if entry.is_dir() else ''}")
        if entry.is_dir():
            extension = "    " if i == len(entries) - 1 else "│   "
            lines.extend(_tree(entry, depth + 1, max_depth, prefix + extension))
    return lines


def execute_tool(name: str, inp: dict) -> dict:

    if name == "scan_workspace":
        max_depth = inp.get("max_depth", 4)
        subpath   = inp.get("path", "")
        root      = WORKSPACE_ROOT / subpath if subpath else WORKSPACE_ROOT
        if not root.exists():
            return {"error": f"Path not found: {subpath}"}
        lines = [str(root)] + _tree(root, 1, max_depth)
        return {"tree": "\n".join(lines), "root": str(root)}

    if name == "read_file":
        path = WORKSPACE_ROOT / inp["path"]
        if not path.exists():
            return {"error": f"File not found: {inp['path']}"}
        if not str(path).startswith(str(WORKSPACE_ROOT)):
            return {"error": "Access denied — outside workspace"}
        try:
            content = path.read_text(errors="replace")
            return {"content": content[:8000], "truncated": len(content) > 8000}
        except Exception as e:
            return {"error": str(e)}

    if name == "git_log":
        n    = inp.get("n", 20)
        cwd  = WORKSPACE_ROOT / inp["path"] if inp.get("path") else WORKSPACE_ROOT
        out  = _run(["git", "log", f"-{n}",
                     "--pretty=format:%h  %ad  %an  %s",
                     "--date=short", "--stat"], cwd=cwd)
        return {"log": out}

    if name == "git_status":
        cwd = WORKSPACE_ROOT / inp["path"] if inp.get("path") else WORKSPACE_ROOT
        out = _run(["git", "status", "--short"], cwd=cwd)
        return {"status": out or "clean"}

    if name == "git_diff":
        cwd    = WORKSPACE_ROOT / inp["path"] if inp.get("path") else WORKSPACE_ROOT
        stat   = inp.get("stat", True)
        commit = inp.get("commit")
        cmd    = ["git", "diff"]
        if commit:
            cmd += [f"{commit}^", commit]
        if stat:
            cmd.append("--stat")
        out = _run(cmd, cwd=cwd)
        return {"diff": out or "no changes"}

    if name == "write_memory":
        if "content" not in inp:
            return {"error": "write_memory called without 'content' field"}
        MEMORY_DIR.mkdir(exist_ok=True)
        filepath = MEMORY_DIR / inp["filename"]
        mode     = "a" if inp.get("append") else "w"
        if inp.get("append") and filepath.exists():
            content = f"\n\n---\n*{datetime.now().strftime('%Y-%m-%d %H:%M')}*\n\n{inp['content']}"
        else:
            content = inp["content"]
        filepath.write_text(content if mode == "w" else
                            (filepath.read_text() if filepath.exists() else "") + content)
        return {"saved": str(filepath)}

    if name == "read_memory":
        filepath = MEMORY_DIR / inp["filename"]
        if not filepath.exists():
            return {"error": f"Memory file not found: {inp['filename']}"}
        return {"content": filepath.read_text()}

    if name == "list_memory":
        MEMORY_DIR.mkdir(exist_ok=True)
        files = [f.name for f in sorted(MEMORY_DIR.iterdir()) if f.is_file()]
        return {"files": files}

    if name == "update_meta":
        MEMORY_DIR.mkdir(exist_ok=True)
        meta_path = MEMORY_DIR / "meta.json"
        existing  = json.loads(meta_path.read_text()) if meta_path.exists() else {}
        existing.update(inp["meta"])
        existing["last_updated"] = datetime.now().isoformat()
        meta_path.write_text(json.dumps(existing, indent=2))
        return {"saved": str(meta_path)}

    return {"error": f"Unknown tool: {name}"}
