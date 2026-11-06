"""Absolute-path runtime entry; works when a host strips PYTHONPATH from MCP."""
from pathlib import Path
import sys

sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
from workgraph.cli import main

if __name__=="__main__":raise SystemExit(main())
