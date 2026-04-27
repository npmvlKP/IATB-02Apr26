import sys
from urllib.error import URLError
from urllib.request import urlopen

HEALTH_URL = "http://127.0.0.1:8000/health"
TIMEOUT_SECONDS = 3

try:
    response = urlopen(HEALTH_URL, timeout=TIMEOUT_SECONDS)
    sys.exit(0) if response.status == 200 else sys.exit(1)
except (URLError, OSError, TimeoutError):
    sys.exit(1)
