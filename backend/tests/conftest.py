import os
from pathlib import Path

# Runs before any test imports the app, so every test sees the small fixed catalogue
# no matter how large the demo dataset in data/ becomes.
os.environ["CATALOGUE_DIR"] = str(Path(__file__).parent / "fixtures")

# The market simulation is off for every test, whatever .env says.
# The tests that need it switch it on themselves.
os.environ["MARKET_ENABLED"] = "false"