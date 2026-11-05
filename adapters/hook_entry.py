"""Reviewed local lifecycle hook entrypoint."""

from pathlib import Path
import json
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from workgraph.hooks import run

print(json.dumps(run(sys.argv[1])))
