import sys
from unittest.mock import MagicMock
sys.modules['gqlalchemy'] = MagicMock()

import pytest
from backend.graph.graphrag import GraphRAG
from backend.graph.knowledge_graph import KnowledgeGraph

def test_graphrag_init():
    rag = GraphRAG()
    assert isinstance(rag.kg, KnowledgeGraph)

def test_fetch_and_save_historical_data(monkeypatch):
    # Mock GCSClient to avoid actual network calls during testing
    class MockGCSClient:
        def file_exists(self, path): return False
        def upload_file(self, local, gcs): pass

    monkeypatch.setattr("backend.graph.graphrag.GCSClient", MockGCSClient)

    rag = GraphRAG()
    rag.fetch_and_save_historical_data()
    # Test would assert files were created in /tmp
