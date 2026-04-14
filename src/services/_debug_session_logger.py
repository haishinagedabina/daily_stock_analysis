from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Dict, Optional

_DEBUG_SESSION_ID = "5f4259"
_DEBUG_LOG_PATH = Path(__file__).resolve().parents[2] / "debug-5f4259.log"


def write_debug_log(
    *,
    location: str,
    message: str,
    hypothesis_id: str,
    data: Optional[Dict[str, Any]] = None,
    run_id: Optional[str] = None,
) -> None:
    payload = {
        "sessionId": _DEBUG_SESSION_ID,
        "runId": run_id,
        "hypothesisId": hypothesis_id,
        "location": location,
        "message": message,
        "data": data or {},
        "timestamp": int(time.time() * 1000),
    }
    try:
        with _DEBUG_LOG_PATH.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, ensure_ascii=False, default=str) + "\n")
    except Exception:
        pass
