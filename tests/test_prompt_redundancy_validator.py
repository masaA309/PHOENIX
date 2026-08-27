from __future__ import annotations

import unittest

from prompt_redundancy_validator import validate_prompt_redundancy


class PromptRedundancyValidatorTest(unittest.TestCase):
    def test_prompt_vs_agents_exact_or_near_exact_duplicate_fails(self) -> None:
        agents_text = "最初にAGENTS.mdを読む。\n他の行"
        prompt_text = "導入\n最初にAGENTS.mdを読む。\n結び"

        result = validate_prompt_redundancy(
            prompt_text=prompt_text,
            agents_text=agents_text,
            proof_targets=["alpha", "beta"],
        )

        self.assertFalse(result.passed)
        self.assertTrue(any(finding.rule == "prompt_vs_agents" for finding in result.findings))

    def test_duplicate_constraint_sentence_in_same_prompt_fails(self) -> None:
        prompt_text = "禁止: test\n禁止: test\n別の文"

        result = validate_prompt_redundancy(
            prompt_text=prompt_text,
            agents_text="まったく別のAGENTS内容",
            proof_targets=["alpha", "beta"],
        )

        self.assertFalse(result.passed)
        self.assertTrue(any(finding.rule == "prompt_internal_duplicate" for finding in result.findings))

    def test_proof_target_containment_fails(self) -> None:
        result = validate_prompt_redundancy(
            prompt_text="差し支えない文",
            agents_text="別のAGENTS",
            proof_targets=[
                "config のみを読む",
                "config のみを読む かつ 実行前に確認する",
                "完全に別",
            ],
        )

        self.assertFalse(result.passed)
        self.assertTrue(any(finding.rule == "proof_target_overlap" for finding in result.findings))

    def test_non_redundant_prompt_passes(self) -> None:
        result = validate_prompt_redundancy(
            prompt_text="A\nB\nC",
            agents_text="X\nY\nZ",
            proof_targets=["alpha", "beta", "gamma"],
        )

        self.assertTrue(result.passed)
        self.assertEqual((), result.findings)


if __name__ == "__main__":
    unittest.main()
