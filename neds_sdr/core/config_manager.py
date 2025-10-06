import yaml
import logging
from pathlib import Path
import os

log = logging.getLogger("ConfigManager")


class ConfigManager:
    """Loads and saves configuration (dongles, channels, sinks)."""

    def __init__(self, path: str | None = None):
        # Default config file location
        if path is None:
            base = os.path.dirname(os.path.dirname(__file__))
            path = os.path.join(base, "config", "config.yaml")

        self.path = path
        self.config = {}
        self.load()

    # ------------------------------------------------------------------
    def load(self):
        """Load YAML config or create default."""
        if not os.path.exists(self.path):
            log.warning(f"Config file not found: {self.path}. Creating default.")
            os.makedirs(os.path.dirname(self.path), exist_ok=True)
            self.config = {"dongles": []}
            self.save(self.config)
        else:
            with open(self.path, "r", encoding="utf-8") as f:
                self.config = yaml.safe_load(f) or {"dongles": []}
            log.info(f"Loaded configuration with {len(self.config.get('dongles', []))} dongles.")

    # ------------------------------------------------------------------
    def save(self, config=None):
        """Save YAML config."""
        if config is not None:
            self.config = config
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        with open(self.path, "w", encoding="utf-8") as f:
            yaml.safe_dump(self.config, f, default_flow_style=False)
        log.info(f"Configuration saved to {self.path}")

    def update_dongle(self, name: str, dongle_cfg: dict):
        """Replace or add a dongle config."""
        dongles = self.config.get("dongles", [])
        updated = False
        for i, d in enumerate(dongles):
            if d.get("name") == name:
                dongles[i] = dongle_cfg
                updated = True
        if not updated:
            dongles.append(dongle_cfg)
        self.save(self.config)

    def remove_dongle(self, name: str):
        """Remove a dongle entry by name."""
        self.config["dongles"] = [
            d for d in self.config.get("dongles", []) if d.get("name") != name
        ]
        self.save(self.config)
