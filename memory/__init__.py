"""Chat memory: short-term history assembly + long-term Qdrant memory store.

Import submodules directly (`memory.store`, `memory.short_term`, `memory.worker`)
— do not re-export here: eager submodule imports in `__init__` create a circular
import with `backend.reset` (which imports `memory.store`).
"""
