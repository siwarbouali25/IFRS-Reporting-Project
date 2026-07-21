import {
  Injectable,
} from '@angular/core';
import {
  HttpClient,
  HttpParams,
} from '@angular/common/http';
import {
  Observable,
  map,
} from 'rxjs';

export type RiskAnalysisStatus =
  | 'pending'
  | 'ready'
  | 'failed';

export interface PayloadManifestSummary {
  id: number;
  bank: number;
  bank_code: string;
  bank_name: string;
  source_batch_id?: string | null;
  reporting_year: number;
  version: string;
  storage_backend: string;
  minio_prefix: string;
  status: string;
  checksum: string;
  created_at: string;
}

export interface Kpi {
  title: string;
  value: number | string;
  suffix?: string;
  change: string;
  cls:
    | 'positive'
    | 'negative'
    | 'neutral';
}

export interface ValidationWarning {
  level:
    | 'error'
    | 'warning'
    | 'info';
  code?: string;
  message: string;
  details?: Record<string, unknown>;
}

export interface EvidenceItem {
  id: string;
  key: string;
  label: string;
  value: string;
  source: string;
  ifrs: string;
  detail: string;
}

export interface RiskMatrixItem {
  x: number;
  y: number;
  z: number;
  name: string;
  rating: string;
  id: string;
  horizon: string;
  category: string;
  ifrs: string;
}

export interface DataQualityRegisterItem {
  domain: string;
  label: string;
  assurance_level: string;
  assurance_provider: string | null;
  assurance_standard: string | null;
  is_synthetic: false;
  confidence: string;
  confidence_basis: string;
  note: string;
}

export interface CounterpartyExposure {
  counterparty_id: string;
  country: string | null;
  exposure_meur: number;
  financial_impact_meur: number;
  hazard_types: string[];
  high_risk_count: number;
  n_exposures: number;
}

export interface ProcessedBundle {
  bank: {
    bank_id?: string;
    bank_name?: string;
    country?: string;
    reporting_currency?: string;
    regulatory_regime?: string;
    [key: string]: unknown;
  };
  metadata: {
    reporting_year?: number;
    data_gaps?: Array<Record<string, unknown>>;
    [key: string]: unknown;
  };
  general_requirements_context: {
    regulatory_regime?: string;
    standards_basis?: string;
    reporting_currency?: string;
    [key: string]: unknown;
  };
  reporting_kpis: Record<string, unknown>;
  kpis: Kpi[];
  intensity_trend: Array<{
    year: string;
    actual: number | null;
    target: number | null;
  }>;
  financed_composition: Array<{
    name: string;
    value: number;
    proxy: boolean;
  }>;
  risk_matrix: RiskMatrixItem[];
  risk_by_category: Array<
    Record<string, string | number>
  >;
  physical_by_hazard: Array<{
    hazard: string;
    exposure: number;
    count: number;
    high: number;
  }>;
  physical_by_country: Array<{
    country: string;
    exposure: number;
    financial_impact: number;
    high_risk_count: number;
  }>;
  scenarios: Array<
    Record<string, string | number | null>
  >;
  data_quality_register:
    DataQualityRegisterItem[];
  data_quality_summary: {
    audited_report_pct?: number | null;
    cdp_disclosure_pct?: number | null;
    estimated_economic_pct?: number | null;
    proxy_model_pct?: number | null;
    interpretation?: string;
  };
  counterparty_drilldown: {
    physical_risk_top_by_exposure:
      CounterpartyExposure[];
    physical_risk_basis: string;
    excluded_physical_rows: number;
    unlinked_equity_rows: number;
  };
  evidence: EvidenceItem[];
}

export interface RiskAnalysis {
  id: string;
  payload_manifest_id?: number | null;
  payload_manifest_version?: string | null;
  bank_id: string;
  bank_name: string;
  reporting_year: number | null;
  status: RiskAnalysisStatus;
  processed: ProcessedBundle | null;
  validation_warnings:
    ValidationWarning[];
  error_message: string;
  created_by?: string | number | null;
  created_by_name?: string;
  created_at: string;
  updated_at: string;
}

export interface RiskAnalysisSummary {
  id: string;
  payload_manifest_id?: number | null;
  payload_manifest_version?: string | null;
  bank_id: string;
  bank_name: string;
  reporting_year: number | null;
  status: RiskAnalysisStatus;
  created_by_name?: string;
  created_at: string;
}

export interface AssessmentResult {
  id: string;
  assessment_text: string;
  recommendations: Array<{
    title: string;
    detail: string;
  }>;
  avoid: Array<{
    title: string;
    detail: string;
  }>;
  evidence: EvidenceItem[];
  model_used: string;
  is_fallback: boolean;
  created_at: string;
}

type ListResponse<T> =
  | T[]
  | {
      results: T[];
    };

@Injectable({
  providedIn: 'root',
})
export class Risk {
  private readonly apiUrl =
    'http://127.0.0.1:8000/api';

  constructor(
    private http: HttpClient
  ) {}

  getPayloadManifests():
    Observable<PayloadManifestSummary[]> {
    return this.http
      .get<
        ListResponse<PayloadManifestSummary>
      >(
        `${this.apiUrl}/payload-manifests/`
      )
      .pipe(
        map((response) =>
          Array.isArray(response)
            ? response
            : response.results
        )
      );
  }

  startAnalysis(
    payloadManifestId: number,
    force = false
  ): Observable<RiskAnalysis> {
    return this.http.post<RiskAnalysis>(
      `${this.apiUrl}/risk/upload/`,
      {
        payload_manifest_id:
          payloadManifestId,
        force,
      }
    );
  }

  list(
    payloadManifestId?: number
  ): Observable<RiskAnalysisSummary[]> {
    let params = new HttpParams();

    if (payloadManifestId) {
      params = params.set(
        'payload_manifest_id',
        String(payloadManifestId)
      );
    }

    return this.http
      .get<
        ListResponse<RiskAnalysisSummary>
      >(
        `${this.apiUrl}/risk/analyses/`,
        {
          params,
        }
      )
      .pipe(
        map((response) =>
          Array.isArray(response)
            ? response
            : response.results
        )
      );
  }

  get(
    id: string
  ): Observable<RiskAnalysis> {
    return this.http.get<RiskAnalysis>(
      `${this.apiUrl}/risk/analyses/${id}/`
    );
  }

  generateAssessment(
    id: string
  ): Observable<AssessmentResult> {
    return this.http.post<AssessmentResult>(
      `${this.apiUrl}/risk/analyses/${id}/assessment/`,
      {}
    );
  }

  getLatestAssessment(
    id: string
  ): Observable<AssessmentResult> {
    return this.http.get<AssessmentResult>(
      `${this.apiUrl}/risk/analyses/${id}/assessment/latest/`
    );
  }
}
