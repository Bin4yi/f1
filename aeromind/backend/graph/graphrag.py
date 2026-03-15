import os
import json
from .knowledge_graph import KnowledgeGraph
from backend.cloud.gcs_client import GCSClient

class GraphRAG:
    """
    Performs GraphRAG operations using Memgraph to provide context to models.
    """
    def __init__(self, live_graph=None, knowledge_graph=None):
        from .live_graph import LiveGraph
        from .knowledge_graph import KnowledgeGraph
        self.lg = live_graph or LiveGraph()
        self.kg = knowledge_graph or KnowledgeGraph()

    def retrieve_context(self, query: str, driver_number: int = None) -> str:
        """
        Retrieve context from the graph based on a natural language or structural query.
        Simplified example.
        """
        if driver_number:
            # Example query: get recent historical performance for this driver
            cypher = "MATCH (d:HistoricalDriver {number: $num})-[:COMPETED_IN]->(r:HistoricalRace) RETURN r.name as race, r.position as pos LIMIT 3"
            results = self.kg.query_history(cypher, {"num": driver_number})
            return json.dumps(results)
        return "No specific context available."

    def fetch_and_save_historical_data(self):
        """Simulate fetching historical data, saving locally, and uploading to GCS."""
        print("Fetching historical data...")
        # Simulate local save
        temp_dir = "/tmp/f1_historical"
        os.makedirs(temp_dir, exist_ok=True)
        saved_files = []
        for i in range(2):
            file_path = os.path.join(temp_dir, f"history_part_{i}.json")
            with open(file_path, "w") as f:
                json.dump({"dummy": "data", "part": i}, f)
            saved_files.append(file_path)

        gcs = GCSClient()
        for local_path in saved_files:
            gcs_path = f"historical/{os.path.basename(local_path)}"
            if not gcs.file_exists(gcs_path):
                gcs.upload_file(local_path, gcs_path)
                print(f"Uploaded {gcs_path} to GCS")
