import logging
import os


os.makedirs("logs", exist_ok=True)

logging.basicConfig(
    filename="logs/nse_scheduler.log",
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s"
)

logger = logging.getLogger("nse_agent")