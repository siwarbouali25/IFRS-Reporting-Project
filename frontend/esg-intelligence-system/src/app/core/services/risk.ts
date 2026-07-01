import { Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';

/* ---------------------------------------------------------------------------
 * Types mirror the backend's processed bundle (risk_analysis/services.py ->
 * process_payload). Kept loose (optional fields) on purpose: the backend
 * omits a series entirely when the source section is missing, so every
 * consumer (the component) must treat each field as possibly absent rather
 * than assuming a fixed shape.
 * ------------------------------------------------------------------------- */
export interface Kpi {
  title: string;
  value: number | string;
  suffix?: string;
  change: string;
  cls: 'up' | 'down' | 'flat';
}

export interface ValidationWarning {
  level: 'error' | 'warning' | 'info';
  message: string;
}

export interface EvidenceItem {
  id: string;
  label: string;
  value: string;
  source: string;
  ifrs: string;
  detail: string;
}

export interface ProcessedBundle {
  bank: any;
  metadata: any;
  general_requirements_context: any;
  reporting_kpis: any;
  kpis: Kpi[];
  intensity_trend: Array<{ year: string; actual: number | null; target: number | null }>;
  op_emissions: Array<Record<string, string | number>>;
  financed_composition: Array<{ name: string; value: number; proxy: boolean }>;
  risk_matrix: Array<{ x: number; y: number; z: number; name: string; rating: string; id: string; horizon: string; ifrs: string }>;
  risk_by_category: Array<Record<string, string | number>>;
  physical_by_hazard: Array<{ hazard: string; exposure: number; count: number; high: number }>;
  scenarios: Array<Record<string, string | number>>;
  data_quality_register: Array<{
    domain: string; label: string; assurance_level: string; assurance_provider: string | null;
    assurance_standard: string | null; is_synthetic: boolean; confidence: string; note: string;
  }>;
  data_quality_summary: {
    audited_report_pct?: number; cdp_disclosure_pct?: number;
    estimated_economic_pct?: number; proxy_model_pct?: number; interpretation?: string;
  };
  peer_benchmark: {
    bank_own: any; peers: any[]; sector_average: any; disclaimer: string;
  } | null;
  counterparty_drilldown: {
    physical_risk_top_by_exposure: Array<{
      counterparty_id: string; country: string; exposure_meur: number;
      financial_impact_meur: number; hazard_types: string[]; high_risk_count: number;
    }>;
    physical_risk_basis: string;
    equity_synthetic_counterparty_map: any[];
    equity_has_real_counterparty_id: boolean;
  };
  scenario_sensitivity: Array<{ horizon: string; low: number; mid: number; high: number }>;
  evidence: EvidenceItem[];
}

export interface RiskAnalysis {
  id: string;
  original_filename: string;
  bank_id: string;
  bank_name: string;
  reporting_year: number | null;
  status: 'pending' | 'ready' | 'failed';
  processed: ProcessedBundle | null;
  validation_warnings: ValidationWarning[];
  error_message: string;
  created_at: string;
  updated_at: string;
}

export interface RiskAnalysisSummary {
  id: string;
  original_filename: string;
  bank_id: string;
  bank_name: string;
  reporting_year: number | null;
  status: 'pending' | 'ready' | 'failed';
  created_at: string;
}

export interface AssessmentResult {
  id: string;
  assessment_text: string;
  recommendations: Array<{ title: string; detail: string }>;
  avoid: Array<{ title: string; detail: string }>;
  evidence: EvidenceItem[];
  model_used: string;
  is_fallback: boolean;
  created_at: string;
}

@Injectable({
  providedIn: 'root',
})
export class Risk {
  private apiUrl = 'http://127.0.0.1:8000/api';

  constructor(private http: HttpClient) {}

  /**
   * Uploads the reporting payload JSON. The backend validates, processes
   * (derives every chart series + augmentation) and persists it in one
   * request, returning the full RiskAnalysis row — including `processed` —
   * so the component can render immediately without a second call.
   */
  upload(file: File): Observable<RiskAnalysis> {
    const formData = new FormData();
    formData.append('file', file, file.name);
    return this.http.post<RiskAnalysis>(`${this.apiUrl}/risk/upload/`, formData);
  }

  list(): Observable<RiskAnalysisSummary[]> {
    return this.http.get<RiskAnalysisSummary[]>(`${this.apiUrl}/risk/analyses/`);
  }

  get(id: string): Observable<RiskAnalysis> {
    return this.http.get<RiskAnalysis>(`${this.apiUrl}/risk/analyses/${id}/`);
  }

  /** Triggers a fresh LLM assessment for an already-processed analysis. */
  generateAssessment(id: string): Observable<AssessmentResult> {
    return this.http.post<AssessmentResult>(`${this.apiUrl}/risk/analyses/${id}/assessment/`, {});
  }

  getLatestAssessment(id: string): Observable<AssessmentResult> {
    return this.http.get<AssessmentResult>(`${this.apiUrl}/risk/analyses/${id}/assessment/latest/`);
  }
}
