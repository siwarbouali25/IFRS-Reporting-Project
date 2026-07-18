import { Component, inject } from '@angular/core';
import { CommonModule } from '@angular/common';
import { RouterLink } from '@angular/router';
import { FormsModule } from '@angular/forms';
import { finalize } from 'rxjs';

import {
  DataPreparation as DataPreparationApi,
  DataUploadBatch,
  UploadResponse,
  TableDetectionResult,
  ColumnMappingResult,
  CanonicalBuildResult,
  CanonicalValidationResult,
  PayloadGenerationResult,
} from '../../core/services/data-preparation';

type StepStatus = 'pending' | 'running' | 'completed' | 'failed';

interface PrepStep {
  key:
    | 'create'
    | 'upload'
    | 'extract'
    | 'detect'
    | 'mapping'
    | 'canonical'
    | 'validation'
    | 'payloads';
  label: string;
  description: string;
  status: StepStatus;
}

@Component({
  selector: 'app-data-preparation',
  imports: [CommonModule, RouterLink, FormsModule],
  templateUrl: './data-preparation.html',
  styleUrl: './data-preparation.css',
})
export class DataPreparation {
  private readonly dataPreparationApi = inject(DataPreparationApi);

  batchName = 'BANK01 Dataset';
  selectedFiles: File[] = [];
  currentBatch: DataUploadBatch | null = null;

  loading = false;
  errorMessage = '';
  successMessage = '';

  uploadResult: UploadResponse | null = null;
  detectionResult: TableDetectionResult | null = null;
  mappingResult: ColumnMappingResult | null = null;
  canonicalResult: CanonicalBuildResult | null = null;
  validationResult: CanonicalValidationResult | null = null;
  payloadResult: PayloadGenerationResult | null = null;

  steps: PrepStep[] = [
    {
      key: 'create',
      label: 'Create Batch',
      description: 'Create a preparation workspace.',
      status: 'pending',
    },
    {
      key: 'upload',
      label: 'Upload Dataset',
      description: 'Upload ZIP or CSV files.',
      status: 'pending',
    },
    {
      key: 'extract',
      label: 'Extract Files',
      description: 'Extract uploaded files.',
      status: 'pending',
    },
    {
      key: 'detect',
      label: 'Detect Tables',
      description: 'Identify source table types.',
      status: 'pending',
    },
    {
      key: 'mapping',
      label: 'Column Mapping',
      description: 'Map client columns to canonical schema.',
      status: 'pending',
    },
    {
      key: 'canonical',
      label: 'Build Canonical',
      description: 'Generate normalized canonical CSV files.',
      status: 'pending',
    },
    {
      key: 'validation',
      label: 'Validate',
      description: 'Check blocking data quality issues.',
      status: 'pending',
    },
    {
      key: 'payloads',
      label: 'Generate Payloads',
      description: 'Run notebook and generate report JSON payloads.',
      status: 'pending',
    },
  ];

  get overview() {
    return [
      {
        label: 'Uploaded Files',
        value: this.uploadResult?.uploaded_files_count ?? this.currentBatch?.uploaded_files_count ?? 0,
        icon: 'pi pi-upload',
      },
      {
        label: 'Mapped Tables',
        value: this.mappingResult?.total_mapped_files ?? 0,
        icon: 'pi pi-sitemap',
      },
      {
        label: 'Canonical Files',
        value: this.canonicalResult?.total_canonical_files ?? 0,
        icon: 'pi pi-database',
      },
      {
        label: 'Payloads',
        value: this.payloadResult?.payload_count ?? 0,
        icon: 'pi pi-file',
      },
    ];
  }

  get canUpload(): boolean {
    return !!this.currentBatch && this.selectedFiles.length > 0 && !this.loading;
  }

  get canRunPipeline(): boolean {
    return !!this.currentBatch && !!this.uploadResult && !this.loading;
  }

  get validationPassed(): boolean {
    return this.validationResult?.is_valid === true;
  }

  get payloadFiles() {
    return this.payloadResult?.payload_outputs ?? [];
  }

  onFilesSelected(event: Event): void {
    const input = event.target as HTMLInputElement;

    if (!input.files) {
      this.selectedFiles = [];
      return;
    }

    this.selectedFiles = Array.from(input.files);
  }

  createBatch(): void {
    this.resetMessages();
    this.clearActivePayloadManifest();
    this.setStepStatus('create', 'running');
    this.loading = true;

    this.dataPreparationApi
      .createBatch(this.batchName)
      .pipe(finalize(() => (this.loading = false)))
      .subscribe({
        next: (batch) => {
          this.currentBatch = batch;
          this.setStepStatus('create', 'completed');
          this.successMessage = 'Batch created successfully.';
        },
        error: (error) => {
          this.setStepStatus('create', 'failed');
          this.errorMessage = this.getErrorMessage(error);
        },
      });
  }

  uploadFiles(): void {
    if (!this.currentBatch) return;

    this.resetMessages();
    this.setStepStatus('upload', 'running');
    this.loading = true;

    this.dataPreparationApi
      .uploadFiles(this.currentBatch.id, this.selectedFiles)
      .pipe(finalize(() => (this.loading = false)))
      .subscribe({
        next: (result) => {
          this.uploadResult = result;
          this.setStepStatus('upload', 'completed');
          this.successMessage = 'Files uploaded successfully.';
        },
        error: (error) => {
          this.setStepStatus('upload', 'failed');
          this.errorMessage = this.getErrorMessage(error);
        },
      });
  }

  runFullPreparation(): void {
    if (!this.currentBatch) return;

    this.resetMessages();
    this.loading = true;

    const batchId = this.currentBatch.id;

    this.setStepStatus('extract', 'running');

    this.dataPreparationApi.extractFiles(batchId).subscribe({
      next: () => {
        this.setStepStatus('extract', 'completed');
        this.runDetectTables(batchId);
      },
      error: (error) => this.failStep('extract', error),
    });
  }

  private runDetectTables(batchId: string): void {
    this.setStepStatus('detect', 'running');

    this.dataPreparationApi.detectTables(batchId).subscribe({
      next: (result) => {
        this.detectionResult = result;
        this.setStepStatus('detect', 'completed');
        this.runColumnMapping(batchId);
      },
      error: (error) => this.failStep('detect', error),
    });
  }

  private runColumnMapping(batchId: string): void {
    this.setStepStatus('mapping', 'running');

    this.dataPreparationApi.runColumnMapping(batchId).subscribe({
      next: (result) => {
        this.mappingResult = result;
        this.setStepStatus('mapping', 'completed');
        this.runBuildCanonical(batchId);
      },
      error: (error) => this.failStep('mapping', error),
    });
  }

  private runBuildCanonical(batchId: string): void {
    this.setStepStatus('canonical', 'running');

    this.dataPreparationApi.buildCanonical(batchId).subscribe({
      next: (result) => {
        this.canonicalResult = result;
        this.setStepStatus('canonical', 'completed');
        this.runValidateCanonical(batchId);
      },
      error: (error) => this.failStep('canonical', error),
    });
  }

  private runValidateCanonical(batchId: string): void {
    this.setStepStatus('validation', 'running');

    this.dataPreparationApi.validateCanonical(batchId).subscribe({
      next: (result) => {
        this.validationResult = result;
        this.setStepStatus('validation', result.is_valid ? 'completed' : 'failed');

        if (result.is_valid) {
          this.successMessage = 'Canonical data validated successfully.';
        } else {
          this.errorMessage = 'Validation failed. Please review blocking issues.';
        }

        this.loading = false;
      },
      error: (error) => this.failStep('validation', error),
    });
  }

  runPayloadGeneration(): void {
    if (!this.currentBatch) return;

    this.resetMessages();
    this.loading = true;
    this.setStepStatus('payloads', 'running');

    this.dataPreparationApi
      .runNotebookPipeline(this.currentBatch.id)
      .pipe(finalize(() => (this.loading = false)))
      .subscribe({
        next: (result) => {
          this.payloadResult = result;
          this.setStepStatus('payloads', 'completed');
          this.storeActivePayloadManifest(result);
          this.successMessage =
            `Payload generation completed. ` +
            `${result.payload_count} payloads generated.`;
        },
        error: (error) => {
          this.setStepStatus('payloads', 'failed');
          this.errorMessage = this.getErrorMessage(error);
        },
      });
  }

  private storeActivePayloadManifest(
    result: PayloadGenerationResult
  ): void {
    const manifests = result.payload_manifests ?? [];

    if (manifests.length === 0) {
      this.clearActivePayloadManifest();
      return;
    }

    const preferredManifest =
      manifests.find(
        (manifest) => manifest.bank_code === 'BANK01'
      ) ?? manifests[0];

    localStorage.setItem(
      'activePayloadManifestId',
      String(preferredManifest.id)
    );
    localStorage.setItem(
      'activeReportBankCode',
      preferredManifest.bank_code
    );
    localStorage.setItem(
      'activeReportingYear',
      String(preferredManifest.reporting_year)
    );
    localStorage.setItem(
      'activePayloadManifestVersion',
      preferredManifest.version
    );
    localStorage.setItem(
      'activeDataPreparationBatchId',
      result.batch_id
    );
  }

  private clearActivePayloadManifest(): void {
    localStorage.removeItem('activePayloadManifestId');
    localStorage.removeItem('activeReportBankCode');
    localStorage.removeItem('activeReportingYear');
    localStorage.removeItem('activePayloadManifestVersion');
    localStorage.removeItem('activeDataPreparationBatchId');
  }

  private failStep(stepKey: PrepStep['key'], error: unknown): void {
    this.setStepStatus(stepKey, 'failed');
    this.errorMessage = this.getErrorMessage(error);
    this.loading = false;
  }

  private setStepStatus(stepKey: PrepStep['key'], status: StepStatus): void {
    this.steps = this.steps.map((step) =>
      step.key === stepKey ? { ...step, status } : step
    );
  }

  private resetMessages(): void {
    this.errorMessage = '';
    this.successMessage = '';
  }

  private getErrorMessage(error: any): string {
    return (
      error?.error?.detail ||
      error?.error?.error ||
      error?.error?.message ||
      error?.message ||
      'An unexpected error occurred.'
    );
  }
}