import csv
import json
import re
from pathlib import Path
from typing import Dict, List, Optional

from data_preparation.models import DataUploadBatch
from data_preparation.services.upload_extractor import (
    get_extracted_folder,
    get_mapping_folder,
)


def normalize_name(value: str) -> str:
    value = value.strip().lower()
    value = re.sub(r"[^a-z0-9]+", "_", value)
    value = re.sub(r"_+", "_", value)
    return value.strip("_")


TABLE_SIGNATURES: Dict[str, Dict] = {
    "banks": {
        "filename_hints": ["banks", "bank", "entity", "company", "institution"],
        "columns": {
            "bank_id": ["bank_id", "entity_id", "company_id", "institution_id"],
            "bank_name": ["bank_name", "entity_name", "company_name", "institution_name", "name"],
            "total_assets_meur": ["total_assets_meur", "total_assets", "assets", "assets_meur"],
            "reporting_currency": ["reporting_currency", "currency"],
            "fiscal_year_end": ["fiscal_year_end", "year_end", "reporting_period_end"],
        },
    },
    "financial_summary": {
        "filename_hints": ["financial_summary", "financials", "finance", "income", "balance"],
        "columns": {
            "bank_id": ["bank_id", "entity_id"],
            "reporting_year": ["reporting_year", "year", "fiscal_year"],
            "total_assets_meur": ["total_assets_meur", "total_assets", "assets"],
            "total_loans_meur": ["total_loans_meur", "total_loans", "loans"],
            "green_loans_meur": ["green_loans_meur", "green_loans"],
            "total_revenue_meur": ["total_revenue_meur", "revenue", "total_revenue"],
            "net_profit_meur": ["net_profit_meur", "net_profit", "profit"],
        },
    },
    "governance": {
        "filename_hints": ["governance", "board", "committee", "assurance"],
        "columns": {
            "bank_id": ["bank_id", "entity_id"],
            "reporting_year": ["reporting_year", "year"],
            "board_size": ["board_size", "directors_count", "number_of_directors"],
            "esg_committee_exists": ["esg_committee_exists", "sustainability_committee_exists"],
            "board_climate_expertise_pct": ["board_climate_expertise_pct", "climate_expertise_pct"],
            "external_assurance": ["external_assurance", "assurance_level"],
            "erm_integration_flag": ["erm_integration_flag", "erm_integration", "risk_integration"],
        },
    },
    "board_minutes_extract": {
        "filename_hints": ["board_minutes", "minutes", "meeting", "committee_minutes"],
        "columns": {
            "meeting_id": ["meeting_id", "minute_id"],
            "committee_name": ["committee_name", "committee"],
            "meeting_date": ["meeting_date", "date"],
            "climate_agenda_flag": ["climate_agenda_flag", "climate_on_agenda"],
            "climate_topics_discussed": ["climate_topics_discussed", "topics_discussed"],
            "decision_summary": ["decision_summary", "decision", "summary"],
        },
    },
    "climate_scenarios": {
        "filename_hints": ["climate_scenarios", "scenario", "ngfs", "stress_test"],
        "columns": {
            "scenario_id": ["scenario_id"],
            "scenario_name": ["scenario_name", "scenario"],
            "scenario_type": ["scenario_type", "type"],
            "framework": ["framework"],
            "temperature_outcome_c": ["temperature_outcome_c", "temperature"],
            "horizon": ["horizon", "time_horizon"],
            "carbon_price_assumption_eur_per_tco2e": ["carbon_price_assumption_eur_per_tco2e", "carbon_price"],
        },
    },
    "climate_risk_register": {
        "filename_hints": ["climate_risk_register", "risk_register", "risks"],
        "columns": {
            "risk_id": ["risk_id"],
            "risk_name": ["risk_name", "risk"],
            "risk_category": ["risk_category", "category"],
            "risk_description": ["risk_description", "description"],
            "likelihood_score": ["likelihood_score", "likelihood"],
            "severity_score": ["severity_score", "severity"],
            "risk_rating": ["risk_rating", "rating"],
            "mitigation_actions": ["mitigation_actions", "mitigation"],
        },
    },
    "physical_risk_exposures": {
        "filename_hints": ["physical_risk", "hazard", "hazards", "physical_exposure"],
        "columns": {
            "physical_risk_id": ["physical_risk_id", "hazard_id"],
            "counterparty_id": ["counterparty_id", "client_id"],
            "hazard_type": ["hazard_type", "hazard"],
            "acute_risk_score": ["acute_risk_score", "acute_score"],
            "chronic_risk_score": ["chronic_risk_score", "chronic_score"],
            "exposure_amount_meur": ["exposure_amount_meur", "exposure_amount", "exposure"],
        },
    },
    "carbon_credits": {
        "filename_hints": ["carbon_credits", "credits", "offsets"],
        "columns": {
            "credit_id": ["credit_id"],
            "bank_id": ["bank_id"],
            "reporting_year": ["reporting_year", "year"],
            "credits_tco2e": ["credits_tco2e", "credits", "volume_tco2e"],
            "use": ["use", "credit_use"],
            "retired_flag": ["retired_flag", "retired"],
            "permanence_years": ["permanence_years", "permanence"],
        },
    },
    "internal_carbon_price": {
        "filename_hints": ["internal_carbon_price", "carbon_price", "shadow_price"],
        "columns": {
            "bank_id": ["bank_id"],
            "reporting_year": ["reporting_year", "year"],
            "price_eur_per_tco2e": ["price_eur_per_tco2e", "carbon_price", "price"],
            "scope": ["scope"],
        },
    },
    "value_chain_map": {
        "filename_hints": ["value_chain", "supply_chain"],
        "columns": {
            "bank_id": ["bank_id"],
            "activity": ["activity", "value_chain_activity"],
            "value_chain_stage": ["value_chain_stage", "stage"],
            "description": ["description"],
            "climate_risk_exposure": ["climate_risk_exposure", "risk_exposure"],
        },
    },
    "climate_opportunities": {
        "filename_hints": ["climate_opportunities", "opportunities", "green_opportunities"],
        "columns": {
            "opportunity_id": ["opportunity_id"],
            "opportunity_name": ["opportunity_name", "opportunity"],
            "opportunity_category": ["opportunity_category", "category"],
            "financial_impact_meur": ["financial_impact_meur", "financial_impact"],
            "time_horizon": ["time_horizon", "horizon"],
        },
    },
    "scope3_categories": {
        "filename_hints": ["scope3", "scope_3", "category_3"],
        "columns": {
            "bank_id": ["bank_id"],
            "reporting_year": ["reporting_year", "year"],
            "scope3_category": ["scope3_category", "category"],
            "emissions_tco2e": ["emissions_tco2e", "emissions"],
        },
    },
    "transition_plan": {
        "filename_hints": ["transition_plan", "transition"],
        "columns": {
            "bank_id": ["bank_id"],
            "action_id": ["action_id"],
            "action_name": ["action_name", "action"],
            "implementation_status": ["implementation_status", "status"],
            "target_year": ["target_year"],
            "capex_meur": ["capex_meur", "capex"],
        },
    },
    "climate_financial_effects": {
        "filename_hints": ["financial_effects", "climate_financial", "financial_impact"],
        "columns": {
            "bank_id": ["bank_id"],
            "reporting_year": ["reporting_year", "year"],
            "effect_type": ["effect_type"],
            "amount_meur": ["amount_meur", "amount"],
            "time_horizon": ["time_horizon", "horizon"],
        },
    },
    "resilience_assessment": {
        "filename_hints": ["resilience", "resilience_assessment"],
        "columns": {
            "bank_id": ["bank_id"],
            "scenario_name": ["scenario_name", "scenario"],
            "assessment_summary": ["assessment_summary", "summary"],
            "resilience_rating": ["resilience_rating", "rating"],
        },
    },
    "ghg_methodology": {
        "filename_hints": ["ghg_methodology", "methodology", "emissions_methodology"],
        "columns": {
            "bank_id": ["bank_id"],
            "scope": ["scope"],
            "methodology": ["methodology"],
            "emission_factor_source": ["emission_factor_source", "factor_source"],
            "calculation_method": ["calculation_method"],
        },
    },
    "scope12_consolidation": {
        "filename_hints": ["scope12", "scope_1_2", "consolidation"],
        "columns": {
            "bank_id": ["bank_id"],
            "reporting_year": ["reporting_year", "year"],
            "scope1_total_tco2e": ["scope1_total_tco2e", "scope1"],
            "scope2_location_tco2e": ["scope2_location_tco2e", "scope2_location"],
            "scope2_market_tco2e": ["scope2_market_tco2e", "scope2_market"],
        },
    },
    "utility_invoices": {
        "filename_hints": ["utility", "utilities", "electricity", "energy_invoice"],
        "columns": {
            "bank_id": ["bank_id"],
            "reporting_year": ["reporting_year", "year"],
            "electricity_kwh": ["electricity_kwh", "electricity"],
            "scope2_location_tco2e": ["scope2_location_tco2e"],
            "scope2_market_tco2e": ["scope2_market_tco2e"],
        },
    },
    "fleet_vehicles": {
        "filename_hints": ["fleet", "vehicles", "cars"],
        "columns": {
            "vehicle_id": ["vehicle_id"],
            "bank_id": ["bank_id"],
            "reporting_year": ["reporting_year", "year"],
            "fuel_type": ["fuel_type", "fuel"],
            "annual_fuel_consumption_l": ["annual_fuel_consumption_l", "fuel_consumption_l"],
            "scope1_tco2e_2024": ["scope1_tco2e_2024", "scope1_fleet_tco2e"],
        },
    },
    "business_travel": {
        "filename_hints": ["business_travel", "travel", "flights"],
        "columns": {
            "travel_id": ["travel_id"],
            "bank_id": ["bank_id"],
            "reporting_year": ["reporting_year", "year"],
            "travel_mode": ["travel_mode", "mode"],
            "distance_km": ["distance_km", "distance"],
            "emissions_tco2e": ["emissions_tco2e", "emissions"],
        },
    },
    "targets": {
        "filename_hints": ["targets", "climate_targets", "net_zero_targets"],
        "columns": {
            "target_id": ["target_id"],
            "bank_id": ["bank_id"],
            "target_type": ["target_type", "type"],
            "scope": ["scope", "scope_coverage"],
            "baseline_year": ["baseline_year"],
            "target_year": ["target_year"],
            "target_framework": ["target_framework", "framework"],
            "status": ["status"],
        },
    },
    "investments": {
        "filename_hints": ["investments", "investment", "portfolio_investments", "securities"],
        "columns": {
            "investment_id": ["investment_id"],
            "bank_id": ["bank_id"],
            "asset_class": ["asset_class"],
            "issuer_name": ["issuer_name", "issuer"],
            "nominal_amount_meur": ["nominal_amount_meur", "nominal_amount"],
            "market_value_meur": ["market_value_meur", "market_value"],
            "issuer_evic_meur": ["issuer_evic_meur", "evic"],
        },
    },
    "source_systems": {
        "filename_hints": ["source_systems", "systems"],
        "columns": {
            "system_id": ["system_id"],
            "system_name": ["system_name", "name"],
            "purpose": ["purpose"],
            "owner": ["owner"],
        },
    },
    "employees": {
        "filename_hints": ["employees", "hr", "workforce"],
        "columns": {
            "bank_id": ["bank_id"],
            "reporting_year": ["reporting_year", "year"],
            "total_headcount": ["total_headcount", "headcount"],
            "female_pct": ["female_pct"],
            "avg_training_hours_per_employee": ["avg_training_hours_per_employee", "training_hours"],
        },
    },
    "facilities": {
        "filename_hints": ["facilities", "buildings", "sites", "branches"],
        "columns": {
            "facility_id": ["facility_id"],
            "bank_id": ["bank_id"],
            "facility_type": ["facility_type", "type"],
            "country": ["country"],
            "city": ["city"],
            "floor_area_sqm": ["floor_area_sqm", "floor_area"],
            "epc_rating": ["epc_rating"],
        },
    },
    "exposures": {
        "filename_hints": ["exposures", "loans", "credit_exposures"],
        "columns": {
            "exposure_id": ["exposure_id", "loan_id"],
            "bank_id": ["bank_id"],
            "counterparty_id": ["counterparty_id", "client_id"],
            "product_type": ["product_type"],
            "outstanding_amount_meur": ["outstanding_amount_meur", "outstanding_amount"],
            "committed_amount_meur": ["committed_amount_meur", "committed_amount"],
            "pcaf_asset_class": ["pcaf_asset_class", "asset_class"],
        },
    },
    "counterparties": {
        "filename_hints": ["counterparties", "clients", "customers", "borrowers"],
        "columns": {
            "counterparty_id": ["counterparty_id", "client_id", "customer_id"],
            "bank_id": ["bank_id"],
            "legal_name": ["legal_name", "client_name", "customer_name", "company_name"],
            "nace_code": ["nace_code", "industry_code"],
            "country": ["country"],
            "annual_revenue_meur": ["annual_revenue_meur", "revenue"],
            "evic_meur": ["evic_meur", "evic"],
        },
    },
    "portfolio_composition": {
        "filename_hints": ["portfolio_composition", "portfolio", "asset_mix"],
        "columns": {
            "bank_id": ["bank_id"],
            "reporting_year": ["reporting_year", "year"],
            "asset_class": ["asset_class"],
            "sector": ["sector"],
            "exposure_amount_meur": ["exposure_amount_meur", "exposure_amount"],
        },
    },
    "collateral": {
        "filename_hints": ["collateral", "security", "property_collateral"],
        "columns": {
            "collateral_id": ["collateral_id"],
            "exposure_id": ["exposure_id", "loan_id"],
            "collateral_type": ["collateral_type", "type"],
            "country": ["country"],
            "valuation_amount_meur": ["valuation_amount_meur", "valuation"],
            "epc_rating": ["epc_rating"],
            "flood_risk_score": ["flood_risk_score"],
        },
    },
    "rec_registry": {
        "filename_hints": ["rec_registry", "renewable_certificate", "certificates", "rec"],
        "columns": {
            "certificate_id": ["certificate_id", "rec_id"],
            "bank_id": ["bank_id"],
            "reporting_year": ["reporting_year", "year"],
            "volume_mwh": ["volume_mwh", "mwh"],
            "certificate_type": ["certificate_type", "type"],
            "registry": ["registry"],
        },
    },
}


def read_csv_headers(csv_path: Path) -> List[str]:
    encodings = ["utf-8-sig", "utf-8", "latin-1"]

    for encoding in encodings:
        try:
            with open(csv_path, "r", encoding=encoding, newline="") as f:
                reader = csv.reader(f)
                return next(reader, [])
        except UnicodeDecodeError:
            continue
        except StopIteration:
            return []

    return []


def score_table_match(csv_path: Path, headers: List[str], table_name: str, signature: Dict) -> Dict:
    normalized_headers = {normalize_name(h) for h in headers if h}
    normalized_filename = normalize_name(csv_path.stem)

    filename_score = 0
    for hint in signature["filename_hints"]:
        if normalize_name(hint) in normalized_filename:
            filename_score += 2

    matched_columns = []
    missing_columns = []

    for canonical_column, aliases in signature["columns"].items():
        normalized_aliases = {normalize_name(alias) for alias in aliases}
        if canonical_column in normalized_headers or normalized_headers.intersection(normalized_aliases):
            matched_columns.append(canonical_column)
        else:
            missing_columns.append(canonical_column)

    column_score = len(matched_columns) * 3
    total_possible = len(signature["columns"]) * 3 + max(len(signature["filename_hints"]) * 2, 1)
    score = filename_score + column_score
    confidence = round(min(score / total_possible, 1.0), 4)

    return {
        "table_name": table_name,
        "score": score,
        "confidence": confidence,
        "filename_score": filename_score,
        "column_score": column_score,
        "matched_columns": matched_columns,
        "missing_signature_columns": missing_columns,
    }


def detect_table_for_file(csv_path: Path) -> Dict:
    headers = read_csv_headers(csv_path)

    candidates = []
    for table_name, signature in TABLE_SIGNATURES.items():
        candidates.append(score_table_match(csv_path, headers, table_name, signature))

    candidates = sorted(candidates, key=lambda x: x["score"], reverse=True)
    best = candidates[0] if candidates else None
    second = candidates[1] if len(candidates) > 1 else None

    needs_review = True
    detected_table: Optional[str] = None

    if best:
        detected_table = best["table_name"]

        # Good enough when confidence is reasonable and the gap to second place is clear.
        if best["confidence"] >= 0.35 and (not second or best["score"] >= second["score"] + 3):
            needs_review = False

    return {
        "source_filename": csv_path.name,
        "source_path": str(csv_path),
        "headers": headers,
        "normalized_headers": [normalize_name(h) for h in headers if h],
        "detected_table": detected_table,
        "confidence": best["confidence"] if best else 0,
        "needs_review": needs_review,
        "top_candidates": candidates[:5],
    }


def detect_tables_for_batch(batch: DataUploadBatch) -> Dict:
    extracted_folder = get_extracted_folder(batch)
    mapping_folder = get_mapping_folder(batch)
    mapping_folder.mkdir(parents=True, exist_ok=True)

    csv_files = sorted(extracted_folder.glob("*.csv"))

    detections = [detect_table_for_file(path) for path in csv_files]

    detected_tables = {}
    duplicates = {}

    for item in detections:
        table_name = item["detected_table"]

        if not table_name:
            continue

        detected_tables.setdefault(table_name, []).append(item["source_filename"])

    for table_name, filenames in detected_tables.items():
        if len(filenames) > 1:
            duplicates[table_name] = filenames
            for item in detections:
                if item["detected_table"] == table_name:
                    item["needs_review"] = True

    result = {
        "batch_id": str(batch.id),
        "extracted_folder": str(extracted_folder),
        "total_csv_files": len(csv_files),
        "detections": detections,
        "detected_tables": detected_tables,
        "duplicates": duplicates,
        "needs_review": any(item["needs_review"] for item in detections),
    }

    output_path = mapping_folder / "detected_tables.json"
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)

    result["output_path"] = str(output_path)
    return result