import os
import vertexai
from vertexai.preview.vision_models import ImageGenerationModel
from backend.cloud.gcs_client import GCSClient

class RaceVisualizer:

    def __init__(self):
        vertexai.init(
            project=os.getenv("GOOGLE_CLOUD_PROJECT"),
            location=os.getenv("VERTEX_AI_LOCATION", "us-central1")
        )
        self.model = ImageGenerationModel.from_pretrained("imagegeneration@006")
        self.gcs = GCSClient()

    def build_prompt(self, chronicle_entry: str, race_context: dict) -> str:
        """
        Build an Imagen prompt from the chronicle entry.
        Style: dramatic F1 photography — not cartoon, not illustrated.
        The prompt should produce something that looks like a real TV broadcast still.
        """
        attacker = race_context.get("car1_name", "a racing car")
        defender = race_context.get("car2_name", "the leading car")
        soc = race_context.get("car1_soc", 0.7)
        mode = "with purple Overtake Mode active" if soc > 0.35 else "pushing hard"

        base_prompt = (
            f"Dramatic Formula 1 race photography, Monaco Grand Prix 2026. "
            f"{attacker} following closely behind {defender} through the barriers "
            f"of Monaco, {mode}. "
            f"Ultra-realistic, cinematic lighting, motion blur on wheels, "
            f"F1 2026 car design — shorter wheelbase, active aerodynamics. "
            f"Sky Sports broadcast quality. No DRS wing. "
            f"High contrast, dramatic shadows, tight shot. "
            f"Style: Sports Illustrated, high-speed racing photography."
        )
        return base_prompt

    async def generate_race_image(self, chronicle_entry: str,
                                  race_context: dict,
                                  event_number: int) -> str:
        """
        Generate a race moment image for the chronicle entry.
        Returns: GCS public URL of the generated image.
        Falls back to "" if generation fails (don't crash the race loop).
        """
        try:
            prompt = self.build_prompt(chronicle_entry, race_context)

            response = self.model.generate_images(
                prompt=prompt,
                number_of_images=1,
                aspect_ratio="16:9",
                safety_filter_level="block_some",
                person_generation="allow_adult"
            )

            if not response.images:
                return ""

            # Save to GCS
            img_bytes = response.images[0]._image_bytes
            gcs_path = f"race_images/event_{event_number:03d}.jpg"
            local_path = f"/tmp/event_{event_number:03d}.jpg"

            # Create /tmp structure if it doesn't exist to prevent local save errors
            os.makedirs(os.path.dirname(local_path), exist_ok=True)
            
            with open(local_path, "wb") as f:
                f.write(img_bytes)

            self.gcs.upload_file(local_path, gcs_path)
            public_url = f"https://storage.googleapis.com/{self.gcs.bucket_name}/{gcs_path}"
            return public_url

        except Exception as e:
            print(f"Image generation failed for event {event_number}: {e}")
            return ""  # Graceful fallback — race loop continues
