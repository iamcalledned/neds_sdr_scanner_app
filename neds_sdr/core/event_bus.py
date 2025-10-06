import logging

log = logging.getLogger("EventBus")


class EventBus:
    """Lightweight pub/sub system for module communication."""

    def __init__(self):
        self.subscribers = {}

    def subscribe(self, event_type: str, callback):
        log.debug("Subscribed to event: %s", event_type)
        self.subscribers.setdefault(event_type, []).append(callback)

    def emit(self, event_type: str, data: dict | None = None):
        """Send an event to all subscribers."""
        if event_type in self.subscribers:
            for cb in self.subscribers[event_type]:
                try:
                    cb(data or {})
                except Exception as e:
                    log.error("Event handler error for %s: %s", event_type, e)
