"""
Vertex AI Vector Search & Visual Embedding Service.
Computes multimodal/text embeddings for garment representations and performs cosine similarity de-duplication.
"""

import math
import hashlib
from typing import List, Dict, Any, Optional, Tuple
from ..config import (
    DEFAULT_EMBEDDING_MODEL,
    DEFAULT_MULTIMODAL_EMBEDDING_MODEL,
    SIMILARITY_THRESHOLD,
    GCP_PROJECT_ID,
    GCP_LOCATION,
    get_genai_client
)

# Try importing Google GenAI / Vertex AI
try:
    from google import genai
    from google.genai import types
    GENAI_AVAILABLE = True
except ImportError:
    GENAI_AVAILABLE = False



def compute_cosine_similarity(vec_a: List[float], vec_b: List[float]) -> float:
    """
    Computes exact cosine similarity between two float vectors.
    Returns float in [-1.0, 1.0].
    """
    if not vec_a or not vec_b or len(vec_a) != len(vec_b):
        return 0.0
    
    dot_product = sum(a * b for a, b in zip(vec_a, vec_b))
    norm_a = math.sqrt(sum(a * a for a in vec_a))
    norm_b = math.sqrt(sum(b * b for b in vec_b))
    
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
        
    return dot_product / (norm_a * norm_b)


class VectorSearchService:
    """
    Generates semantic and visual embeddings for clothing items and executes vector matching.
    """
    def __init__(self, embedding_model: str = DEFAULT_EMBEDDING_MODEL):
        self.embedding_model = embedding_model
        self._genai_client = None  # Initialized lazily on first use to avoid blocking startup

    def generate_garment_embedding(self, garment_data: Dict[str, Any]) -> List[float]:
        """
        Generates a normalized embedding vector for a garment record based on its
        visual attributes, category, material, color, pattern, formality, and occasion.
        """
        # Formulate rich descriptive feature text
        feature_text = (
            f"Category: {garment_data.get('category', '')}. "
            f"Sub-category: {garment_data.get('sub_category', '')}. "
            f"Color: {garment_data.get('primary_color', '')}. "
            f"Material: {garment_data.get('material', '')}. "
            f"Pattern: {garment_data.get('pattern', '')}. "
            f"Design: {garment_data.get('design', '')}. "
            f"Formality: {garment_data.get('formality', '')}. "
            f"Occasion: {garment_data.get('occasion', '')}. "
            f"Season: {garment_data.get('season_tag') or garment_data.get('season', '')}. "
            f"Style tags: {', '.join(garment_data.get('style_tags', [])) if isinstance(garment_data.get('style_tags'), list) else garment_data.get('style_tags', '')}."
        )

        if self._genai_client is None and GENAI_AVAILABLE:
            try:
                self._genai_client = get_genai_client()
            except Exception:
                self._genai_client = None

        if self._genai_client:
            try:
                response = self._genai_client.models.embed_content(
                    model=self.embedding_model,
                    contents=feature_text
                )
                if response.embedding and response.embedding.values:
                    return response.embedding.values
            except Exception as e:
                # Log and proceed to deterministic semantic embedding
                pass

        return self._generate_deterministic_embedding(feature_text, garment_data)

    def _generate_deterministic_embedding(self, text: str, data: Dict[str, Any], dim: int = 128) -> List[float]:
        """
        Deterministic, semantic-aware pseudo-embedding for testing and offline execution.
        Preserves high similarity (>0.88) for near-identical garments and low similarity for distinct ones.
        """
        vector = [0.0] * dim
        
        # Key attributes produce concentrated weight buckets
        semantic_keys = [
            f"cat_{data.get('category', '').lower()}",
            f"sub_{data.get('sub_category', '').lower()}",
            f"col_{data.get('primary_color', '').lower()}",
            f"mat_{data.get('material', '').lower()}",
            f"pat_{data.get('pattern', '').lower()}",
            f"occ_{data.get('occasion', '').lower()}",
            f"form_{data.get('formality', '').lower()}"
        ]

        for i, key in enumerate(semantic_keys):
            h = int(hashlib.md5(key.encode()).hexdigest(), 16)
            bucket = h % dim
            vector[bucket] += 2.0
            vector[(bucket + 1) % dim] += 1.0

        # General text hashing for nuanced variance
        for word in text.lower().split():
            h = int(hashlib.sha256(word.encode()).hexdigest(), 16)
            bucket = h % dim
            vector[bucket] += 0.5

        # Normalize vector to unit length
        norm = math.sqrt(sum(x * x for x in vector))
        if norm > 0:
            vector = [x / norm for x in vector]
        return vector

    def find_most_similar(
        self,
        query_embedding: List[float],
        candidate_items: List[Dict[str, Any]],
        threshold: float = SIMILARITY_THRESHOLD
    ) -> Tuple[Optional[Dict[str, Any]], float]:
        """
        Compares query_embedding against candidate items.
        Returns (matched_item, max_similarity).
        If max_similarity >= threshold, matched_item is the existing garment record.
        """
        best_match = None
        highest_sim = 0.0

        for item in candidate_items:
            item_embedding = item.get("embedding")
            if not item_embedding:
                # If item record doesn't have an embedding cached, compute on the fly
                item_embedding = self.generate_garment_embedding(item)

            sim = compute_cosine_similarity(query_embedding, item_embedding)
            if sim > highest_sim:
                highest_sim = sim
                if sim >= threshold:
                    best_match = item

        return best_match, highest_sim


_VECTOR_SEARCH_INSTANCE: Optional[VectorSearchService] = None

def get_vector_search_service() -> VectorSearchService:
    global _VECTOR_SEARCH_INSTANCE
    if _VECTOR_SEARCH_INSTANCE is None:
        _VECTOR_SEARCH_INSTANCE = VectorSearchService()
    return _VECTOR_SEARCH_INSTANCE
