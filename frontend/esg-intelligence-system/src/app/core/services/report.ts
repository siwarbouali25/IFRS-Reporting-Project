import { Injectable } from '@angular/core';
import {
  HttpClient,
  HttpParams,
} from '@angular/common/http';
import { Observable, map } from 'rxjs';

export type GenerationJobStatus =
  | 'queued'
  | 'running'
  | 'completed'
  | 'completed_with_warnings'
  | 'failed'
  | 'cancelled';

export type ReportVersionStatus =
  | 'draft'
  | 'pending_review'
  | 'changes_requested'
  | 'approved'
  | 'rejected'
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

export interface StartGenerationRequest {
  bank_code: string;
  reporting_year: number;
  payload_manifest_id: number;
  ifrs_asset_version?: string;
  style_asset_version?: string;
  output_formats: Array<'markdown' | 'pdf'>;
  max_revisions: number;
}

export interface GenerationJob {
  job_id: string;
  bank: number;
  bank_code: string;
  bank_name: string;
  reporting_year: number;
  payload_manifest: number;
  payload_manifest_version: string;
  ifrs_asset_bundle?: number;
  ifrs_asset_version?: string;
  style_asset_bundle?: number;
  style_asset_version?: string;
  status: GenerationJobStatus;
  current_stage: string;
  progress_percent: number;
  warning_count: number;
  error_message: string;
  celery_task_id?: string;
  config: any;
  final_summary: any;
  report_version_id?: string | null;
  report_version_status?: ReportVersionStatus | null;
  created_at: string;
  started_at?: string;
  completed_at?: string;
}

export interface GenerationWarning {
  id: string;
  job: string;
  stage: string;
  warning_type: string;
  message: string;
  details: any;
  created_at: string;
}

export interface ReportArtifact {
  id: string;
  job: string;
  job_id: string;
  report_version?: string | null;
  artifact_type: string;
  bucket: string;
  object_key: string;
  content_type: string;
  size_bytes: number;
  checksum: string;
  created_at: string;
}

export interface ReportApprovalAction {
  id: string;
  action:
    | 'submitted'
    | 'approved'
    | 'changes_requested'
    | 'rejected';
  actor?: number | null;
  actor_name?: string;
  actor_email?: string;
  comment: string;
  created_at: string;
}

export interface ReportSection {
  id: string;
  report_version: string;
  section_key: string;
  status:
    | 'generated'
    | 'validation_failed'
    | 'revised'
    | 'approved'
    | 'warning'
    | 'failed';
  score?: number | null;
  revision_count: number;
  created_at: string;
}

export interface ReportValidationSummary {
  total_sections: number;
  ready_sections: number;
  approved_sections: number;
  warning_sections: number;
  failed_sections: number;
  average_score?: number | null;
}

export interface ReportVersion {
  id: string;
  job: string;
  job_id: string;
  bank: number;
  bank_code: string;
  bank_name: string;
  reporting_year: number;
  version_number: number;
  status: ReportVersionStatus;
  created_by?: number | null;
  created_by_name?: string;
  submitted_by?: number | null;
  submitted_by_name?: string;
  submitted_at?: string | null;
  reviewed_by?: number | null;
  reviewed_by_name?: string;
  reviewed_at?: string | null;
  review_comment: string;
  approval_actions: ReportApprovalAction[];
  sections: ReportSection[];
  generation_status: GenerationJobStatus;
  generation_completed_at?: string | null;
  warning_count: number;
  validation_summary: ReportValidationSummary;
  is_creator: boolean;
  can_submit: boolean;
  can_review: boolean;
  is_locked: boolean;
  created_at: string;
}

type ListResponse<T> = T[] | { results: T[] };

@Injectable({
  providedIn: 'root',
})
export class Report {
  private readonly apiUrl =
    'http://127.0.0.1:8000/api';

  constructor(private http: HttpClient) {}

  getPayloadManifests(
    bankCode?: string,
    reportingYear?: number
  ): Observable<PayloadManifestSummary[]> {
    let params = new HttpParams();

    if (bankCode) {
      params = params.set(
        'bank_code',
        bankCode
      );
    }

    if (reportingYear) {
      params = params.set(
        'reporting_year',
        String(reportingYear)
      );
    }

    return this.http
      .get<ListResponse<PayloadManifestSummary>>(
        `${this.apiUrl}/payload-manifests/`,
        { params }
      )
      .pipe(
        map((response) =>
          Array.isArray(response)
            ? response
            : response.results
        )
      );
  }

  startGenerationJob(
    payload: StartGenerationRequest
  ): Observable<GenerationJob> {
    return this.http.post<GenerationJob>(
      `${this.apiUrl}/report-generation/jobs/`,
      payload
    );
  }

  getGenerationJobs():
    Observable<GenerationJob[]> {
    return this.http
      .get<ListResponse<GenerationJob>>(
        `${this.apiUrl}/report-generation/jobs/`
      )
      .pipe(
        map((response) =>
          Array.isArray(response)
            ? response
            : response.results
        )
      );
  }

  getGenerationJob(
    jobId: string
  ): Observable<GenerationJob> {
    return this.http.get<GenerationJob>(
      `${this.apiUrl}/report-generation/jobs/${jobId}/`
    );
  }

  getWarnings(
    jobId: string
  ): Observable<GenerationWarning[]> {
    return this.http.get<GenerationWarning[]>(
      `${this.apiUrl}/report-generation/jobs/${jobId}/warnings/`
    );
  }

  getArtifacts(
    jobId: string,
    includeInternal = false
  ): Observable<ReportArtifact[]> {
    let params = new HttpParams();

    if (includeInternal) {
      params = params.set(
        'include_internal',
        'true'
      );
    }

    return this.http.get<ReportArtifact[]>(
      `${this.apiUrl}/report-generation/jobs/${jobId}/artifacts/`,
      { params }
    );
  }

  downloadArtifact(
    artifactId: string,
    inline = false
  ): Observable<Blob> {
    let params = new HttpParams();

    if (inline) {
      params = params.set(
        'inline',
        'true'
      );
    }

    const options = {
      params,
      responseType: 'blob' as const,
    };

    return this.http.get(
      `${this.apiUrl}/artifacts/${artifactId}/download/`,
      options
    );
  }

  getReportVersion(
    reportVersionId: string
  ): Observable<ReportVersion> {
    return this.http.get<ReportVersion>(
      `${this.apiUrl}/reports/${reportVersionId}/`
    );
  }

  getReportVersions(
    bankCode?: string,
    reportingYear?: number
  ): Observable<ReportVersion[]> {
    let params = new HttpParams();

    if (bankCode) {
      params = params.set('bank_code', bankCode);
    }

    if (reportingYear) {
      params = params.set(
        'reporting_year',
        String(reportingYear)
      );
    }

    return this.http
      .get<ListResponse<ReportVersion>>(
        `${this.apiUrl}/reports/`,
        { params }
      )
      .pipe(
        map((response) =>
          Array.isArray(response)
            ? response
            : response.results
        )
      );
  }

  submitForReview(
    reportVersionId: string,
    comment = ''
  ): Observable<ReportVersion> {
    return this.http.post<ReportVersion>(
      `${this.apiUrl}/reports/${reportVersionId}/submit-for-review/`,
      { comment }
    );
  }

  approveReport(
    reportVersionId: string,
    comment = ''
  ): Observable<ReportVersion> {
    return this.http.post<ReportVersion>(
      `${this.apiUrl}/reports/${reportVersionId}/approve/`,
      { comment }
    );
  }

  requestChanges(
    reportVersionId: string,
    comment: string
  ): Observable<ReportVersion> {
    return this.http.post<ReportVersion>(
      `${this.apiUrl}/reports/${reportVersionId}/request-changes/`,
      { comment }
    );
  }

  rejectReport(
    reportVersionId: string,
    comment: string
  ): Observable<ReportVersion> {
    return this.http.post<ReportVersion>(
      `${this.apiUrl}/reports/${reportVersionId}/reject/`,
      { comment }
    );
  }
}
