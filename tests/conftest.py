import sys
from pathlib import Path

# Works whether or not the package has been pip installed.
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "simulation"))
