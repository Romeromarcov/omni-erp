"""
Señales de auditoría (NEW-DOC-2).

Hogar de las señales relacionadas con la auditoría del sistema. Antes vivían
(como stub vacío) en ``apps/core/signals.py``; se movieron aquí por coherencia
con el dominio. Se conectan vía ``AuditoriaConfig.ready()``.
"""


def connect_signals():
    """Conecta las señales de auditoría. Punto de extensión para futuros receivers."""
    # Aún no hay receivers globales; el registro de auditoría se hace en las vistas
    # (RegistroAuditoria). Este es el punto único para conectarlos cuando se añadan.
    return
