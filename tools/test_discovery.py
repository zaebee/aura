import asyncio
import unittest
from unittest.mock import MagicMock, patch
from hive.proteins.discovery.skill import DiscoverySkill
from config.discovery import DiscoverySettings
from aura_core_gen.aura.core.v1 import Observation, DiscoveryObservation, XenoEntity

class TestDiscoverySkill(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.settings = DiscoverySettings(github_token="fake_token")
        self.provider = {"lm": MagicMock()}
        self.skill = DiscoverySkill()
        self.skill.bind(self.settings, self.provider)

    @patch("hive.proteins.discovery.skill.Github")
    @patch("dspy.configure")
    async def test_initialize(self, mock_dspy_config, mock_github):
        success = await self.skill.initialize()
        self.assertTrue(success)
        mock_github.assert_called_once()
        mock_dspy_config.assert_called_once()

    @patch("hive.proteins.discovery.skill.generate_proposal")
    @patch("hive.proteins.discovery.skill.analyze_compatibility")
    @patch("hive.proteins.discovery.skill.sequence_genome")
    @patch("hive.proteins.discovery.skill.scan_github")
    @patch("dspy.configure")
    @patch("hive.proteins.discovery.skill.Github")
    async def test_first_contact_intent_rhizomatic(self, mock_github, mock_dspy_config, mock_scan, mock_sequence, mock_analyze, mock_proposal):
        await self.skill.initialize()
        mock_scan.return_value = [{"name": "test-repo", "url": "https://github.com/test-repo"}]
        mock_sequence.return_value = "repo DNA content"
        mock_analyze.return_value = {
            "substrate": "Python",
            "nervous_system": "gRPC",
            "valence": "compute",
            "architecture_type": "Microservices",
            "detected_interfaces": ["gRPC", "REST"],
            "compatibility_score": 0.9,
            "reasoning": "High compatibility"
        }
        mock_proposal.return_value = "Symbiotic Proposal"

        params = {"query": "test query"}
        observation = await self.skill.execute("first_contact", params)

        self.assertTrue(observation.success)

        # Check DiscoveryObservation
        self.assertIsNotNone(observation.discovery)
        self.assertEqual(len(observation.discovery.entities), 1)
        entity = observation.discovery.entities[0]
        self.assertEqual(entity.repo_url, "https://github.com/test-repo")
        self.assertEqual(entity.architecture_type, "Microservices")
        self.assertIn("gRPC", entity.detected_interfaces)
        self.assertEqual(entity.compatibility_score, 0.9)

if __name__ == "__main__":
    unittest.main()
