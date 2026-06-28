from collections import defaultdict
from dataclasses import dataclass
from functools import cached_property

from app.etl.models import DiseasePhenotypeAnnotation, GenePhenotypeAnnotation, KnowledgeBase, PhenotypeTerm


@dataclass(frozen=True)
class DiseaseProfile:
    disease_id: str
    disease_name: str
    phenotype_ids: frozenset[str]


class KnowledgeIndex:
    def __init__(self, kb: KnowledgeBase) -> None:
        self.kb = kb

    @cached_property
    def phenotypes(self) -> dict[str, PhenotypeTerm]:
        return self.kb.phenotypes

    @cached_property
    def disease_profiles(self) -> dict[str, DiseaseProfile]:
        names: dict[str, str] = {}
        phenotype_ids: dict[str, set[str]] = defaultdict(set)
        for annotation in self.kb.disease_phenotypes:
            names[annotation.disease_id] = annotation.disease_name
            phenotype_ids[annotation.disease_id].add(annotation.hpo_id)
        return {
            disease_id: DiseaseProfile(
                disease_id=disease_id,
                disease_name=names[disease_id],
                phenotype_ids=frozenset(ids),
            )
            for disease_id, ids in phenotype_ids.items()
        }

    @cached_property
    def disease_annotations(self) -> dict[str, list[DiseasePhenotypeAnnotation]]:
        annotations: dict[str, list[DiseasePhenotypeAnnotation]] = defaultdict(list)
        for annotation in self.kb.disease_phenotypes:
            annotations[annotation.disease_id].append(annotation)
        return dict(annotations)

    @cached_property
    def hpo_to_diseases(self) -> dict[str, set[str]]:
        mapping: dict[str, set[str]] = defaultdict(set)
        for annotation in self.kb.disease_phenotypes:
            mapping[annotation.hpo_id].add(annotation.disease_id)
        return dict(mapping)

    @cached_property
    def disease_genes(self) -> dict[str, set[str]]:
        mapping: dict[str, set[str]] = defaultdict(set)
        for annotation in self.kb.gene_phenotypes:
            if annotation.disease_id:
                mapping[annotation.disease_id].add(annotation.gene_symbol)
        return dict(mapping)

    @cached_property
    def disease_gene_phenotypes(self) -> dict[str, dict[str, set[str]]]:
        mapping: dict[str, dict[str, set[str]]] = defaultdict(lambda: defaultdict(set))
        for annotation in self.kb.gene_phenotypes:
            if annotation.disease_id:
                mapping[annotation.disease_id][annotation.hpo_id].add(annotation.gene_symbol)
        return {disease_id: dict(hpo_map) for disease_id, hpo_map in mapping.items()}

    @cached_property
    def gene_phenotypes(self) -> dict[str, list[GenePhenotypeAnnotation]]:
        mapping: dict[str, list[GenePhenotypeAnnotation]] = defaultdict(list)
        for annotation in self.kb.gene_phenotypes:
            mapping[annotation.gene_symbol].append(annotation)
        return dict(mapping)

    def get_disease_name(self, disease_id: str) -> str:
        profile = self.disease_profiles.get(disease_id)
        return profile.disease_name if profile else disease_id

    def get_phenotype_name(self, hpo_id: str) -> str | None:
        term = self.phenotypes.get(hpo_id)
        return term.name if term else None
