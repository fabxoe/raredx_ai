import pytest

from app.retrieval.negation import apply_negation_context, final_selected_hpo_terms
from app.retrieval.note_matcher import ExtractedPhenotype


def _phenotype(hpo_id: str, name: str, matched_text: str) -> ExtractedPhenotype:
    return ExtractedPhenotype(hpo_id=hpo_id, name=name, matched_text=matched_text, confidence=1.0)


def test_off_mode_keeps_negated_text_as_present() -> None:
    extracted = [_phenotype("HP:0001250", "Seizure", "seizure")]

    annotated = apply_negation_context("No seizure was observed.", extracted, mode="off")

    assert final_selected_hpo_terms(annotated) == ["HP:0001250"]
    assert annotated[0].metadata["context_label"] == "present"
    assert annotated[0].metadata["final_selected"] is True


def test_simple_trigger_excludes_negated_hpo() -> None:
    extracted = [_phenotype("HP:0001250", "Seizure", "seizure")]

    annotated = apply_negation_context("No seizure was observed.", extracted, mode="simple_trigger")

    assert final_selected_hpo_terms(annotated) == []
    assert annotated[0].metadata["context_label"] == "negated"
    assert annotated[0].metadata["final_selected"] is False
    assert annotated[0].metadata["exclusion_reason"] == "negated"


def test_negex_lite_stops_scope_at_and_has() -> None:
    extracted = [
        _phenotype("HP:0001250", "Seizure", "seizure"),
        _phenotype("HP:0000252", "Microcephaly", "microcephaly"),
    ]

    annotated = apply_negation_context(
        "Patient denies seizure and has microcephaly.",
        extracted,
        mode="negex_lite",
    )

    assert final_selected_hpo_terms(annotated) == ["HP:0000252"]
    by_id = {item.hpo_id: item for item in annotated}
    assert by_id["HP:0001250"].metadata["context_label"] == "negated"
    assert by_id["HP:0000252"].metadata["context_label"] == "present"


def test_no_evidence_phrase_excludes_developmental_delay() -> None:
    extracted = [_phenotype("HP:0001263", "Global developmental delay", "developmental delay")]

    annotated = apply_negation_context("No evidence of developmental delay.", extracted, mode="negex_lite")

    assert final_selected_hpo_terms(annotated) == []
    assert annotated[0].metadata["context_trigger"] == "no evidence of"


def test_medspacy_mode_reports_missing_dependency(monkeypatch: pytest.MonkeyPatch) -> None:
    import builtins

    original_import = builtins.__import__

    def fake_import(name: str, *args: object, **kwargs: object) -> object:
        if name == "medspacy":
            raise ImportError("not installed")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)

    with pytest.raises(RuntimeError, match="requires medspaCy"):
        apply_negation_context(
            "No seizure was observed.",
            [_phenotype("HP:0001250", "Seizure", "seizure")],
            mode="medspacy_context",
        )
