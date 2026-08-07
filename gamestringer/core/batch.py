"""
Batch Processing & Auto Engine Detection Manager for GameStringer CLI.

Supports batch extraction and repatching tasks configured via JSON or TOML configs,
utilizing ThreadPoolExecutor for concurrent game processing.
"""

import os
import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Dict, Any, Optional
from gamestringer.core.base_engine import BaseEngine
from gamestringer.core.logger import logger


def load_config(config_path: str) -> List[Dict[str, Any]]:
    """Load batch processing configuration from JSON or TOML file."""
    if not os.path.exists(config_path):
        raise FileNotFoundError(f"Config file not found: {config_path}")

    ext = os.path.splitext(config_path)[1].lower()

    if ext == ".json":
        with open(config_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, list):
                return data
            elif isinstance(data, dict) and "tasks" in data:
                return data["tasks"]
            else:
                raise ValueError("JSON batch config must be a list of task objects or contain a 'tasks' array.")

    elif ext in (".toml", ".tbm"):
        try:
            import tomllib  # Python 3.11+ standard library
        except ImportError:
            try:
                import tomli as tomllib
            except ImportError:
                raise RuntimeError("TOML parsing requires Python 3.11+ or 'tomli' package installed.")

        with open(config_path, "rb") as f:
            data = tomllib.load(f)
            return data.get("tasks", [])

    else:
        raise ValueError(f"Unsupported config format '{ext}'. Supported formats: .json, .toml")


def auto_detect_engine(input_path: str, engine_registry: Dict[str, BaseEngine]) -> BaseEngine:
    """
    Auto-detect matching engine for an input path by testing all registered engines' detect() method.
    """
    matches = []
    for name, engine in engine_registry.items():
        try:
            if engine.detect(input_path):
                matches.append(engine)
        except Exception:
            pass

    if not matches:
        raise ValueError(f"Auto-detect failed: No matching engine detected for '{input_path}'.")

    if len(matches) > 1:
        match_names = ", ".join(m.name for m in matches)
        logger.warning(f"Ambiguous engine match for '{input_path}'. Multiple engines matched: {match_names}. Using '{matches[0].name}'.")

    return matches[0]


def process_batch_task(task: Dict[str, Any], engine_registry: Dict[str, BaseEngine]) -> Dict[str, Any]:
    """Execute a single extract or patch batch task."""
    input_path = task.get("input")
    engine_name = task.get("engine", "auto")
    output_path = task.get("output")
    action = task.get("action", "extract").lower()
    xliff_path = task.get("xliff")
    target_lang = task.get("lang", "it")

    if not input_path or not os.path.exists(input_path):
        return {"status": "error", "message": f"Input path does not exist: {input_path}", "task": task}

    try:
        if engine_name == "auto":
            engine = auto_detect_engine(input_path, engine_registry)
        else:
            engine = engine_registry.get(engine_name.lower())
            if not engine:
                return {"status": "error", "message": f"Unknown engine '{engine_name}'", "task": task}

        if action == "extract":
            if not output_path:
                return {"status": "error", "message": "Missing 'output' path for extract task", "task": task}
            result_path = engine.extract(input_path, output_path)
            return {"status": "success", "action": "extract", "result": result_path, "engine": engine.name, "task": task}

        elif action == "patch":
            if not xliff_path or not os.path.exists(xliff_path):
                return {"status": "error", "message": f"Missing or invalid 'xliff' path for patch task: {xliff_path}", "task": task}
            msg = engine.patch(input_path, xliff_path, output_path)
            return {"status": "success", "action": "patch", "result": msg, "engine": engine.name, "task": task}

        else:
            return {"status": "error", "message": f"Unknown action '{action}'", "task": task}

    except Exception as err:
        return {"status": "error", "message": str(err), "task": task}


def run_batch(
    config_path: str,
    engine_registry: Dict[str, BaseEngine],
    max_workers: int = 4,
) -> List[Dict[str, Any]]:
    """
    Run batch processing tasks concurrently using ThreadPoolExecutor.
    """
    tasks = load_config(config_path)
    if not tasks:
        logger.warning(f"No tasks found in batch configuration file: {config_path}")
        return []

    logger.info(f"Loaded {len(tasks)} batch task(s) from {config_path}. Processing with max {max_workers} worker threads...")
    results = []

    with ThreadPoolExecutor(max_workers=min(max_workers, len(tasks))) as executor:
        future_to_task = {
            executor.submit(process_batch_task, task, engine_registry): task
            for task in tasks
        }
        for future in as_completed(future_to_task):
            res = future.result()
            results.append(res)
            if res["status"] == "success":
                logger.info(f"Task finished [{res['engine']}]: {res['result']}")
            else:
                logger.error(f"Task failed: {res['message']}")

    return results
