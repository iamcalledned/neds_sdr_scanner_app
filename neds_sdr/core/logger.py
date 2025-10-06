import logging
import os
from datetime import datetime


def setup_logging():
    """Configure structured logging for the SDR system."""
    log_dir = os.getenv("LOG_DIR", "./logs")
    os.makedirs(log_dir, exist_ok=True)

    log_file = os.path.join(log_dir, f"neds_sdr_{datetime.now():%Y%m%d}.log")

    logging.basicConfig(
        level=os.getenv("LOG_LEVEL", "INFO"),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[
            logging.FileHandler(log_file),
            logging.StreamHandler()
        ]
    )

    logging.getLogger().info("Logging initialized. Log file: %s", log_file)
