"""NASA documentation retrieval components for B03."""

from wildfire_api.rag.index import NasaDocumentIndex, build_index
from wildfire_api.rag.models import RetrievedPassage, SourceSpec

__all__ = ["NasaDocumentIndex", "RetrievedPassage", "SourceSpec", "build_index"]
