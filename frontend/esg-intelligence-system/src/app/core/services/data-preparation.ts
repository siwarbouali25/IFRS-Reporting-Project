import { Injectable, inject } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';

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

export interface UploadResponse {
  batch_id: string;
  status: string;
  uploaded_files_count?: number;
  files?: any[];
}

export interface TableDetectionResult {
  batch_id: string;
  job_id?: string;
  status: string;
  total_detected_files?: number;
  needs_review?: boolean;
  detections?: any[];
}

export interface ColumnMappingResult {
  batch_id: string;
  job_id?: string;
  status: string;
  needs_review?: boolean;
  total_mapped_files?: number;
  mappings?: any[];
}

export interface CanonicalBuildResult {
  batch_id: string;
  job_id?: string;
  status: string;
  canonical_folder?: string;
  total_canonical_files?: number;
  outputs?: any[];
}

export interface CanonicalValidationResult {
  batch_id: string;
  job_id?: string;
  status: string;
  is_valid: boolean;
  total_validated_files?: number;
  issues?: any[];
  validations?: any[];
}

export interface PayloadGenerationResult {
  batch_id: string;
  job_id?: string;
  status: string;
  payload_count: number;
  payloads_folder?: string;
  payload_outputs?: any[];
  manifest_path?: string;
  executed_notebook_path?: string;
  stderr_log?: string;
}

@Injectable({
  providedIn: 'root',
})
export class DataPreparation {
  private readonly http = inject(HttpClient);

  private readonly baseUrl = 'http://127.0.0.1:8000/api/data-preparation/batches';;

  listBatches(): Observable<DataUploadBatch[]> {
    return this.http.get<DataUploadBatch[]>(`${this.baseUrl}/`);
  }

  getBatch(batchId: string): Observable<DataUploadBatch> {
    return this.http.get<DataUploadBatch>(`${this.baseUrl}/${batchId}/`);
  }

  createBatch(name: string): Observable<DataUploadBatch> {
    return this.http.post<DataUploadBatch>(`${this.baseUrl}/`, { name });
  }

  uploadFiles(batchId: string, files: File[]): Observable<UploadResponse> {
    const formData = new FormData();

    for (const file of files) {
      formData.append('files', file);
    }

    return this.http.post<UploadResponse>(
      `${this.baseUrl}/${batchId}/upload/`,
      formData
    );
  }

  extractFiles(batchId: string): Observable<any> {
    return this.http.post<any>(`${this.baseUrl}/${batchId}/extract/`, {});
  }

  detectTables(batchId: string): Observable<TableDetectionResult> {
    return this.http.post<TableDetectionResult>(
      `${this.baseUrl}/${batchId}/detect-tables/`,
      {}
    );
  }

  runColumnMapping(batchId: string): Observable<ColumnMappingResult> {
    return this.http.post<ColumnMappingResult>(
      `${this.baseUrl}/${batchId}/column-mapping/`,
      {}
    );
  }

  buildCanonical(batchId: string): Observable<CanonicalBuildResult> {
    return this.http.post<CanonicalBuildResult>(
      `${this.baseUrl}/${batchId}/build-canonical/`,
      {}
    );
  }

  validateCanonical(batchId: string): Observable<CanonicalValidationResult> {
    return this.http.post<CanonicalValidationResult>(
      `${this.baseUrl}/${batchId}/validate-canonical/`,
      {}
    );
  }

  runNotebookPipeline(batchId: string): Observable<PayloadGenerationResult> {
    return this.http.post<PayloadGenerationResult>(
      `${this.baseUrl}/${batchId}/run-notebook-pipeline/`,
      {}
    );
  }
}