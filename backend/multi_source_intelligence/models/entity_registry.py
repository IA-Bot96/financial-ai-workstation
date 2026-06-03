"""Entity registry contracts for MSIL Phase 1."""

from __future__ import annotations

import re
from collections import Counter
from typing import Iterable

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .enums import (
    AliasType,
    EntityStatus,
    EntityType,
    RelationshipType,
)
from .versioning import CURRENT_ENTITY_REGISTRY_VERSION


def normalize_identifier(value: str) -> str:
    """Normalize entity identifiers for deterministic registry matching."""

    value = value.lower().replace("&", " and ")
    value = re.sub(r"[^a-z0-9]+", " ", value)
    return re.sub(r"\s+", " ", value).strip()


class EntityAlias(BaseModel):
    """One normalized alias attached to an entity."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    value: str = Field(..., min_length=1)
    alias_type: AliasType = Field(..., description="Frozen alias type.")
    normalized_value: str | None = Field(
        default=None,
        description="Computed normalized value; filled when omitted.",
    )
    exact_match: bool = Field(
        default=False,
        description="Whether this alias is eligible for exact resolution.",
    )
    historical: bool = Field(default=False)
    requires_confirmation: bool = Field(default=False)
    notes: str | None = Field(default=None)

    @model_validator(mode="before")
    @classmethod
    def _normalize_alias(cls, data: object) -> object:
        if isinstance(data, dict) and not data.get("normalized_value"):
            value = str(data.get("value", ""))
            return {**data, "normalized_value": normalize_identifier(value)}
        return data


class EntityRelationship(BaseModel):
    """Directed relationship between registry entities."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    rel_type: RelationshipType = Field(..., description="Relationship type.")
    target_canonical_id: str = Field(..., min_length=1)
    requires_confirmation: bool = Field(default=False)
    notes: str | None = Field(default=None)


class Entity(BaseModel):
    """Canonical entity registry record."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    canonical_id: str = Field(..., min_length=1)
    entity_type: EntityType = Field(..., description="Entity type.")
    display_name: str = Field(..., min_length=1)
    aliases: tuple[EntityAlias, ...] = Field(default_factory=tuple)
    relationships: tuple[EntityRelationship, ...] = Field(default_factory=tuple)
    status: EntityStatus = Field(default=EntityStatus.ACTIVE)
    merged_into: str | None = Field(default=None)
    entity_registry_version: str = Field(
        default=CURRENT_ENTITY_REGISTRY_VERSION,
        min_length=1,
    )

    @property
    def normalized_display_name(self) -> str:
        """Return the normalized display name."""

        return normalize_identifier(self.display_name)

    @model_validator(mode="after")
    def _validate_tombstone(self) -> "Entity":
        if self.status == EntityStatus.MERGED and not self.merged_into:
            raise ValueError("merged entities require merged_into.")
        if self.status != EntityStatus.MERGED and self.merged_into:
            raise ValueError("only merged entities may carry merged_into.")
        alias_values = [alias.normalized_value for alias in self.aliases]
        duplicates = {value for value in alias_values if alias_values.count(value) > 1}
        if duplicates:
            raise ValueError(
                "entity aliases contain duplicates: "
                + ", ".join(sorted(value for value in duplicates if value))
            )
        return self


class EntityRegistry(BaseModel):
    """Frozen entity registry used by the deterministic resolver."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    entity_registry_version: str = Field(
        default=CURRENT_ENTITY_REGISTRY_VERSION,
        min_length=1,
    )
    entities: tuple[Entity, ...] = Field(..., min_length=1)

    @model_validator(mode="after")
    def _validate_registry(self) -> "EntityRegistry":
        canonical_ids = [entity.canonical_id for entity in self.entities]
        duplicates = {
            canonical_id
            for canonical_id in canonical_ids
            if canonical_ids.count(canonical_id) > 1
        }
        if duplicates:
            raise ValueError(
                "canonical_id values must be unique: " + ", ".join(sorted(duplicates))
            )

        entities_by_id = {entity.canonical_id: entity for entity in self.entities}
        self._validate_alias_uniqueness_within_entity_type()
        self._validate_relationships(entities_by_id)
        self._validate_tombstone_targets(entities_by_id)
        return self

    def entity_by_id(self, canonical_id: str) -> Entity | None:
        """Return an entity by canonical id."""

        return next(
            (entity for entity in self.entities if entity.canonical_id == canonical_id),
            None,
        )

    def active_entities(self) -> tuple[Entity, ...]:
        """Return active entities only."""

        return tuple(entity for entity in self.entities if entity.status == EntityStatus.ACTIVE)

    def aliases(self) -> tuple[tuple[Entity, EntityAlias], ...]:
        """Return all active entity aliases with their owning entity."""

        return tuple(
            (entity, alias)
            for entity in self.active_entities()
            for alias in entity.aliases
        )

    def relationship_count(self) -> int:
        """Return total relationship count."""

        return sum(len(entity.relationships) for entity in self.entities)

    def alias_count(self) -> int:
        """Return total alias count."""

        return sum(len(entity.aliases) for entity in self.entities)

    def _validate_alias_uniqueness_within_entity_type(self) -> None:
        by_scope: dict[tuple[EntityType, str], list[str]] = {}
        for entity in self.entities:
            if entity.status != EntityStatus.ACTIVE:
                continue
            for alias in entity.aliases:
                if not alias.normalized_value:
                    continue
                key = (entity.entity_type, alias.normalized_value)
                by_scope.setdefault(key, []).append(entity.canonical_id)
        duplicates = {
            key: owners
            for key, owners in by_scope.items()
            if len(set(owners)) > 1
        }
        if duplicates:
            details = [
                f"{entity_type.value}:{alias} -> {sorted(set(owners))}"
                for (entity_type, alias), owners in duplicates.items()
            ]
            raise ValueError(
                "aliases must be unique within entity type: " + "; ".join(details)
            )

    def _validate_relationships(self, entities_by_id: dict[str, Entity]) -> None:
        for source in self.entities:
            for relationship in source.relationships:
                target = entities_by_id.get(relationship.target_canonical_id)
                if target is None:
                    raise ValueError(
                        "relationship target does not exist: "
                        f"{source.canonical_id}->{relationship.target_canonical_id}"
                    )
                _validate_relationship_shape(source, target, relationship.rel_type)

    def _validate_tombstone_targets(self, entities_by_id: dict[str, Entity]) -> None:
        for entity in self.entities:
            if entity.status == EntityStatus.MERGED:
                if entity.merged_into == entity.canonical_id:
                    raise ValueError("merged entity cannot point to itself.")
                if entity.merged_into not in entities_by_id:
                    raise ValueError(
                        f"merged_into target does not exist: {entity.merged_into}"
                    )


def _validate_relationship_shape(
    source: Entity,
    target: Entity,
    rel_type: RelationshipType,
) -> None:
    if rel_type == RelationshipType.SECURITY_OF:
        _require_types(source, target, EntityType.SECURITY, EntityType.COMPANY, rel_type)
    elif rel_type == RelationshipType.MEMBER_OF_SECTOR:
        if source.entity_type not in {EntityType.COMPANY, EntityType.SECURITY}:
            raise ValueError("member_of_sector source must be company or security.")
        if target.entity_type != EntityType.SECTOR:
            raise ValueError("member_of_sector target must be sector.")
    elif rel_type in {RelationshipType.PARENT_OF, RelationshipType.SUBSIDIARY_OF}:
        _require_types(source, target, EntityType.COMPANY, EntityType.COMPANY, rel_type)
    elif rel_type == RelationshipType.FUTURES_ON:
        _require_types(
            source,
            target,
            EntityType.FUTURES_INSTRUMENT,
            EntityType.SECURITY,
            rel_type,
        )
    elif rel_type == RelationshipType.PERSON_OF:
        _require_types(source, target, EntityType.PERSON, EntityType.COMPANY, rel_type)


def _require_types(
    source: Entity,
    target: Entity,
    source_type: EntityType,
    target_type: EntityType,
    rel_type: RelationshipType,
) -> None:
    if source.entity_type != source_type or target.entity_type != target_type:
        raise ValueError(
            f"{rel_type.value} requires {source_type.value}->{target_type.value}."
        )


def duplicate_normalized_values(values: Iterable[str]) -> set[str]:
    """Return duplicate normalized values for diagnostics."""

    counts = Counter(normalize_identifier(value) for value in values)
    return {value for value, count in counts.items() if count > 1}


__all__ = [
    "Entity",
    "EntityAlias",
    "EntityRelationship",
    "EntityRegistry",
    "duplicate_normalized_values",
    "normalize_identifier",
]
