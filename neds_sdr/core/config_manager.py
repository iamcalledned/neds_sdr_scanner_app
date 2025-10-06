import yaml
import logging
from pathlib import Path

log = logging.getLogger("ConfigManager")


class ConfigManager:
    """Handles loading and saving SDR configuration from YAML."""

    def __init__(self, path: str):
        self.path = Path(path)
        self.config = {}

    def load(self) -> dict:
        """Load configuration from YAML file."""
        if not self.path.exists():
            log.warning("Config file not found. Creating new default.")
            self.config = {"dongles": []}
            self.save()
        else:
            with open(self.path, "r") as f:
                self.config = yaml.safe_load(f) or {"dongles": []}
        log.info("Loaded configuration with %d dongles.", len(self.config.get("dongles", [])))
        return self.config

    def save(self, data: dict | None = None):
        """Save current configuration to YAML."""
        if data:
            self.config = data
        with open(self.path, "w") as f:
            yaml.dump(self.config, f)
        log.info("Configuration saved to %s", self.path)

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
