from pathlib import Path


def pinned_model_path(settings) -> Path:
    return settings.data_dir.parent / ".local/models/pinned" / settings.embedding_model.replace("/", "--") / settings.embedding_revision
