"""midea.cafeca.io — the public site: official channel, topics, most-watched, and audience feedback (phase 1).

Separate from the internal studio board (midea/web): its own process, no studio access, read-only view of
published projects. Records live in SQLite (`site.db` under `site.data_dir`) behind `store.Store`, so the
PostgreSQL / Redis setup in the plan can replace it without touching the API layer.
"""
