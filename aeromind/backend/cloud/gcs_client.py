import os
from google.cloud import storage

class GCSClient:
    def __init__(self, bucket_name: str = None):
        self.bucket_name = bucket_name or os.getenv("GCS_BUCKET_NAME", "aeromind-f1-data")
        self._client = None
        self._bucket = None

    @property
    def client(self):
        if self._client is None:
            self._client = storage.Client()
        return self._client

    @property
    def bucket(self):
        if self._bucket is None:
            self._bucket = self.client.bucket(self.bucket_name)
        return self._bucket
    def verify_bucket(self) -> bool:
        """Verify that the bucket exists and is accessible."""
        try:
            return self.bucket.exists()
        except Exception as e:
            print(f"Bucket verification failed: {e}")
            return False

    def upload_file(self, local_path: str, gcs_path: str):
        # Upload file to GCS. Used for historical F1 data and ML models.
        blob = self.bucket.blob(gcs_path)
        blob.upload_from_filename(local_path)

    def download_file(self, gcs_path: str, local_path: str):
        # Download from GCS. Used to load cached training data.
        blob = self.bucket.blob(gcs_path)
        blob.download_to_filename(local_path)

    def file_exists(self, gcs_path: str) -> bool:
        return self.bucket.blob(gcs_path).exists()

    def list_files(self, prefix: str) -> list[str]:
        return [b.name for b in self.client.list_blobs(self.bucket_name, prefix=prefix)]
