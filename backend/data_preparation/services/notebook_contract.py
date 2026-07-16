import re
from pathlib import Path
from typing import List, Optional, Set


NOTEBOOK_REQUIRED_TABLES: Set[str] = {
    "banks",
    "financial_summary",
    "governance",
    "targets",
    "travel_records",
    "utility_invoices",
    "vehicles",
    "exposures",
    "counterparties",
    "counterparty_emissions",
    "investments",
    "climate_risk_register",
    "climate_scenarios",
    "physical_risk_exposures",
    "collateral",
    "facilities",
    "source_systems",
    "board_minutes_extract",
    "carbon_credits",
}


NOTEBOOK_OPTIONAL_TABLES: Set[str] = {
    "internal_carbon_price",
    "value_chain_map",
    "climate_opportunities",
    "scope3_categories",
    "transition_plan",
    "climate_financial_effects",
    "resilience_assessment",
    "ghg_methodology",
    "scope12_consolidation",
    "employees",
    "portfolio_composition",
    "rec_registry",
}


NOTEBOOK_EXPECTED_TABLES: Set[str] = NOTEBOOK_REQUIRED_TABLES | NOTEBOOK_OPTIONAL_TABLES


SOURCE_TABLE_ALIASES = {
    # Travel
    "business_travel": "travel_records",
    "business_travel_records": "travel_records",
    "travel": "travel_records",
    "flights": "travel_records",

    # Fleet
    "fleet_vehicles": "vehicles",
    "fleet": "vehicles",
    "vehicle_fleet": "vehicles",
    "cars": "vehicles",

    # Counterparty emissions
    "counterparty_emission": "counterparty_emissions",
    "counterparty_emissions": "counterparty_emissions",
    "client_emissions": "counterparty_emissions",
    "customer_emissions": "counterparty_emissions",
    "borrower_emissions": "counterparty_emissions",
    "emissions_counterparties": "counterparty_emissions",

    # Other aliases
    "board_minutes": "board_minutes_extract",
    "minutes": "board_minutes_extract",
    "physical_risk": "physical_risk_exposures",
    "hazard_exposures": "physical_risk_exposures",
    "carbon_credit": "carbon_credits",
    "offsets": "carbon_credits",
    "scope_3_categories": "scope3_categories",
    "scope_1_2_consolidation": "scope12_consolidation",
    "rec": "rec_registry",
    "renewable_certificates": "rec_registry",
    "renewable_certificate_registry": "rec_registry",
    "climate_financial_impact": "climate_financial_effects",
}


def normalize_table_name(value: Optional[str]) -> str:
    if not value:
        return ""

    value = Path(str(value)).stem
    value = value.strip().lower()
    value = re.sub(r"[^a-z0-9]+", "_", value)
    value = re.sub(r"_+", "_", value)
    return value.strip("_")


def resolve_by_keywords(normalized_name: str) -> Optional[str]:
    """
    Fallback rules for client file names that are not exact.
    Example:
        client_counterparty_ghg_export.csv -> counterparty_emissions
    """

    if not normalized_name:
        return None

    if "counterparty" in normalized_name and (
        "emission" in normalized_name or "ghg" in normalized_name
    ):
        return "counterparty_emissions"

    if "client" in normalized_name and (
        "emission" in normalized_name or "ghg" in normalized_name
    ):
        return "counterparty_emissions"

    if "travel" in normalized_name or "flight" in normalized_name:
        return "travel_records"

    if "vehicle" in normalized_name or "fleet" in normalized_name:
        return "vehicles"

    if "board" in normalized_name and "minute" in normalized_name:
        return "board_minutes_extract"

    if "physical" in normalized_name and "risk" in normalized_name:
        return "physical_risk_exposures"

    if "carbon" in normalized_name and "credit" in normalized_name:
        return "carbon_credits"

    if "renewable" in normalized_name and "certificate" in normalized_name:
        return "rec_registry"

    return None


def resolve_notebook_table_name(
    source_filename: Optional[str],
    detected_table: Optional[str],
) -> str:
    """
    Resolves the final CSV/table name expected by the notebook.

    Priority:
    1. Source filename exact match.
    2. Source filename alias.
    3. Source filename keyword rule.
    4. Detected table exact match.
    5. Detected table alias.
    6. Detected table keyword rule.
    7. Fallback to detected table.
    """

    source_name = normalize_table_name(source_filename)
    detected_name = normalize_table_name(detected_table)

    if source_name in NOTEBOOK_EXPECTED_TABLES:
        return source_name

    if source_name in SOURCE_TABLE_ALIASES:
        return SOURCE_TABLE_ALIASES[source_name]

    keyword_match = resolve_by_keywords(source_name)
    if keyword_match:
        return keyword_match

    if detected_name in NOTEBOOK_EXPECTED_TABLES:
        return detected_name

    if detected_name in SOURCE_TABLE_ALIASES:
        return SOURCE_TABLE_ALIASES[detected_name]

    keyword_match = resolve_by_keywords(detected_name)
    if keyword_match:
        return keyword_match

    return detected_name


def list_available_notebook_tables(folder: Path) -> List[str]:
    if not folder.exists():
        return []

    return sorted(
        normalize_table_name(path.stem)
        for path in folder.glob("*.csv")
    )


def find_missing_required_notebook_tables(folder: Path) -> List[str]:
    available = set(list_available_notebook_tables(folder))
    return sorted(NOTEBOOK_REQUIRED_TABLES - available)