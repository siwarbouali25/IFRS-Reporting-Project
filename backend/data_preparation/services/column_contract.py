from typing import Dict, List


def unique_list(values: List[str]) -> List[str]:
    seen = set()
    result = []

    for value in values:
        if value not in seen:
            result.append(value)
            seen.add(value)

    return result


GLOBAL_COLUMN_ALIASES: Dict[str, List[str]] = {
    "bank_id": [
        "bank_id",
        "entity_id",
        "institution_id",
        "company_id",
        "organisation_id",
        "organization_id",
    ],
    "bank_name": [
        "bank_name",
        "entity_name",
        "company_name",
        "institution_name",
        "organisation_name",
        "organization_name",
        "client_name",
        "name",
    ],
    "reporting_year": [
        "reporting_year",
        "year",
        "fiscal_year",
        "fy",
        "report_year",
        "reporting_period",
    ],
    "reporting_currency": [
        "reporting_currency",
        "currency",
        "ccy",
    ],
    "country": [
        "country",
        "country_code",
        "jurisdiction",
        "location_country",
    ],
    "counterparty_id": [
        "counterparty_id",
        "client_id",
        "customer_id",
        "borrower_id",
        "obligor_id",
        "company_id",
    ],
    "exposure_id": [
        "exposure_id",
        "loan_id",
        "facility_id",
        "credit_id",
        "contract_id",
        "deal_id",
    ],
    "outstanding_amount_meur": [
        "outstanding_amount_meur",
        "outstanding_amount",
        "outstanding_balance",
        "loan_balance",
        "exposure_amount",
        "exposure_amount_meur",
        "ead",
        "gross_carrying_amount",
    ],
    "committed_amount_meur": [
        "committed_amount_meur",
        "committed_amount",
        "commitment_amount",
        "limit_amount",
        "approved_amount",
    ],
    "total_assets_meur": [
        "total_assets_meur",
        "total_assets",
        "assets",
        "assets_meur",
        "total_assets_eurm",
        "total_assets_eur_m",
    ],
    "total_loans_meur": [
        "total_loans_meur",
        "total_loans",
        "loans",
        "loan_book",
        "loan_portfolio",
        "gross_loans",
    ],
    "emissions_tco2e": [
        "emissions_tco2e",
        "emissions",
        "ghg_emissions",
        "co2e",
        "tco2e",
    ],
    "total_ghg_tco2e": [
        "total_ghg_tco2e",
        "total_ghg",
        "total_emissions",
        "total_emissions_tco2e",
        "ghg_total",
        "total_co2e",
    ],
}


NOTEBOOK_TABLE_CONTRACT: Dict[str, Dict[str, List[str]]] = {
    "banks": {
        "required": [
            "bank_id",
            "bank_name",
            "total_assets_meur",
            "total_loans_meur",
        ],
        "optional": [
            "archetype",
            "country",
            "headcount",
            "established_year",
            "reporting_currency",
            "fiscal_year_end",
            "target_intensity_tco2e_per_meur",
            "lei_code",
            "boundary_type",
            "regulatory_regime",
            "in_scope_esg_flag",
            "tier1_capital_meur",
            "cet1_ratio_pct",
        ],
    },
    "financial_summary": {
        "required": [
            "bank_id",
            "reporting_year",
            "total_assets_meur",
            "total_loans_meur",
        ],
        "optional": [
            "green_loans_meur",
            "green_loans_pct",
            "total_revenue_meur",
            "net_profit_meur",
            "climate_capex_meur",
            "climate_opex_meur",
            "tier1_capital_meur",
            "cet1_ratio_pct",
            "carbon_intensity_tco2e_per_meur_lending",
        ],
    },
    "governance": {
        "required": [
            "bank_id",
            "reporting_year",
        ],
        "optional": [
            "board_size",
            "esg_committee_exists",
            "board_climate_expertise_pct",
            "external_assurance",
            "erm_integration_flag",
            "esg_committee_meetings_per_year",
            "ceo_esg_compensation_pct",
            "climate_risk_reporting_to_board",
            "tcfd_aligned",
            "ifrs_s2_aligned",
        ],
    },
    "targets": {
        "required": [
            "target_id",
            "bank_id",
            "target_year",
        ],
        "optional": [
            "target_type",
            "scope",
            "scope_coverage",
            "baseline_year",
            "target_framework",
            "status",
            "metric",
            "baseline_value",
            "target_value_pct_reduction",
            "interim_milestones_json",
            "planned_carbon_credits_pct",
            "progress_metric",
        ],
    },
    "travel_records": {
        "required": [
            "travel_id",
            "bank_id",
            "travel_date",
            "emissions_kg_co2e",
        ],
        "optional": [
            "reporting_year",
            "travel_mode",
            "distance_km",
            "emissions_tco2e",
            "employee_id_hash",
            "emission_factor_kg_co2e_per_km",
            "purpose",
        ],
    },
    "utility_invoices": {
        "required": [
            "bank_id",
            "invoice_year",
            "invoice_month",
            "scope1_gas_tco2e",
            "scope2_location_tco2e",
            "scope2_market_tco2e",
        ],
        "optional": [
            "invoice_id",
            "facility_id",
            "reporting_year",
            "electricity_kwh",
            "electricity_cost_eur",
            "renewable_share_pct",
            "natural_gas_kwh",
            "water_m3",
            "rec_volume_kwh",
            "grid_emission_factor_tco2e_per_mwh",
        ],
    },
    "vehicles": {
        "required": [
            "vehicle_id",
            "bank_id",
            "fuel_type",
            "annual_fuel_consumption_l",
        ],
        "optional": [
            "reporting_year",
            "scope1_tco2e_2024",
            "scope1_tco2e_2024_clean",
            "vehicle_type",
            "registration_year",
            "annual_km_2024",
            "annual_electricity_consumption_kwh",
            "emission_factor_source",
        ],
    },
    "exposures": {
        "required": [
            "exposure_id",
            "bank_id",
            "counterparty_id",
            "outstanding_amount_meur",
        ],
        "optional": [
            "product_type",
            "committed_amount_meur",
            "pcaf_asset_class",
            "origination_date",
            "maturity_date",
            "currency",
            "stage",
            "eu_taxonomy_aligned",
            "green_label_flag",
            "green_taxonomy",
            "total_project_cost_meur",
            "instrument_type",
        ],
    },
    "counterparties": {
        "required": [
            "counterparty_id",
            "bank_id",
            "nace_code",
        ],
        "optional": [
            "legal_name",
            "country",
            "annual_revenue_meur",
            "evic_meur",
            "ppp_adjusted_gdp_meur",
            "national_scope1_tco2e",
            "national_scope2_tco2e",
            "national_scope3_tco2e",
            "data_source_type",
            "transition_risk_score",
        ],
    },
    "counterparty_emissions": {
        "required": [
            "counterparty_id",
            "reporting_year",
            "total_ghg_tco2e",
        ],
        "optional": [
            "emissions_id",
            "bank_id",
            "scope_1_tco2e",
            "scope_2_location_tco2e",
            "scope_2_market_tco2e",
            "scope_3_tco2e",
            "pcaf_data_quality_score",
            "data_source",
            "verification_status",
            "gwp_basis",
        ],
    },
    "investments": {
        "required": [
            "investment_id",
            "bank_id",
            "asset_class",
            "market_value_meur",
            "reporting_year",
        ],
        "optional": [
            "issuer_name",
            "nominal_amount_meur",
            "issuer_evic_meur",
            "nace_code",
            "country",
            "currency",
            "issuer_revenue_meur",
            "ppp_gdp_meur",
            "counterparty_id",
            "pcaf_data_quality_score",
        ],
    },
    "climate_risk_register": {
        "required": [
            "risk_id",
            "bank_id",
            "risk_category",
            "risk_rating",
        ],
        "optional": [
            "risk_name",
            "risk_description",
            "likelihood_score",
            "severity_score",
            "mitigation_actions",
            "reporting_year",
            "time_horizon",
            "financial_impact_meur",
            "erm_integrated_flag",
        ],
    },
    "climate_scenarios": {
        "required": [
            "scenario_id",
            "scenario_name",
            "scenario_type",
        ],
        "optional": [
            "bank_id",
            "framework",
            "temperature_outcome_c",
            "horizon",
            "horizon_year",
            "carbon_price_assumption_eur_per_tco2e",
            "physical_risk_loss_pct_capital",
            "transition_risk_loss_pct_capital",
            "resilience_assessment",
        ],
    },
    "physical_risk_exposures": {
        "required": [
            "physical_risk_id",
            "counterparty_id",
            "hazard_type",
        ],
        "optional": [
            "bank_id",
            "country",
            "acute_risk_score",
            "chronic_risk_score",
            "exposure_amount_meur",
            "assessment_horizon",
            "scenario_basis",
            "high_risk_flag",
            "financial_impact_meur",
            "portfolio_pct",
        ],
    },
    "collateral": {
        "required": [
            "collateral_id",
            "exposure_id",
        ],
        "optional": [
            "bank_id",
            "counterparty_id",
            "collateral_type",
            "country",
            "valuation_amount_meur",
            "market_value_meur",
            "epc_rating",
            "flood_zone_class",
            "flood_risk_score",
            "physical_risk_score",
            "exposure_amount_meur",
            "property_type",
            "ltv_pct",
            "year_built",
            "floor_area_sqm",
            "valuation_date",
            "market_value_at_origination_meur",
            "building_emissions_tco2e",
            "postcode",
        ],
    },
    "facilities": {
        "required": [
            "facility_id",
            "bank_id",
        ],
        "optional": [
            "facility_type",
            "country",
            "city",
            "floor_area_sqm",
            "epc_rating",
            "headcount",
            "year_built",
            "ownership",
        ],
    },
    "board_minutes_extract": {
        "required": [
            "meeting_id",
            "bank_id",
            "meeting_date",
        ],
        "optional": [
            "committee_name",
            "committee_type",
            "reporting_year",
            "climate_agenda_flag",
            "climate_topics_discussed",
            "decision_made_flag",
            "decision_summary",
            "ifrs_s2_para_evidence",
        ],
    },
    "carbon_credits": {
        "required": [
            "credit_id",
            "bank_id",
            "reporting_year",
        ],
        "optional": [
            "credits_tco2e",
            "tonnes_co2e",
            "use",
            "retired_flag",
            "credit_type",
            "permanence_years",
            "permanence_rating",
            "additionality_verified",
            "retirement_year",
        ],
    },
}


TABLE_SPECIFIC_COLUMN_ALIASES: Dict[str, Dict[str, List[str]]] = {
    "banks": {
        "bank_name": ["company", "company_name", "entity", "entity_name", "institution"],
        "total_assets_meur": ["assets", "assets_eur_m", "total_assets_eur_m", "total_assets_m_eur"],
        "total_loans_meur": ["loans", "loan_book", "credit_portfolio", "total_credit"],
    },
    "exposures": {
        "counterparty_id": ["borrower_id", "client_number", "customer_number", "obligor"],
        "outstanding_amount_meur": ["outstanding_balance", "loan_balance", "ead", "exposure", "exposure_amount"],
        "committed_amount_meur": ["limit", "approved_limit", "commitment", "committed_exposure"],
    },
    "counterparty_emissions": {
        "counterparty_id": ["client_id", "borrower_id", "customer_id"],
        "total_ghg_tco2e": ["ghg_total", "total_emissions", "total_co2e", "emissions_total"],
        "scope_1_tco2e": ["scope1", "scope_1", "scope_1_emissions", "scope1_tco2e"],
        "scope_2_location_tco2e": ["scope2_location", "scope_2_location", "scope2_location_tco2e"],
        "scope_2_market_tco2e": ["scope2_market", "scope_2_market", "scope2_market_tco2e"],
        "scope_3_tco2e": ["scope3", "scope_3", "scope_3_emissions", "scope3_tco2e"],
    },
    "travel_records": {
        "travel_date": ["date", "trip_date", "journey_date"],
        "emissions_kg_co2e": ["emissions_kg", "kg_co2e", "co2e_kg", "travel_emissions_kg"],
        "distance_km": ["km", "distance", "travel_distance"],
    },
    "utility_invoices": {
        "invoice_year": ["year", "billing_year", "fiscal_year"],
        "invoice_month": ["month", "billing_month", "invoice_date"],
        "scope1_gas_tco2e": ["gas_emissions", "natural_gas_tco2e", "scope1_gas"],
        "scope2_location_tco2e": ["location_based_scope2", "scope2_location"],
        "scope2_market_tco2e": ["market_based_scope2", "scope2_market"],
    },
}


# ============================================================
# Additional contracts and aliases for robust client CSV mapping
# ============================================================
# These updates reduce false review noise and allow the mapper to
# recognise common client column names without changing notebook logic.

ADDITIONAL_NOTEBOOK_TABLE_CONTRACT: Dict[str, Dict[str, List[str]]] = {
    "employees": {
        "required": ["bank_id", "reporting_year"],
        "optional": [
            "total_headcount", "female_pct", "avg_training_hours_per_employee",
            "board_female_pct", "executive_female_pct", "esg_training_hours_per_employee",
            "ceo_pay_ratio", "voluntary_turnover_pct", "lost_time_injury_rate",
        ],
    },
    "source_systems": {
        "required": ["system_id", "system_name"],
        "optional": ["purpose", "owner"],
    },
    "climate_financial_effects": {
        "required": ["bank_id", "reporting_year"],
        "optional": [
            "effect_id", "effect_type", "driver_type", "linked_id",
            "affected_statement", "line_item", "effect_timing", "time_horizon",
            "horizon", "amount_meur", "quantitative_effect_meur",
            "qualitative_description", "material_adjustment_next_period_flag",
            "basis", "is_synthetic",
        ],
    },
    "climate_opportunities": {
        "required": ["opportunity_id", "bank_id", "reporting_year"],
        "optional": [
            "opportunity_name", "opportunity_category", "opportunity_type",
            "category", "description", "financial_impact_meur",
            "estimated_revenue_impact_meur", "time_horizon", "confidence_level",
            "ifrs_s2_para_evidence", "data_source", "linked_risk_category",
        ],
    },
    "ghg_methodology": {
        "required": ["bank_id", "scope"],
        "optional": [
            "method_id", "reporting_year", "methodology", "measurement_approach",
            "emission_factor_source", "calculation_method", "key_inputs",
            "key_assumptions", "reason_for_approach", "changes_in_period",
            "consolidation_basis", "gwp_basis", "standard_reference", "is_synthetic",
        ],
    },
    "internal_carbon_price": {
        "required": ["bank_id", "reporting_year"],
        "optional": [
            "icp_id", "price_eur_per_tco2e", "carbon_price_eur_per_tco2e",
            "price_type", "scope", "application_scope",
            "applies_to_lending_decisions", "applies_to_financed_emissions",
            "benchmark_reference", "review_frequency", "currency",
        ],
    },
    "rec_registry": {
        "required": ["bank_id", "reporting_year", "volume_mwh"],
        "optional": [
            "certificate_id", "rec_id", "certificate_type", "registry",
            "issuing_registry", "energy_source", "country_of_generation",
            "issue_date", "expiry_date", "cancellation_date",
            "associated_facility_ids", "price_eur_per_mwh",
        ],
    },
    "resilience_assessment": {
        "required": ["bank_id", "reporting_year"],
        "optional": [
            "resilience_id", "scenario_name", "scenario_type", "assessment_summary",
            "resilience_rating", "capacity_to_adjust", "asset_redeployment_capacity",
            "financial_resource_flexibility", "significant_uncertainties",
            "assessment_horizon", "is_synthetic", "data_source",
        ],
    },
    "scope12_consolidation": {
        "required": ["bank_id", "reporting_year"],
        "optional": [
            "cons_id", "scope", "scope1_total_tco2e", "scope2_location_tco2e",
            "scope2_market_tco2e", "consolidated_group_share_pct",
            "other_investees_share_pct", "consolidation_basis", "note", "is_synthetic",
        ],
    },
    "scope3_categories": {
        "required": ["bank_id", "reporting_year", "emissions_tco2e"],
        "optional": [
            "scope3_id", "scope3_category", "category_number", "category_name",
            "included_flag", "calculation_method", "data_source",
            "pcaf_data_quality_score", "exclusion_reason", "is_synthetic",
        ],
    },
    "transition_plan": {
        "required": ["bank_id", "reporting_year"],
        "optional": [
            "tp_id", "action_id", "action_name", "implementation_status",
            "target_year", "has_transition_plan", "net_zero_target_year",
            "aligned_framework", "key_assumptions", "dependencies", "capex_meur",
            "resourcing_meur", "resourcing_description", "prior_period_progress",
            "is_synthetic", "data_source",
        ],
    },
    "value_chain_map": {
        "required": ["bank_id"],
        "optional": [
            "node_id", "node_name", "node_type", "upstream_downstream",
            "sustainability_theme", "climate_exposure_type", "materiality_flag",
            "climate_risk_description", "financial_exposure_meur", "nace_link",
            "ifrs_s2_para_evidence",
        ],
    },
}

for _table_name, _contract in ADDITIONAL_NOTEBOOK_TABLE_CONTRACT.items():
    existing = NOTEBOOK_TABLE_CONTRACT.setdefault(
        _table_name,
        {"required": [], "optional": []},
    )
    existing["required"] = unique_list(
        existing.get("required", []) + _contract.get("required", [])
    )
    existing["optional"] = unique_list(
        existing.get("optional", []) + _contract.get("optional", [])
    )


ADDITIONAL_TABLE_SPECIFIC_COLUMN_ALIASES: Dict[str, Dict[str, List[str]]] = {
    "carbon_credits": {
        "credits_tco2e": ["tonnes_co2e", "credits", "volume_tco2e"],
        "retired_flag": ["retired", "retirement_flag"],
        "permanence_years": ["permanence", "crediting_period_years"],
    },
    "climate_financial_effects": {
        "effect_type": ["driver_type"],
        "amount_meur": ["quantitative_effect_meur", "financial_effect_meur"],
        "time_horizon": ["horizon", "effect_timing"],
    },
    "climate_opportunities": {
        "opportunity_name": ["description", "opportunity_type"],
        "opportunity_category": ["category", "opportunity_type", "linked_risk_category"],
        "financial_impact_meur": ["estimated_revenue_impact_meur"],
    },
    "collateral": {
        "valuation_amount_meur": ["market_value_meur", "valuation_meur", "collateral_value_meur"],
        "flood_zone_class": ["flood_zone_class", "flood_zone", "flood_class", "flood_hazard_zone"],
        "flood_risk_score": ["flood_risk_score", "flood_score", "flood_hazard_score"],
        "physical_risk_score": ["physical_risk_score", "physical_score", "physical_hazard_score"],
    },
    "ghg_methodology": {
        "methodology": ["measurement_approach"],
        "emission_factor_source": ["standard_reference"],
        "calculation_method": ["key_inputs", "measurement_approach"],
    },
    "internal_carbon_price": {
        "price_eur_per_tco2e": ["carbon_price_eur_per_tco2e"],
        "scope": ["application_scope"],
    },
    "rec_registry": {
        "certificate_id": ["rec_id"],
        "registry": ["issuing_registry"],
    },
    "resilience_assessment": {
        "scenario_name": ["scenario_type"],
        "assessment_summary": ["significant_uncertainties"],
        "resilience_rating": ["capacity_to_adjust"],
    },
    "scope3_categories": {
        "scope3_category": ["category_name", "category_number"],
    },
    "transition_plan": {
        "action_id": ["tp_id"],
        "action_name": ["aligned_framework", "has_transition_plan"],
        "implementation_status": ["has_transition_plan", "prior_period_progress"],
        "target_year": ["net_zero_target_year"],
        "capex_meur": ["resourcing_meur"],
    },
    "travel_records": {
        "travel_mode": ["mode", "transport_mode"],
        "travel_date": ["date", "trip_date", "journey_date"],
        "emissions_kg_co2e": ["emissions_kg", "kg_co2e", "co2e_kg", "travel_emissions_kg"],
        "distance_km": ["km", "distance", "travel_distance"],
    },
    "vehicles": {
        "reporting_year": ["registration_year"],
    },
    "utility_invoices": {
        "reporting_year": ["invoice_year"],
    },
}

for _table_name, _column_aliases in ADDITIONAL_TABLE_SPECIFIC_COLUMN_ALIASES.items():
    existing_aliases = TABLE_SPECIFIC_COLUMN_ALIASES.setdefault(_table_name, {})
    for _canonical_column, _aliases in _column_aliases.items():
        existing_aliases[_canonical_column] = unique_list(
            existing_aliases.get(_canonical_column, []) + _aliases
        )



def get_contract_for_table(table_name: str) -> Dict[str, List[str]]:
    return NOTEBOOK_TABLE_CONTRACT.get(
        table_name,
        {
            "required": [],
            "optional": [],
        },
    )


def get_expected_columns_for_table(table_name: str) -> List[str]:
    contract = get_contract_for_table(table_name)

    return unique_list(
        contract.get("required", [])
        + contract.get("optional", [])
    )


def get_required_columns_for_table(table_name: str) -> List[str]:
    return get_contract_for_table(table_name).get("required", [])


def get_aliases_for_column(table_name: str, canonical_column: str) -> List[str]:
    aliases = []

    aliases.extend(GLOBAL_COLUMN_ALIASES.get(canonical_column, []))
    aliases.extend(
        TABLE_SPECIFIC_COLUMN_ALIASES
        .get(table_name, {})
        .get(canonical_column, [])
    )

    aliases.append(canonical_column)

    return unique_list(aliases)