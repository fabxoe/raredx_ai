from app.llm.phenotype_qc import PhenotypeLLMSelector
from app.retrieval.note_matcher import ExtractedPhenotype


class FakeJSONChatClient:
    def complete_json(self, system_prompt: str, user_prompt: str) -> dict[str, object]:
        return {
            "selected_hpo_ids": ["HP:0001250"],
            "rejected_hpo_ids": ["HP:0001263"],
            "notes": {"HP:0001250": "supported by seizure mention"},
        }


def test_phenotype_llm_selector_keeps_only_selected_candidates() -> None:
    selector = PhenotypeLLMSelector(FakeJSONChatClient(), provider="openai", model="gpt-test")
    candidates = [
        ExtractedPhenotype("HP:0001250", "Seizure", "seizure", 0.91, "original_hpo_mapper"),
        ExtractedPhenotype("HP:0001263", "Global developmental delay", "delay", 0.80, "original_hpo_mapper"),
    ]

    selected = selector.select("Patient has seizures.", candidates, protocol="p3_llm_selection")

    assert [item.hpo_id for item in selected] == ["HP:0001250"]
    assert selected[0].metadata["llm_used"] is True
    assert selected[0].metadata["llm_provider"] == "openai"
    assert selected[0].metadata["llm_protocol"] == "p3_llm_selection"
    assert selected[0].metadata["llm_qc_status"] == "selected"
