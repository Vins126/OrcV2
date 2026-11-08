"""Estrae per ogni run valida della campagna MVP: log, sciame, valutazione, codice del sito.

Uso: venv/bin/python -m analisi.estrai  (dalla radice del progetto). Nessuna chiamata a modelli.
Legge `runs/` (non versionata) e scrive `runs/analisi-mvp/dati.json`.
"""

import collections
import json
import tomllib
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "runs" / "analisi-mvp"
CAMPAIGNS = ROOT / "runs" / "campaigns"
cfg = tomllib.loads((ROOT / "campaigns" / "mvp_giudizio.toml").read_text())
CODE_EXT = {".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs", ".css", ".html", ".sh", ".json"}
SKIP_DIRS = {"node_modules", "dist", ".git", "data", "tests", "test", "__tests__", "coverage", ".vite", "playwright-report"}


def jsonl(path):
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def row_of(campaign, task):
    rows = [r for r in jsonl(CAMPAIGNS / f"{campaign}.jsonl") if r.get("task_id") == task]
    assert len(rows) == 1, (campaign, task)
    return rows[0]


def ts(text):
    return datetime.fromisoformat(text)


def run_info(run_id):
    run_dir = ROOT / "runs" / run_id
    summary = json.loads((run_dir / "summary.json").read_text())
    usage = [e["record"] for e in jsonl(run_dir / "usage.jsonl") if e.get("event_type") == "usage"]
    events = jsonl(run_dir / "events.jsonl")
    tools = collections.Counter()
    tool_errors = collections.Counter()
    skills = []
    other_events = collections.Counter()
    for event in events:
        kind = event["event_type"]
        details = event.get("details", {})
        if kind == "tool_call":
            tools[details.get("tool")] += 1
            if details.get("error"):
                tool_errors[details.get("tool")] += 1
            if details.get("tool") == "load_skill":
                skills.append(details.get("args", {}).get("name"))
        else:
            other_events[kind] += 1
    viste = run_dir / "viste"
    finish = collections.Counter(u.get("finish_reason") for u in usage)
    latencies = [u.get("latency_s") for u in usage if isinstance(u.get("latency_s"), (int, float))]
    return {
        "run_id": run_id, "role": summary.get("role"), "status": summary.get("status"),
        "started": summary.get("started_at"), "finished": summary.get("finished_at"),
        "duration_s": summary.get("duration_s"), "iterations": summary.get("iterations"),
        "cost": summary.get("total_cost"), "cost_by_model": summary.get("cost_by_model", {}),
        "quantities": summary.get("quantities_by_unit", {}), "calls": len(usage),
        "latency_sum_s": sum(latencies), "latency_max_s": max(latencies, default=0),
        "finish_reasons": dict(finish), "tools": dict(tools), "tool_errors": dict(tool_errors),
        "skills": skills, "other_events": dict(other_events),
        "view_site_shots": len([d for d in viste.iterdir() if d.is_dir()]) if viste.exists() else 0,
        # costo per chiamata in ordine, per vedere quanto si spende dopo la prima consegna utile
        "call_costs": [u.get("cost") or 0 for u in usage],
        "call_models": [u.get("model") for u in usage],
        "final_message": summary.get("final_message") or "",
        "agent_id": summary.get("agent_id"),
        "n_tool_calls_per_call": [u.get("n_tool_calls") or 0 for u in usage],
        "tool_sequence": [e.get("details", {}).get("tool") for e in events if e["event_type"] == "tool_call"],
    }


def site_code(workspace):
    ws = Path(workspace)
    files, lines = collections.Counter(), collections.Counter()
    test_files = 0
    for path in ws.rglob("*"):
        rel = path.relative_to(ws)
        if any(part in ("node_modules", "dist", ".git") for part in rel.parts):
            continue
        if path.is_file() and any(part in ("tests", "test", "__tests__") for part in rel.parts) or ".test." in path.name or ".spec." in path.name:
            if path.is_file():
                test_files += 1
            continue
        if not path.is_file() or any(part in SKIP_DIRS for part in rel.parts):
            continue
        if path.suffix in CODE_EXT and path.name != "package-lock.json":
            files[path.suffix] += 1
            try:
                lines[path.suffix] += len(path.read_text(encoding="utf-8", errors="replace").splitlines())
            except OSError:
                pass
    pkg = {}
    if (ws / "package.json").exists():
        try:
            pkg = json.loads((ws / "package.json").read_text())
        except ValueError:
            pkg = {}
    dist_bytes = sum(p.stat().st_size for p in (ws / "dist").rglob("*") if p.is_file()) if (ws / "dist").exists() else 0
    dist_js = sum(p.stat().st_size for p in (ws / "dist").rglob("*.js") if p.is_file()) if (ws / "dist").exists() else 0
    src_files = list((ws / "src").rglob("*.jsx")) + list((ws / "src").rglob("*.tsx")) if (ws / "src").exists() else []
    testids = 0
    for path in (ws / "src").rglob("*") if (ws / "src").exists() else []:
        if path.is_file() and path.suffix in (".jsx", ".tsx", ".js", ".ts"):
            testids += path.read_text(encoding="utf-8", errors="replace").count("data-testid")
    return {
        "files_by_ext": dict(files), "lines_by_ext": dict(lines),
        "files": sum(files.values()), "lines": sum(lines.values()),
        "components": len(src_files), "test_files": test_files,
        "dependencies": sorted(pkg.get("dependencies", {})), "dev_dependencies": sorted(pkg.get("devDependencies", {})),
        "dist_bytes": dist_bytes, "dist_js_bytes": dist_js, "data_testid": testids,
    }


def swarm_info(row):
    log = Path(row["swarm_log"])
    events = jsonl(log)
    plan_file = log.parent / "plan.json"
    plan = json.loads(plan_file.read_text()) if plan_file.exists() else {}
    pieces = [e for e in events if e.get("event") == "piece"]
    end = next((e for e in events if e.get("event") == "end"), {})
    return {
        "plan_attempts": len([e for e in events if e.get("event") == "plan"]),
        "plan_agents": [e.get("agent_id") for e in events if e.get("event") == "plan"],
        "plan_valid": [e.get("valid") for e in events if e.get("event") == "plan"],
        "pieces": [{k: p.get(k) for k in ("piece_id", "wave", "role", "model", "status", "cost", "error_type")} for p in pieces],
        "waves": 1 + max((p.get("wave") or 0 for p in pieces), default=-1),
        "gates": [{k: e.get(k) for k in ("phase", "accepted", "reason")} for e in events if e.get("event") == "gate"],
        "file_checks": [e for e in events if e.get("event") == "file_check"],
        "escalated": end.get("escalated"), "end_status": end.get("status"),
        "breakdown": end.get("breakdown", {}),
        "events": dict(collections.Counter(e.get("event") for e in events)),
        "plan_style_chars": len(plan.get("style", "")) if isinstance(plan, dict) else 0,
        "plan_keys": sorted(plan) if isinstance(plan, dict) else [],
    }


records = []
for arm, table in cfg["runs"].items():
    for task, campaign in sorted(table.items()):
        row = row_of(campaign, task)
        evaluation = json.loads(Path(row["evaluation"]["path"]).read_text())
        run_ids = row.get("run_ids") or [row["run_id"]]
        runs = [run_info(r) for r in run_ids if (ROOT / "runs" / r / "summary.json").exists()]
        steps = evaluation["riservato"].get("steps", [])
        widths = evaluation.get("cancello", {}).get("widths", {})
        record = {
            "arm": arm, "task": task, "campaign": campaign, "status": row["status"],
            "manifest_cost": row["total_cost"], "funziona": row["evaluation"]["funziona"],
            "funziona_server": row["evaluation"].get("funziona_server"),
            "gate_accepted": row.get("gate", {}).get("accepted"), "gate_reason": row.get("gate", {}).get("reason"),
            "steps": steps,
            "widths": {w: {"errors": len(v.get("errors", [])), "overflow": v.get("overflow"),
                           "a11y": len(v.get("a11y", [])), "a11y_ids": [a.get("id") if isinstance(a, dict) else a for a in v.get("a11y", [])],
                           "status": v.get("status")} for w, v in widths.items()},
            "screenshots": evaluation["riservato"]["screenshots"],
            "runs": runs, "workspace": row["workspace"],
            "code": site_code(row["workspace"]),
            "started": min(r["started"] for r in runs), "finished": max(r["finished"] for r in runs),
        }
        record["wall_s"] = (ts(record["finished"]) - ts(record["started"])).total_seconds()
        if arm == "C":
            record["swarm"] = swarm_info(row)
        records.append(record)

# Spesa di tutte le righe mvp-* (comprese quelle non valide), per il costo vero dell'esperimento
all_rows = []
for manifest in sorted(CAMPAIGNS.glob("mvp-*.jsonl")):
    for row in jsonl(manifest):
        if row.get("task_id"):
            all_rows.append({"campaign": manifest.stem, "task": row["task_id"], "status": row.get("status"),
                             "cost": row.get("total_cost") or 0, "error_type": row.get("error_type"),
                             "run_ids": row.get("run_ids") or [row.get("run_id")]})

judgments = jsonl(ROOT / "runs" / "giudizio-mvp" / "giudizi.jsonl")
plan = json.loads((ROOT / "runs" / "giudizio-mvp" / "coppie.json").read_text())
OUT.mkdir(parents=True, exist_ok=True)
(OUT / "dati.json").write_text(json.dumps({"records": records, "all_rows": all_rows, "judgments": judgments,
                                           "judge_plan": plan}, indent=1, ensure_ascii=False))
print(len(records), "record;", len(all_rows), "righe mvp-*")
