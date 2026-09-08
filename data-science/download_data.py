"""Reproducible download entry point. See README: source requires network."""
import subprocess
from pathlib import Path
dst=Path(__file__).parent/"data/downloads/berka-dataset"
if dst.exists(): print(f"Already present: {dst}")
else: subprocess.run(["git","clone","--depth","1","https://github.com/jlacko/berka-dataset.git",str(dst)],check=True)

