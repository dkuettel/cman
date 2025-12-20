from __future__ import annotations

import json
import os
from pathlib import Path

path = Path(__file__).parent / "paths.json"
if path.exists():
    # in prod
    data = json.loads(path.read_text())
    katex = str(data["katex"])
else:
    # in dev
    katex = f"{os.environ['h']}/result/lib/node_modules/katex/dist/"

__all__ = ["katex"]
