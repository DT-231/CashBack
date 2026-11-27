"""Cho phép chạy `python backend/scripts/x.py` mà không cần cài package."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
