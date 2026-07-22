import { Injectable, inject } from '@angular/core';
import { HttpClient, HttpParams } from '@angular/common/http';
import { Observable } from 'rxjs';

export interface KpiItem {
  key: string;
  label: string;
  value: number | string | null;
  unit: string;
  description: string;
  category: string;
}

export interface EsgScore {
  overall: number | null;
  environmental: number | null;
  social: number | null;
  governance: number | null;
  methodology: string;
  weights: {
    environmental: number;
    social: number;
    governance: number;
  };
  environmental_inputs?: {
    financed_emissions_intensity_tco2e_per_meur_loans?: number | null;
    operational_emissions_intensity_tco2e_per_meur_assets?: number | null;
    high_carbon_exposure_pct?: number | null;
    high_physical_risk_exposure_pct?: number | null;
  };
  indicator_scores?: {
    environmental?: Record<string, number | null>;
    social?: Record<string, number | null>;
    governance?: Record<string, number | null>;
  };
}

export interface ChartDataset {
  type?: string;
  label: string;
  data: number[];
  stack?: string;
  unit?: string;
  y_axis_id?: string;
  yAxisID?: string;
}

export interface BasicChartData {
  labels: string[];
  datasets: ChartDataset[];
}

export interface MiniKpi {
  key: string;
  label: string;
  value: number | string | null;
  unit: string;
  delta: string | null;
  delta_type: 'good' | 'bad' | 'neutral';
  note?: string;
}

export interface RiskMatrixCell {
  likelihood: number;
  severity: number;
  count: number;
  impact: number;
  level: 'empty' | 'low' | 'medium' | 'high';
}

export interface GovernanceTile {
  label: string;
  value: number | string | null;
  unit: string;
}

export interface MethodologyNote {
  field: string;
  reason: string;
  years: string;
}

export interface DashboardCharts {
  mini_kpis: MiniKpi[];
  materiality: {
    financed_emissions_pct: number | null;
    operations_emissions_tco2e: number | null;
    financed_emissions_tco2e: number | null;
  };
  operations_trend: BasicChartData;
  financed_emissions_trend: BasicChartData;
  scope3_categories: BasicChartData;
  data_quality: BasicChartData;
  scenario_analysis: BasicChartData;
  physical_risk_by_hazard: BasicChartData;
  country_exposure: BasicChartData;
  opportunities: BasicChartData;
  investment_emissions: BasicChartData;
  portfolio_mix: BasicChartData;
  climate_exposure_ratios: BasicChartData;
  risk_matrix: RiskMatrixCell[];
  governance_tiles: GovernanceTile[];
  methodology_notes: MethodologyNote[];
}

export interface KpiDashboardResponse {
  batch_id: string;
  bank_id: string;
  reporting_year: number;
  bank_name: string;
  validation_passed: boolean;
  payload_exists: boolean;
  esg_score: EsgScore;
  kpis: KpiItem[];
  charts: DashboardCharts;
}

@Injectable({
  providedIn: 'root',
})
export class KpiDashboardService {
  private readonly http = inject(HttpClient);

  private readonly baseUrl = 'http://127.0.0.1:8000/api/kpi-dashboard';

  getDashboard(
    batchId: string,
    bankId: string = 'BANK01',
    reportingYear: number = 2024
  ): Observable<KpiDashboardResponse> {
    const params = new HttpParams()
      .set('bank_id', bankId)
      .set('reporting_year', String(reportingYear));

    return this.http.get<KpiDashboardResponse>(
      `${this.baseUrl}/batches/${batchId}/`,
      { params }
    );
  }
}