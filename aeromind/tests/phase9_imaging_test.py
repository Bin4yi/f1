from unittest.mock import MagicMock, patch
import pytest

from backend.imaging.race_visualizer import RaceVisualizer

# Test 1
def test_build_prompt_contains_monaco():
    rv = RaceVisualizer()
    prompt = rv.build_prompt("Leclerc closed in...", {"car1_name": "Leclerc"})
    assert "Monaco" in prompt
    assert "2026" in prompt

# Test 2
def test_build_prompt_no_drs():
    rv = RaceVisualizer()
    prompt = rv.build_prompt("...", {"car1_name": "Leclerc", "car1_soc": 0.7})
    assert "DRS" not in prompt or "No DRS" in prompt or "no drs" in prompt.lower()

# Test 3
def test_build_prompt_mentions_2026_car_design():
    rv = RaceVisualizer()
    prompt = rv.build_prompt("...", {"car1_name": "Leclerc"})
    assert "2026" in prompt or "active aerodynamics" in prompt

# Test 4
@pytest.mark.asyncio
async def test_generate_image_returns_string_or_empty():
    with patch('backend.imaging.race_visualizer.ImageGenerationModel.from_pretrained') as mock_model_init:
        mock_model_instance = MagicMock()
        mock_model_init.return_value = mock_model_instance
        rv = RaceVisualizer()
        with patch.object(rv.model, 'generate_images') as mock_gen:
            mock_gen.return_value = MagicMock(images=[])
            result = await rv.generate_race_image("Test", {}, 1)
            assert result == ""

# Test 5
@pytest.mark.asyncio
async def test_generate_image_on_success_returns_gcs_url():
    with patch('backend.imaging.race_visualizer.ImageGenerationModel.from_pretrained') as mock_model_init:
        mock_model_instance = MagicMock()
        mock_model_init.return_value = mock_model_instance
        rv = RaceVisualizer()
        with patch.object(rv.model, 'generate_images') as mock_gen, \
             patch.object(rv.gcs, 'upload_file'):
            mock_image = MagicMock()
            mock_image._image_bytes = b"FAKE_IMAGE_BYTES"
            mock_gen.return_value = MagicMock(images=[mock_image])
            result = await rv.generate_race_image("Test", {}, 1)
            assert "storage.googleapis.com" in result
