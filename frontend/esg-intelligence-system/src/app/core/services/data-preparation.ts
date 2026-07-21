import { Injectable, inject } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable, map } from 'rxjs';

export interface DataUploadBatch {
  id: string;
  name: string;
  status: string;
  original_filename?: string;
  uploaded_files_count?: number;
  raw_folder?: string;
  patched_folder?: string;
  payload_folder?: string;
  log_folder?: string;
  error_message?: string;
  created_at?: string;
  updated_at?: string;
}

export interface UploadedFileSummary {
  id?: string;
  original_filename?: string;
  stored_filename?: string;
  size_bytes?: number;
  checksum_sha256?: string;
}

export interface UploadResponse {
  batch_id: string;
  status: string;
  uploaded_files_count?: number;
  files?: UploadedFileSummary[];
}

export interface ExtractionResult {
  batch_id: string;
  job_id?: string;
  status: string;
  extracted_csv_count?: number;
  extracted_folder?: string;
  manifest_path?: string;
  files?: unknown[];
  errors?: unknown[];
}

export interface TableDetectionResult {
  batch_id: string;
  job_id?: string;
  status: string;
  total_detected_files?: number;
  needs_review?: boolean;
  detections?: Array<Record<string, unknown>>;
}

export interface ColumnMappingResult {
  batch_id: string;
  job_id?: string;
  status: string;
  needs_review?: boolean;
  total_mapped_files?: number;
  mappings?: Array<Record<string, unknown>>;
}

export interface CanonicalBuildResult {
  batch_id: string;
  job_id?: string;
  status: string;
  canonical_folder?: string;
  total_canonical_files?: number;
  outputs?: Array<Record<string, unknown>>;
}

export interface DataQualityIssue {
  severity?: string;
  code?: string;
  message?: string;
  table_name?: string;
  is_report_blocking?: boolean;
  is_internal_only?: boolean;
}

export interface CanonicalValidationResult {
  batch_id: string;
  job_id?: string;
  status: string;
  is_valid: boolean;
  total_validated_files?: number;
  issues?: DataQualityIssue[];
  validations?: Array<Record<string, unknown>>;
}

export interface GeneratedPayloadManifest {
  id: number;
  bank?: number;
  bank_code: string;
  bank_name: string;
  source_batch_id?: string | null;
  reporting_year: number;
  version: string;
  storage_backend: string;
  minio_prefix?: string;
  status?: string;
  checksum?: string;
  created_at?: string;
}

export interface PayloadOutput {
  filename?: string;
  size_bytes?: number;
  path?: string;
}

export interface PayloadGenerationResult {
  batch_id: string;
  job_id?: string;
  status: string;
  payload_count: number;
  payloads_folder?: string;
  payload_outputs?: PayloadOutput[];
  manifest_path?: string;
  executed_notebook_path?: string;
  stderr_log?: string;
  payload_manifests: GeneratedPayloadManifest[];
}

@Injectable({
  providedIn: 'root',
})
export class DataPreparation {
  private readonly http = inject(HttpClient);

  private readonly baseUrl =
    'http://127.0.0.1:8000/api/data-preparation/batches';

  listBatches(): Observable<DataUploadBatch[]> {
    return this.http.get<DataUploadBatch[]>(
      `${this.baseUrl}/`
    );
  }

  getPayloadManifests(
    bankCode?: string,
    reportingYear?: number
  ): Observable<GeneratedPayloadManifest[]> {
    const params: Record<string, string> = {};

    if (bankCode) {
      params['bank_code'] = bankCode;
    }

    if (reportingYear) {
      params['reporting_year'] = String(reportingYear);
    }

    return this.http
      .get<
        | GeneratedPayloadManifest[]
        | {
            results:
              GeneratedPayloadManifest[];
          }
      >(
        'http://127.0.0.1:8000/api/payload-manifests/',
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

  getBatch(batchId: string): Observable<DataUploadBatch> {
    return this.http.get<DataUploadBatch>(
      `${this.baseUrl}/${batchId}/`
    );
  }

  createBatch(name: string): Observable<DataUploadBatch> {
    return this.http.post<DataUploadBatch>(
      `${this.baseUrl}/`,
      { name }
    );
  }

  uploadFiles(
    batchId: string,
    files: File[]
  ): Observable<UploadResponse> {
    const formData = new FormData();

    for (const file of files) {
      formData.append('files', file);
    }

    return this.http.post<UploadResponse>(
      `${this.baseUrl}/${batchId}/upload/`,
      formData
    );
  }

  extractFiles(batchId: string): Observable<ExtractionResult> {
    return this.http.post<ExtractionResult>(
      `${this.baseUrl}/${batchId}/extract/`,
      {}
    );
  }

  detectTables(
    batchId: string
  ): Observable<TableDetectionResult> {
    return this.http.post<TableDetectionResult>(
      `${this.baseUrl}/${batchId}/detect-tables/`,
      {}
    );
  }

  runColumnMapping(
    batchId: string
  ): Observable<ColumnMappingResult> {
    return this.http.post<ColumnMappingResult>(
      `${this.baseUrl}/${batchId}/column-mapping/`,
      {}
    );
  }

  buildCanonical(
    batchId: string
  ): Observable<CanonicalBuildResult> {
    return this.http.post<CanonicalBuildResult>(
      `${this.baseUrl}/${batchId}/build-canonical/`,
      {}
    );
  }

  validateCanonical(
    batchId: string
  ): Observable<CanonicalValidationResult> {
    return this.http.post<CanonicalValidationResult>(
      `${this.baseUrl}/${batchId}/validate-canonical/`,
      {}
    );
  }

  runNotebookPipeline(
    batchId: string
  ): Observable<PayloadGenerationResult> {
    return this.http.post<PayloadGenerationResult>(
      `${this.baseUrl}/${batchId}/run-notebook-pipeline/`,
      {}
    );
  }
}