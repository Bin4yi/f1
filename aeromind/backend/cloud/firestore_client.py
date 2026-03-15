import os
from google.cloud import firestore

class FirestoreClient:
    """
    Firestore stores live race state for ARIA to access.
    ARIA's Live API session reads from Firestore to get current telemetry
    without needing the full Memgraph query — it needs fast, flat key-value access.
    """
    def __init__(self):
        self._db = None
        self.collection = os.getenv("FIRESTORE_COLLECTION", "aeromind_race_state")

    @property
    def db(self):
        if self._db is None:
            self._db = firestore.AsyncClient(project=os.getenv("GOOGLE_CLOUD_PROJECT"))
        return self._db

    async def update_race_state(self, state: dict):
        # Write current race state to Firestore
        # state: {cars, edges, attacking_pairs, latest_decision, timestamp}
        doc_ref = self.db.collection(self.collection).document("live")
        await doc_ref.set(state)

    async def get_race_state(self) -> dict | None:
        doc_ref = self.db.collection(self.collection).document("live")
        doc = await doc_ref.get()
        return doc.to_dict() if doc.exists else None

    async def update_debate(self, debate_log: list):
        doc_ref = self.db.collection(self.collection).document("debate")
        await doc_ref.set({"debate_log": debate_log, "timestamp": firestore.SERVER_TIMESTAMP})

    async def update_simulation(self, sim_display: dict):
        doc_ref = self.db.collection(self.collection).document("simulation")
        await doc_ref.set(sim_display)
