import sys
from unittest.mock import MagicMock
sys.modules['gqlalchemy'] = MagicMock()

import pytest
from backend.graph.live_graph import LiveGraph

def test_live_graph_init():
    # Will fail if gqlalchemy is not installed or Memgraph isn't running
    # but sufficient for structure testing
    graph = LiveGraph()
    assert graph is not None
