"""MCP entrypoint usable directly from a plugin checkout."""

import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from workgraph.mcp import serve

serve(os.environ.get("WORKGRAPH_REPO", "."), os.environ.get("WORKGRAPH_SESSION"),
      os.environ.get("WORKGRAPH_RUNTIME", "mcp"), os.environ.get("WORKGRAPH_ATTEMPT"),unbound=not bool(os.environ.get('WORKGRAPH_REPO')))
