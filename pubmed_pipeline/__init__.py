"""
PubMed Harvesting Pipeline for AesthetiCite
============================================

A 3-stage pipeline for harvesting biomedical publications from PubMed:
- Stage 1: Query planning (corpus definition)
- Stage 2: Retrieval (metadata + abstracts via E-utilities)
- Stage 3: Normalization + Storage

Legal Note:
-----------
This pipeline ingests bibliographic metadata and abstracts from PubMed.
Where full text is ingested, it is limited to open-access sources such as
PubMed Central OA content. For paywalled articles, AesthetiCite stores
citations and links, not the full text.
"""

__version__ = "1.0.0"
