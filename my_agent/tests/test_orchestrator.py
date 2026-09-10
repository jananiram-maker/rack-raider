import unittest
from my_agent.services.weather_service import WeatherService
from my_agent.tools.evaluate_outfit import evaluate_outfit_rules
from my_agent.tools.synthesize_outfits import synthesize_outfits
from my_agent.agent import orchestrator_agent, tagging_agent, outfit_agent


class TestOrchestratorAndOutfitTools(unittest.TestCase):
    def setUp(self):
        self.weather_service = WeatherService()

    def test_weather_data_preprocessing(self):
        """Validates Open-Meteo weather JSON pre-processing into structured summary."""
        raw_mock_data = {
            "current": {
                "temperature_2m": 17.5,
                "precipitation": 0.2,
                "weather_code": 3
            },
            "daily": {
                "temperature_2m_max": [22.0],
                "temperature_2m_min": [12.0],
                "precipitation_probability_max": [40],
                "uv_index_max": [5.5]
            }
        }

        summary = self.weather_service.pre_process_weather_data(raw_mock_data)
        
        self.assertEqual(summary["temp_range"], [12.0, 22.0])
        self.assertEqual(summary["current_temp"], 17.5)
        self.assertEqual(summary["precipitation_risk"], 0.4)
        self.assertEqual(summary["uv_index"], 5.5)
        self.assertTrue(summary["layering_recommended"])
        self.assertIn("Overcast", summary["weather_condition"])
        self.assertIn("summary_prompt", summary)

    def test_evaluate_outfit_rules_dress_support(self):
        """Validates that a Dress + Footwear is recognized as a complete standalone base outfit."""
        # 1. Dress + Footwear (Valid complete outfit)
        dress_outfit = [
            {"item_name": "Emerald Silk Midi Dress", "category": "Dress", "warmth_rating": 2, "formality": "Smart Casual"},
            {"item_name": "Leather Loafers", "category": "Footwear", "warmth_rating": 2, "formality": "Smart Casual"}
        ]
        res_dress = evaluate_outfit_rules(dress_outfit, target_occasion="Casual / Daily", temperature_c=20.0)
        self.assertEqual(res_dress["status"], "PASS")
        self.assertTrue(res_dress["is_valid"])

        # 2. Top + Bottom + Footwear (Valid complete separates outfit)
        separates_outfit = [
            {"item_name": "White Shirt", "category": "Top", "warmth_rating": 2, "formality": "Smart Casual"},
            {"item_name": "Chino Pants", "category": "Bottom", "warmth_rating": 2, "formality": "Smart Casual"},
            {"item_name": "Sneakers", "category": "Footwear", "warmth_rating": 2, "formality": "Casual"}
        ]
        res_sep = evaluate_outfit_rules(separates_outfit, target_occasion="Casual / Daily", temperature_c=20.0)
        self.assertEqual(res_sep["status"], "PASS")
        self.assertTrue(res_sep["is_valid"])

        # 3. Incomplete outfit (Missing bottom and not a dress)
        incomplete_outfit = [
            {"item_name": "White Shirt", "category": "Top", "warmth_rating": 2, "formality": "Casual"},
            {"item_name": "Sneakers", "category": "Footwear", "warmth_rating": 2, "formality": "Casual"}
        ]
        res_inc = evaluate_outfit_rules(incomplete_outfit, target_occasion="Casual / Daily", temperature_c=20.0)
        self.assertEqual(res_inc["status"], "FAIL")
        self.assertFalse(res_inc["is_valid"])

    def test_synthesize_outfits_returns_multiple_options(self):
        """Validates that outfit synthesizer produces 2-3 complete layered options."""
        inventory = [
            {"item_id": "1", "item_name": "Linen Shirt", "category": "Top", "warmth_rating": 2, "primary_color": "White"},
            {"item_id": "2", "item_name": "Oxford Shirt", "category": "Top", "warmth_rating": 2, "primary_color": "Blue"},
            {"item_id": "3", "item_name": "Chinos", "category": "Bottom", "warmth_rating": 3, "primary_color": "Beige"},
            {"item_id": "4", "item_name": "Silk Wrap Dress", "category": "Dress", "warmth_rating": 2, "primary_color": "Black"},
            {"item_id": "5", "item_name": "Leather Chelsea Boots", "category": "Footwear", "warmth_rating": 2, "primary_color": "Black"},
            {"item_id": "6", "item_name": "Wool Trench Coat", "category": "Outerwear", "warmth_rating": 4, "primary_color": "Camel"}
        ]

        result = synthesize_outfits(
            inventory_data=inventory,
            weather_context="16°C, Light rain",
            occasion="Work / Professional"
        )

        self.assertIn("outfit_options", result)
        self.assertTrue(len(result["outfit_options"]) >= 2)
        self.assertIsNotNone(result.get("bridge_staple_recommendation"))

    def test_orchestrator_agent_structure(self):
        """Validates orchestrator agent setup and tool registration."""
        self.assertEqual(orchestrator_agent.name, "NaturallyEasy_Primary_Orchestrator")
        self.assertTrue(len(orchestrator_agent.tools) >= 5)
        self.assertEqual(len(orchestrator_agent.sub_agents), 2)


if __name__ == "__main__":
    unittest.main()
