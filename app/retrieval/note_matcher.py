import re
from dataclasses import dataclass

from app.retrieval.knowledge import KnowledgeIndex


@dataclass(frozen=True)
class ExtractedPhenotype:
    hpo_id: str
    name: str
    matched_text: str
    confidence: float
    source: str = "dictionary"


class ClinicalNoteMatcher:
    def __init__(self, knowledge: KnowledgeIndex, min_phrase_length: int = 4) -> None:
        self.knowledge = knowledge
        self.min_phrase_length = min_phrase_length
        self._entries = self._build_entries()

    def extract(self, clinical_note: str, limit: int = 30) -> list[ExtractedPhenotype]:
        normalized_note = _normalize_text(clinical_note)
        found: dict[str, ExtractedPhenotype] = {}
        for phrase, hpo_id, source in self._entries:
            pattern = rf"(?<![a-z0-9]){re.escape(phrase)}(?![a-z0-9])"
            if not re.search(pattern, normalized_note):
                continue
            term = self.knowledge.phenotypes[hpo_id]
            current = found.get(hpo_id)
            confidence = 1.0 if source == "name" else 0.85
            if current is None or confidence > current.confidence:
                found[hpo_id] = ExtractedPhenotype(
                    hpo_id=hpo_id,
                    name=term.name,
                    matched_text=phrase,
                    confidence=confidence,
                )

        extracted = sorted(found.values(), key=lambda item: (-item.confidence, item.name))
        return extracted[:limit]

    def _build_entries(self) -> list[tuple[str, str, str]]:
        entries: list[tuple[str, str, str]] = []
        for hpo_id, term in self.knowledge.phenotypes.items():
            candidates = [(term.name, "name"), *[(synonym, "synonym") for synonym in term.synonyms]]
            for text, source in candidates:
                phrase = _normalize_text(text)
                if len(phrase) < self.min_phrase_length:
                    continue
                entries.append((phrase, hpo_id, source))
        entries.sort(key=lambda entry: len(entry[0]), reverse=True)
        return entries


def _normalize_text(text: str) -> str:
    lowered = text.lower()
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", lowered)).strip()

