import { Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';

export type GenerationJobStatus =
  | 'queued'
  | 'running'
  | 'completed'
  | 'completed_with_warnings'
  | 'failed'
  | 'cancelled';

export interface StartGenerationRequest {
  bank_code: string;
  reporting_year: number;
  payload_manifest_id: number;
  ifrs_asset_version?: string;
  style_asset_version?: string;
  output_formats: string[];
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
  style_asset_bundle?: number;
  status: GenerationJobStatus;
  current_stage: string;
  progress_percent: number;
  warning_count: number;
  error_message: string;
  config: any;
  final_summary: any;
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
  report_version?: string;
  artifact_type: string;
  bucket: string;
  object_key: string;
  content_type: string;
  size_bytes: number;
  checksum: string;
  created_at: string;
}
@Injectable({
  providedIn: 'root',
})
export class Report {
  private apiUrl = 'http://127.0.0.1:8000/api';

  constructor(private http: HttpClient) {}

  startGenerationJob(payload: StartGenerationRequest): Observable<GenerationJob> {
    return this.http.post<GenerationJob>(
      `${this.apiUrl}/report-generation/jobs/`,
      payload
    );
  }

  getGenerationJob(jobId: string): Observable<GenerationJob> {
    return this.http.get<GenerationJob>(
      `${this.apiUrl}/report-generation/jobs/${jobId}/`
    );
  }

  getWarnings(jobId: string): Observable<GenerationWarning[]> {
    return this.http.get<GenerationWarning[]>(
      `${this.apiUrl}/report-generation/jobs/${jobId}/warnings/`
    );
  }



  getArtifacts(jobId: string): Observable<ReportArtifact[]> {
  return this.http.get<ReportArtifact[]>(
    `${this.apiUrl}/report-generation/jobs/${jobId}/artifacts/`
  );
}

downloadArtifact(artifactId: string): Observable<Blob> {
  return this.http.get(
    `${this.apiUrl}/artifacts/${artifactId}/download/`,
    {
      responseType: 'blob',
    }
  );
}
}