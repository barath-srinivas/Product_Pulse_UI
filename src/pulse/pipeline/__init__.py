"""Phase 2 reasoning pipeline: scrub → embed → cluster → Groq LLM → validate."""

# Keep this module lightweight — pulse-api imports pulse.pipeline.models at startup.
# Eager imports here previously pulled torch/umap/hdbscan and broke Railway healthchecks.
