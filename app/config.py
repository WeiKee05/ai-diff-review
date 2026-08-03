"""Central configuration. /spec reads from here so declared limits cannot drift."""

import os

from dotenv import load_dotenv

load_dotenv()

APP_VERSION = "0.1.0"
SPEC_VERSION = "1.0"

API_TOKEN = os.environ.get("API_TOKEN", "")

PROVIDERS = ["mock", "llm"]

MAX_PAYLOAD_BYTES = 1_048_576
CHUNK_BYTES = 65_536
MAX_CONCURRENT_JOBS = 4
RATE_LIMIT_PER_MINUTE = 30

# Burst capacity. Above the declared sustained rate so that 30 rapid
# submissions all succeed, per the brief.
RATE_LIMIT_BURST = 60
