import re
from dataclasses import replace
from typing import Literal

from app.llm.phenotype_qc import PhenotypeLLMSelector
from app.retrieval.note_matcher import ExtractedPhenotype


NegationMode = Literal[
    "off",
    "simple_trigger",
    "negex_lite",
    "medspacy_context",
    "status_weight",
    "llm_qc",
]

NEGATION_MODES: tuple[str, ...] = (
    "off",
    "simple_trigger",
    "negex_lite",
    "medspacy_context",
    "status_weight",
    "llm_qc",
)

_PRE_NEGATION_TRIGGERS = (
    "no evidence of",
    "absence of",
    "negative for",
    "free of",
    "denies",
    "denied",
    "without",
    "no",
    "not",
    "lack of",
    "lacks",
)
_POST_NEGATION_TRIGGERS = (
    "not observed",
    "not seen",
    "not present",
    "is absent",
    "was absent",
    "were absent",
    "absent",
    "negative",
)
_TERMINATORS = ("but", "however", "although", "except", "while", "and has", "and had", "with")


def apply_negation_context(
    clinical_note: str,
    extracted: list[ExtractedPhenotype],
    mode: str = "off",
    llm_selector: PhenotypeLLMSelector | None = None,
) -> list[ExtractedPhenotype]:
    normalized_mode = (mode or "off").strip().lower()
    if normalized_mode not in NEGATION_MODES:
        raise ValueError(f"unsupported negation_mode: {mode}")
    if normalized_mode == "off":
        return [_with_context(item, "present", "off", weight=1.0, selected=True) for item in extracted]
    if normalized_mode == "medspacy_context":
        return _annotate_with_medspacy(clinical_note, extracted)
    if normalized_mode == "llm_qc":
        if llm_selector is None:
            raise RuntimeError("LLM negation QC requires RAREDX_LLM_PROVIDER=openai or ollama and a configured API key/model.")
        return _annotate_with_llm_qc(clinical_note, extracted, llm_selector)

    use_window = normalized_mode in {"negex_lite", "status_weight"}
    annotated = [
        _annotate_rule_based(clinical_note, item, normalized_mode, use_window=use_window)
        for item in extracted
    ]
    return annotated


def final_selected_hpo_terms(extracted: list[ExtractedPhenotype]) -> list[str]:
    return [item.hpo_id for item in extracted if item.metadata.get("final_selected") is not False]


def _annotate_rule_based(
    clinical_note: str,
    item: ExtractedPhenotype,
    mode: str,
    use_window: bool,
) -> ExtractedPhenotype:
    sentence = _sentence_for_match(clinical_note, item)
    trigger = _find_negation_trigger(sentence, item, use_window=use_window)
    if trigger is None:
        return _with_context(item, "present", mode, weight=1.0, selected=True, scope=sentence)
    return _with_context(
        item,
        "negated",
        mode,
        trigger=trigger,
        scope=sentence,
        weight=0.0,
        selected=False,
        exclusion_reason="negated",
    )


def _annotate_with_medspacy(
    clinical_note: str,
    extracted: list[ExtractedPhenotype],
) -> list[ExtractedPhenotype]:
    try:
        import medspacy  # type: ignore[import-not-found]
        from loguru import logger
        from spacy.util import filter_spans
    except ImportError as exc:
        raise RuntimeError("medspaCy negation mode requires medspaCy. Install medspacy before selecting medspacy_context.") from exc

    try:
        logger.disable("PyRuSH")
        nlp = medspacy.load()
        doc = nlp.make_doc(clinical_note)
        for name, pipe in nlp.pipeline:
            if name == "medspacy_context":
                break
            doc = pipe(doc)

        spans = []
        span_key_by_index: dict[int, tuple[int, int]] = {}
        for index, item in enumerate(extracted):
            match_span = _find_note_span(clinical_note, item)
            if match_span is None:
                continue
            start, end = match_span
            span = doc.char_span(start, end, label="HPO", alignment_mode="expand")
            if span is None:
                continue
            spans.append(span)
            span_key_by_index[index] = (span.start_char, span.end_char)

        doc.ents = filter_spans(spans)
        if "medspacy_context" not in nlp.pipe_names:
            raise RuntimeError("medspaCy context pipeline does not include medspacy_context.")
        doc = nlp.get_pipe("medspacy_context")(doc)
    except Exception as exc:
        raise RuntimeError(f"medspaCy context pipeline could not be initialized: {exc}") from exc

    entity_by_key = {(ent.start_char, ent.end_char): ent for ent in getattr(doc, "ents", [])}
    output: list[ExtractedPhenotype] = []
    for index, item in enumerate(extracted):
        span_key = span_key_by_index.get(index)
        ent = entity_by_key.get(span_key) if span_key is not None else None
        negated = bool(ent is not None and getattr(ent._, "is_negated", False))
        trigger = _medspacy_trigger(ent) if ent is not None else ""
        scope = getattr(getattr(ent, "sent", None), "text", "") if ent is not None else _sentence_for_match(clinical_note, item)
        if negated:
            output.append(
                _with_context(
                    item,
                    "negated",
                    "medspacy_context",
                    trigger=trigger,
                    scope=scope,
                    weight=0.0,
                    selected=False,
                    exclusion_reason="negated",
                )
            )
        else:
            output.append(_with_context(item, "present", "medspacy_context", trigger=trigger, scope=scope, weight=1.0, selected=True))
    return output


def _annotate_with_llm_qc(
    clinical_note: str,
    extracted: list[ExtractedPhenotype],
    llm_selector: PhenotypeLLMSelector,
) -> list[ExtractedPhenotype]:
    selected = llm_selector.select(clinical_note, extracted, protocol="p2_qc")
    selected_by_id = {item.hpo_id: item for item in selected}
    output: list[ExtractedPhenotype] = []
    for item in extracted:
        selected_item = selected_by_id.get(item.hpo_id)
        if selected_item is not None:
            output.append(
                _with_context(
                    selected_item,
                    "present",
                    "llm_qc",
                    weight=1.0,
                    selected=True,
                )
            )
            continue
        output.append(
            _with_context(
                item,
                "uncertain",
                "llm_qc",
                weight=0.0,
                selected=False,
                exclusion_reason="llm_qc_rejected",
            )
        )
    return output


def _with_context(
    item: ExtractedPhenotype,
    label: str,
    method: str,
    *,
    trigger: str | None = None,
    scope: str | None = None,
    weight: float,
    selected: bool,
    exclusion_reason: str | None = None,
) -> ExtractedPhenotype:
    metadata = {
        **(item.metadata or {}),
        "context_label": label,
        "context_method": method,
        "context_trigger": trigger or "",
        "context_scope": (scope or "")[:500],
        "context_weight": weight,
        "final_selected": selected,
        "exclusion_reason": exclusion_reason or "",
    }
    return replace(item, metadata=metadata)


def _sentence_for_match(clinical_note: str, item: ExtractedPhenotype) -> str:
    candidates = [item.matched_text, item.name]
    for sentence in _sentences(clinical_note):
        normalized_sentence = _normalize(sentence)
        if any(_normalize(candidate) in normalized_sentence for candidate in candidates if candidate):
            return sentence.strip()
    return clinical_note.strip()[:500]


def _find_note_span(clinical_note: str, item: ExtractedPhenotype) -> tuple[int, int] | None:
    for candidate in (item.matched_text, item.name):
        if not candidate:
            continue
        pattern = _loose_text_pattern(candidate)
        match = re.search(pattern, clinical_note, flags=re.IGNORECASE)
        if match is not None:
            return match.start(), match.end()
    return None


def _loose_text_pattern(text: str) -> str:
    tokens = [re.escape(token) for token in _normalize(text).split() if token]
    if not tokens:
        return r"$^"
    return rf"(?<![a-z0-9]){r'[^a-z0-9]+'.join(tokens)}(?![a-z0-9])"


def _medspacy_trigger(ent: object) -> str:
    modifiers = getattr(getattr(ent, "_", None), "modifiers", []) or []
    categories = [str(getattr(modifier, "category", "")) for modifier in modifiers]
    return ", ".join(category for category in categories if category) or "medspacy_context"


def _find_negation_trigger(sentence: str, item: ExtractedPhenotype, *, use_window: bool) -> str | None:
    normalized_sentence = _normalize(sentence)
    match_text = _normalize(item.matched_text or item.name)
    match_index = normalized_sentence.find(match_text)
    if match_index < 0:
        match_index = normalized_sentence.find(_normalize(item.name))
    if match_index < 0:
        return None

    before = normalized_sentence[:match_index].strip()
    after = normalized_sentence[match_index + len(match_text):].strip()
    before_scope = _after_last_terminator(before)
    after_scope = _before_first_terminator(after)
    if use_window:
        before_scope = _last_tokens(before_scope, 8)
        after_scope = _first_tokens(after_scope, 6)

    for trigger in _PRE_NEGATION_TRIGGERS:
        if _contains_phrase(before_scope, trigger):
            return trigger
    for trigger in _POST_NEGATION_TRIGGERS:
        if _contains_phrase(after_scope, trigger):
            return trigger
    return None


def _sentences(text: str) -> list[str]:
    return [part.strip() for part in re.split(r"(?<=[.!?])\s+|\n+", text) if part.strip()]


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", text.lower())).strip()


def _contains_phrase(text: str, phrase: str) -> bool:
    return re.search(rf"(?<![a-z0-9]){re.escape(_normalize(phrase))}(?![a-z0-9])", text) is not None


def _after_last_terminator(text: str) -> str:
    index = -1
    for terminator in _TERMINATORS:
        matches = list(re.finditer(rf"(?<![a-z0-9]){re.escape(terminator)}(?![a-z0-9])", text))
        if matches and matches[-1].end() > index:
            index = matches[-1].end()
    return text[index:] if index >= 0 else text


def _before_first_terminator(text: str) -> str:
    indexes = [
        match.start()
        for terminator in _TERMINATORS
        for match in re.finditer(rf"(?<![a-z0-9]){re.escape(terminator)}(?![a-z0-9])", text)
    ]
    return text[: min(indexes)] if indexes else text


def _last_tokens(text: str, count: int) -> str:
    tokens = text.split()
    return " ".join(tokens[-count:])


def _first_tokens(text: str, count: int) -> str:
    return " ".join(text.split()[:count])
