import unittest

from src import agent


class MathPromptTests(unittest.TestCase):
    def test_prompt_requires_step_by_step_verification(self):
        prompt = agent.SYSTEM_PROMPT.lower()
        self.assertIn("step-by-step", prompt)
        self.assertIn("verify", prompt)
        self.assertIn("arithmetic", prompt)


if __name__ == "__main__":
    unittest.main()
