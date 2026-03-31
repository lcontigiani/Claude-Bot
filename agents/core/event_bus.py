"""
Bus de eventos en proceso para comunicacion inmediata entre agentes.
Complementa la persistencia de SQLite con wakeups instantaneos.
"""

import threading
from collections import defaultdict


class EventBus:
    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._subscribers = defaultdict(list)
                cls._instance._sub_lock = threading.Lock()
        return cls._instance

    def subscribe(self, event_pattern, callback):
        """
        Suscribir un callback a un patron de evento.
        Patrones soportados: nombre exacto o con wildcard '*' al final.
        Ej: 'finding:critical', 'agent:*:completed'
        """
        with self._sub_lock:
            self._subscribers[event_pattern].append(callback)

    def publish(self, event_name, data=None):
        """
        Publicar un evento. Notifica a todos los suscriptores que matcheen.
        Cada callback se ejecuta en un thread separado para no bloquear.
        """
        with self._sub_lock:
            callbacks = []
            for pattern, cbs in self._subscribers.items():
                if self._matches(pattern, event_name):
                    callbacks.extend(cbs)

        for cb in callbacks:
            t = threading.Thread(target=cb, args=(event_name, data), daemon=True)
            t.start()

    @staticmethod
    def _matches(pattern, event_name):
        if pattern == event_name:
            return True
        if pattern.endswith("*"):
            prefix = pattern[:-1]
            return event_name.startswith(prefix)
        parts_p = pattern.split(":")
        parts_e = event_name.split(":")
        if len(parts_p) != len(parts_e):
            return False
        return all(pp == ep or pp == "*" for pp, ep in zip(parts_p, parts_e))


# Singleton global
bus = EventBus()
