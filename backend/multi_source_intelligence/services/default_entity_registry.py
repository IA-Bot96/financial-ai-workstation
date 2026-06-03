"""Seeded MVP entity registry for MSIL Phase 1 truth-set validation."""

from __future__ import annotations

from multi_source_intelligence.models import (
    AliasType,
    Entity,
    EntityAlias,
    EntityRegistry,
    EntityRelationship,
    EntityType,
    RelationshipType,
)


def default_entity_registry() -> EntityRegistry:
    """Return the seeded Lucky/Millat MVP registry.

    The seed intentionally excludes ambiguity-prone bare tokens such as
    "Lucky", "Millat", "ICI", and "Yunus"; those are handled by the resolver's
    review path so the registry does not silently contaminate one company with
    another.
    """

    return EntityRegistry(
        entities=(
            *_sector_entities(),
            *_lucky_group_entities(),
            *_millat_group_entities(),
            *_security_entities(),
        )
    )


def _sector_entities() -> tuple[Entity, ...]:
    return (
        Entity(
            canonical_id="sector_cement",
            entity_type=EntityType.SECTOR,
            display_name="Cement",
            aliases=(_alias("Cement", AliasType.NAME_VARIANT, exact=True),),
        ),
        Entity(
            canonical_id="sector_chemicals",
            entity_type=EntityType.SECTOR,
            display_name="Chemicals",
            aliases=(_alias("Chemicals", AliasType.NAME_VARIANT, exact=True),),
        ),
        Entity(
            canonical_id="sector_power",
            entity_type=EntityType.SECTOR,
            display_name="Power",
            aliases=(_alias("Power", AliasType.NAME_VARIANT, exact=True),),
        ),
        Entity(
            canonical_id="sector_automobile_assembler",
            entity_type=EntityType.SECTOR,
            display_name="Automobile Assembler",
            aliases=(
                _alias("Automobile Assembler", AliasType.NAME_VARIANT, exact=True),
                _alias("Tractors", AliasType.NAME_VARIANT),
            ),
        ),
        Entity(
            canonical_id="sector_automobile_parts",
            entity_type=EntityType.SECTOR,
            display_name="Automobile Parts",
            aliases=(
                _alias("Automobile Parts", AliasType.NAME_VARIANT, exact=True),
                _alias("Auto Parts", AliasType.NAME_VARIANT),
            ),
        ),
        Entity(
            canonical_id="sector_textile",
            entity_type=EntityType.SECTOR,
            display_name="Textile",
            aliases=(_alias("Textile", AliasType.NAME_VARIANT, exact=True),),
        ),
    )


def _lucky_group_entities() -> tuple[Entity, ...]:
    return (
        Entity(
            canonical_id="yunus_brothers_group",
            entity_type=EntityType.COMPANY,
            display_name="Yunus Brothers Group",
            aliases=(
                _alias("Yunus Brothers Group", AliasType.LEGAL_NAME, exact=True),
                _alias("YBG", AliasType.NAME_VARIANT),
                _alias("Yunus Brothers", AliasType.NAME_VARIANT),
            ),
            relationships=(
                _rel(RelationshipType.PARENT_OF, "lucky_cement"),
                _rel(RelationshipType.PARENT_OF, "lucky_core_industries"),
                _rel(RelationshipType.PARENT_OF, "lucky_motor_corporation"),
                _rel(RelationshipType.PARENT_OF, "lucky_electric_power"),
                _rel(RelationshipType.PARENT_OF, "yunus_textile_mills"),
            ),
        ),
        Entity(
            canonical_id="lucky_cement",
            entity_type=EntityType.COMPANY,
            display_name="Lucky Cement Limited",
            aliases=(
                _alias("Lucky Cement Limited", AliasType.LEGAL_NAME, exact=True),
                _alias("Lucky Cement", AliasType.NAME_VARIANT),
                _alias("Lucky Cement Ltd", AliasType.NAME_VARIANT),
                _alias("LCL", AliasType.NAME_VARIANT),
            ),
            relationships=(
                _rel(RelationshipType.SUBSIDIARY_OF, "yunus_brothers_group"),
                _rel(RelationshipType.MEMBER_OF_SECTOR, "sector_cement"),
            ),
        ),
        Entity(
            canonical_id="lucky_core_industries",
            entity_type=EntityType.COMPANY,
            display_name="Lucky Core Industries Limited",
            aliases=(
                _alias("Lucky Core Industries Limited", AliasType.LEGAL_NAME, exact=True),
                _alias(
                    "ICI Pakistan Limited",
                    AliasType.LEGAL_NAME,
                    exact=True,
                    historical=True,
                    confirm=True,
                ),
                _alias("Lucky Core", AliasType.NAME_VARIANT),
                _alias("Lucky Core Industries", AliasType.NAME_VARIANT),
            ),
            relationships=(
                _rel(RelationshipType.SUBSIDIARY_OF, "yunus_brothers_group"),
                _rel(RelationshipType.MEMBER_OF_SECTOR, "sector_chemicals"),
            ),
        ),
        Entity(
            canonical_id="lucky_motor_corporation",
            entity_type=EntityType.COMPANY,
            display_name="Lucky Motor Corporation (Pvt) Limited",
            aliases=(
                _alias(
                    "Lucky Motor Corporation (Pvt) Limited",
                    AliasType.LEGAL_NAME,
                    exact=True,
                ),
                _alias("Lucky Motor", AliasType.NAME_VARIANT),
                _alias("Lucky Motors", AliasType.NAME_VARIANT),
                _alias("LMC", AliasType.NAME_VARIANT),
            ),
            relationships=(
                _rel(RelationshipType.SUBSIDIARY_OF, "yunus_brothers_group"),
                _rel(RelationshipType.MEMBER_OF_SECTOR, "sector_automobile_assembler"),
            ),
        ),
        Entity(
            canonical_id="lucky_electric_power",
            entity_type=EntityType.COMPANY,
            display_name="Lucky Electric Power Company Limited",
            aliases=(
                _alias(
                    "Lucky Electric Power Company Limited",
                    AliasType.LEGAL_NAME,
                    exact=True,
                    confirm=True,
                ),
                _alias("Lucky Electric", AliasType.NAME_VARIANT),
                _alias("LEPL", AliasType.NAME_VARIANT),
            ),
            relationships=(
                _rel(RelationshipType.SUBSIDIARY_OF, "yunus_brothers_group"),
                _rel(RelationshipType.MEMBER_OF_SECTOR, "sector_power"),
            ),
        ),
        Entity(
            canonical_id="yunus_textile_mills",
            entity_type=EntityType.COMPANY,
            display_name="Yunus Textile Mills Limited",
            aliases=(
                _alias(
                    "Yunus Textile Mills Limited",
                    AliasType.LEGAL_NAME,
                    exact=True,
                    confirm=True,
                ),
                _alias("Yunus Textile", AliasType.NAME_VARIANT),
                _alias("YTML", AliasType.NAME_VARIANT),
            ),
            relationships=(
                _rel(RelationshipType.SUBSIDIARY_OF, "yunus_brothers_group"),
                _rel(RelationshipType.MEMBER_OF_SECTOR, "sector_textile"),
            ),
        ),
    )


def _millat_group_entities() -> tuple[Entity, ...]:
    return (
        Entity(
            canonical_id="millat_tractors",
            entity_type=EntityType.COMPANY,
            display_name="Millat Tractors Limited",
            aliases=(
                _alias("Millat Tractors Limited", AliasType.LEGAL_NAME, exact=True),
                _alias("Millat Tractors", AliasType.NAME_VARIANT),
                _alias("Millat Tractor", AliasType.NAME_VARIANT),
            ),
            relationships=(
                _rel(RelationshipType.MEMBER_OF_SECTOR, "sector_automobile_assembler"),
            ),
        ),
        Entity(
            canonical_id="millat_industrial_products",
            entity_type=EntityType.COMPANY,
            display_name="Millat Industrial Products Limited",
            aliases=(
                _alias(
                    "Millat Industrial Products Limited",
                    AliasType.LEGAL_NAME,
                    exact=True,
                    confirm=True,
                ),
                _alias("Millat Industrial", AliasType.NAME_VARIANT),
                _alias("MIPL", AliasType.NAME_VARIANT, confirm=True),
            ),
            relationships=(
                _rel(RelationshipType.MEMBER_OF_SECTOR, "sector_automobile_parts"),
            ),
        ),
        Entity(
            canonical_id="millat_equipment",
            entity_type=EntityType.COMPANY,
            display_name="Millat Equipment Limited",
            aliases=(
                _alias(
                    "Millat Equipment Limited",
                    AliasType.LEGAL_NAME,
                    exact=True,
                    confirm=True,
                ),
                _alias("Millat Equipment", AliasType.NAME_VARIANT),
                _alias("MEL", AliasType.NAME_VARIANT, confirm=True),
            ),
            relationships=(
                _rel(RelationshipType.MEMBER_OF_SECTOR, "sector_automobile_parts"),
            ),
        ),
        Entity(
            canonical_id="bolan_castings",
            entity_type=EntityType.COMPANY,
            display_name="Bolan Castings Limited",
            aliases=(
                _alias(
                    "Bolan Castings Limited",
                    AliasType.LEGAL_NAME,
                    exact=True,
                    confirm=True,
                ),
                _alias("Bolan Castings", AliasType.NAME_VARIANT),
                _alias("Bolan Casting", AliasType.NAME_VARIANT),
            ),
            relationships=(
                _rel(RelationshipType.MEMBER_OF_SECTOR, "sector_automobile_parts"),
            ),
        ),
    )


def _security_entities() -> tuple[Entity, ...]:
    return (
        Entity(
            canonical_id="sec_luck",
            entity_type=EntityType.SECURITY,
            display_name="LUCK Ordinary Share",
            aliases=(_alias("LUCK", AliasType.TICKER, exact=True),),
            relationships=(_rel(RelationshipType.SECURITY_OF, "lucky_cement"),),
        ),
        Entity(
            canonical_id="sec_lci",
            entity_type=EntityType.SECURITY,
            display_name="LCI Ordinary Share",
            aliases=(_alias("LCI", AliasType.TICKER, exact=True, confirm=True),),
            relationships=(_rel(RelationshipType.SECURITY_OF, "lucky_core_industries"),),
        ),
        Entity(
            canonical_id="sec_mtl",
            entity_type=EntityType.SECURITY,
            display_name="MTL Ordinary Share",
            aliases=(_alias("MTL", AliasType.TICKER, exact=True),),
            relationships=(_rel(RelationshipType.SECURITY_OF, "millat_tractors"),),
        ),
        Entity(
            canonical_id="sec_bcl",
            entity_type=EntityType.SECURITY,
            display_name="BCL Ordinary Share",
            aliases=(_alias("BCL", AliasType.TICKER, exact=True, confirm=True),),
            relationships=(_rel(RelationshipType.SECURITY_OF, "bolan_castings"),),
        ),
    )


def _alias(
    value: str,
    alias_type: AliasType,
    *,
    exact: bool = False,
    historical: bool = False,
    confirm: bool = False,
) -> EntityAlias:
    return EntityAlias(
        value=value,
        alias_type=alias_type,
        exact_match=exact,
        historical=historical,
        requires_confirmation=confirm,
    )


def _rel(
    rel_type: RelationshipType,
    target_canonical_id: str,
    *,
    confirm: bool = False,
) -> EntityRelationship:
    return EntityRelationship(
        rel_type=rel_type,
        target_canonical_id=target_canonical_id,
        requires_confirmation=confirm,
    )


__all__ = ["default_entity_registry"]
