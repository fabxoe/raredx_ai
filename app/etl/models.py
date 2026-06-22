from dataclasses import dataclass, field


@dataclass(frozen=True)
class PhenotypeTerm:
    hpo_id: str
    name: str
    definition: str | None = None
    parents: tuple[str, ...] = field(default_factory=tuple)
    synonyms: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class DiseasePhenotypeAnnotation:
    disease_id: str
    disease_name: str
    hpo_id: str
    frequency: str | None = None
    evidence: str | None = None
    source: str | None = None


@dataclass(frozen=True)
class GenePhenotypeAnnotation:
    gene_id: str
    gene_symbol: str
    hpo_id: str
    hpo_name: str | None = None
    disease_id: str | None = None
    disease_name: str | None = None
    source: str | None = None


@dataclass(frozen=True)
class KnowledgeBase:
    phenotypes: dict[str, PhenotypeTerm]
    disease_phenotypes: list[DiseasePhenotypeAnnotation]
    gene_phenotypes: list[GenePhenotypeAnnotation]
