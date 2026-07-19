import { Component, inject } from '@angular/core';
import { CommonModule } from '@angular/common';
import { RouterLink } from '@angular/router';

import {
  CanonicalBuildResult,
  CanonicalValidationResult,
  ColumnMappingResult,
  DataPreparation as DataPreparationApi,
  DataQualityIssue,
  DataUploadBatch,
  GeneratedPayloadManifest,
  PayloadGenerationResult,
  TableDetectionResult,
  UploadResponse,
} from '../../core/services/data-preparation';

type StepStatus =
  | 'pending'
  | 'running'
  | 'completed'
  | 'failed';

type PreparationStepKey =
  | 'received'
  | 'analysed'
  | 'standardised'
  | 'quality'
  | 'ready';

interface PreparationStep {
  key: PreparationStepKey;
  label: string;
  description: string;
  status: StepStatus;
}

interface DisclosureArea {
  name: string;
  description: string;
  icon: string;
}

@Component({
  selector: 'app-data-preparation',
  imports: [CommonModule, RouterLink],
  templateUrl: './data-preparation.html',
  styleUrl: './data-preparation.css',
})
export class DataPreparation {
  private readonly dataPreparationApi =
    inject(DataPreparationApi);

  selectedFiles: File[] = [];
  currentBatch: DataUploadBatch | null = null;

  loading = false;
  isDragging = false;
  errorMessage = '';
  successMessage = '';
  currentActivity =
    'Select the institution source files to begin.';

  completedAt: Date | null = null;

  uploadResult: UploadResponse | null = null;
  detectionResult: TableDetectionResult | null = null;
  mappingResult: ColumnMappingResult | null = null;
  canonicalResult: CanonicalBuildResult | null = null;
  validationResult:
    CanonicalValidationResult | null = null;
  payloadResult:
    PayloadGenerationResult | null = null;

  activeManifest:
    GeneratedPayloadManifest | null = null;

  steps: PreparationStep[] = [
    {
      key: 'received',
      label: 'Data received',
      description:
        'Source files are uploaded securely.',
      status: 'pending',
    },
    {
      key: 'analysed',
      label: 'Structure analysed',
      description:
        'The system identifies the available information.',
      status: 'pending',
    },
    {
      key: 'standardised',
      label: 'Information standardised',
      description:
        'Source information is prepared in a consistent structure.',
      status: 'pending',
    },
    {
      key: 'quality',
      label: 'Quality checks completed',
      description:
        'Required information and blocking issues are reviewed.',
      status: 'pending',
    },
    {
      key: 'ready',
      label: 'Disclosure package prepared',
      description:
        'Reporting information is ready for the next stage.',
      status: 'pending',
    },
  ];

  readonly disclosureAreas: DisclosureArea[] = [
    {
      name: 'General Requirements',
      description:
        'Reporting basis, boundaries, and general disclosures.',
      icon: 'pi pi-book',
    },
    {
      name: 'Governance',
      description:
        'Oversight, responsibilities, and governance processes.',
      icon: 'pi pi-building',
    },
    {
      name: 'Strategy',
      description:
        'Risks, opportunities, resilience, and business strategy.',
      icon: 'pi pi-compass',
    },
    {
      name: 'Risk Management',
      description:
        'Identification, assessment, and monitoring processes.',
      icon: 'pi pi-shield',
    },
    {
      name: 'Metrics and Targets',
      description:
        'Performance indicators, targets, and progress information.',
      icon: 'pi pi-chart-line',
    },
  ];

  get canStartPreparation(): boolean {
    return (
      this.selectedFiles.length > 0 &&
      !this.loading
    );
  }

  get preparationStarted(): boolean {
    return (
      this.loading ||
      this.currentBatch !== null ||
      this.steps.some(
        (step) =>
          step.status !== 'pending'
      )
    );
  }

  get preparationCompleted(): boolean {
    return (
      this.payloadResult !== null &&
      this.activeManifest !== null &&
      this.getStepStatus('ready') ===
        'completed'
    );
  }

  get selectedFileCount(): number {
    return this.selectedFiles.length;
  }

  get selectedFileSize(): number {
    return this.selectedFiles.reduce(
      (total, file) =>
        total + file.size,
      0
    );
  }

  get selectedFileTypeLabel(): string {
    const csvCount =
      this.selectedFiles.filter(
        (file) =>
          file.name
            .toLowerCase()
            .endsWith('.csv')
      ).length;

    const zipCount =
      this.selectedFiles.filter(
        (file) =>
          file.name
            .toLowerCase()
            .endsWith('.zip')
      ).length;

    const parts: string[] = [];

    if (csvCount > 0) {
      parts.push(
        `${csvCount} CSV ${
          csvCount === 1
            ? 'file'
            : 'files'
        }`
      );
    }

    if (zipCount > 0) {
      parts.push(
        `${zipCount} ZIP ${
          zipCount === 1
            ? 'archive'
            : 'archives'
        }`
      );
    }

    return parts.join(' · ');
  }

  get filesProcessedCount(): number {
    return (
      this.validationResult
        ?.total_validated_files ??
      this.canonicalResult
        ?.total_canonical_files ??
      this.uploadResult
        ?.uploaded_files_count ??
      this.selectedFiles.length
    );
  }

  get qualityIssues(): DataQualityIssue[] {
    return (
      this.validationResult?.issues ??
      []
    );
  }

  get blockingIssueCount(): number {
    return this.qualityIssues.filter(
      (issue) =>
        issue.is_report_blocking ===
          true ||
        issue.severity?.toLowerCase() ===
          'error'
    ).length;
  }

  get reviewNoteCount(): number {
    return this.qualityIssues.filter(
      (issue) =>
        issue.is_report_blocking !==
          true &&
        issue.severity?.toLowerCase() !==
          'error'
    ).length;
  }

  get visibleReviewNotes(): DataQualityIssue[] {
    return this.qualityIssues
      .filter(
        (issue) =>
          issue.is_internal_only !== true
      )
      .slice(0, 4);
  }

  get progressPercent(): number {
    const completedCount =
      this.steps.filter(
        (step) =>
          step.status === 'completed'
      ).length;

    const hasRunning =
      this.steps.some(
        (step) =>
          step.status === 'running'
      );

    const base =
      completedCount * 20;

    return Math.min(
      100,
      base + (hasRunning ? 10 : 0)
    );
  }

  get reportingEntities():
    GeneratedPayloadManifest[] {
    return (
      this.payloadResult
        ?.payload_manifests ?? []
    );
  }

  get entityName(): string {
    return (
      this.activeManifest?.bank_name ??
      'Reporting entity'
    );
  }

  get reportingYear(): number | string {
    return (
      this.activeManifest
        ?.reporting_year ??
      '—'
    );
  }

  get currentStatusLabel(): string {
    if (this.preparationCompleted) {
      return 'Ready';
    }

    if (
      this.steps.some(
        (step) =>
          step.status === 'failed'
      )
    ) {
      return 'Needs attention';
    }

    if (this.loading) {
      return 'In progress';
    }

    if (
      this.selectedFiles.length > 0
    ) {
      return 'Ready to start';
    }

    return 'Waiting for files';
  }

  onFilesSelected(event: Event): void {
    const input =
      event.target as HTMLInputElement;

    if (!input.files) {
      return;
    }

    this.applySelectedFiles(
      Array.from(input.files)
    );

    input.value = '';
  }

  onDragOver(event: DragEvent): void {
    event.preventDefault();
    this.isDragging = true;
  }

  onDragLeave(event: DragEvent): void {
    event.preventDefault();
    this.isDragging = false;
  }

  onDrop(event: DragEvent): void {
    event.preventDefault();
    this.isDragging = false;

    const files =
      Array.from(
        event.dataTransfer?.files ?? []
      );

    this.applySelectedFiles(files);
  }

  startPreparation(): void {
    if (!this.canStartPreparation) {
      return;
    }

    this.resetProcessingState();
    this.clearActivePayloadManifest();

    this.loading = true;
    this.currentActivity =
      'Creating a secure preparation workspace...';

    this.setStepStatus(
      'received',
      'running'
    );

    this.dataPreparationApi
      .createBatch(
        this.buildAutomaticBatchName()
      )
      .subscribe({
        next: (batch) => {
          this.currentBatch = batch;
          this.uploadSelectedFiles(
            batch.id
          );
        },
        error: (error) => {
          this.failPreparation(
            'received',
            error
          );
        },
      });
  }

  startNewPreparation(): void {
    this.selectedFiles = [];
    this.currentBatch = null;
    this.resetProcessingState();
    this.clearActivePayloadManifest();
    this.currentActivity =
      'Select the institution source files to begin.';
  }

  selectManifest(
    manifest: GeneratedPayloadManifest
  ): void {
    this.activeManifest = manifest;
    this.storeActivePayloadManifest(
      manifest
    );
  }

  formatBytes(bytes: number): string {
    if (bytes <= 0) {
      return '0 B';
    }

    if (bytes < 1024) {
      return `${bytes} B`;
    }

    if (
      bytes <
      1024 * 1024
    ) {
      return (
        `${(
          bytes / 1024
        ).toFixed(1)} KB`
      );
    }

    return (
      `${(
        bytes /
        (1024 * 1024)
      ).toFixed(1)} MB`
    );
  }

  getStepIcon(
    status: StepStatus
  ): string {
    if (status === 'completed') {
      return 'pi pi-check';
    }

    if (status === 'running') {
      return (
        'pi pi-spin pi-spinner'
      );
    }

    if (status === 'failed') {
      return 'pi pi-times';
    }

    return 'pi pi-circle';
  }

  getIssueMessage(
    issue: DataQualityIssue
  ): string {
    return (
      issue.message ??
      'An item requires review.'
    );
  }

  private applySelectedFiles(
    files: File[]
  ): void {
    const supported =
      files.filter(
        (file) =>
          this.isSupportedFile(file)
      );

    const unsupportedCount =
      files.length - supported.length;

    if (supported.length === 0) {
      this.errorMessage =
        'Select CSV files or a ZIP archive.';
      return;
    }

    if (this.loading) {
      return;
    }

    this.selectedFiles = supported;
    this.currentBatch = null;
    this.resetProcessingState();
    this.clearActivePayloadManifest();

    this.currentActivity =
      `${supported.length} source ${
        supported.length === 1
          ? 'file is'
          : 'files are'
      } ready for preparation.`;

    if (unsupportedCount > 0) {
      this.errorMessage =
        `${unsupportedCount} unsupported ${
          unsupportedCount === 1
            ? 'file was'
            : 'files were'
        } ignored.`;
    }
  }

  private uploadSelectedFiles(
    batchId: string
  ): void {
    this.currentActivity =
      'Uploading source information...';

    this.dataPreparationApi
      .uploadFiles(
        batchId,
        this.selectedFiles
      )
      .subscribe({
        next: (result) => {
          this.uploadResult = result;
          this.setStepStatus(
            'received',
            'completed'
          );
          this.runExtraction(batchId);
        },
        error: (error) => {
          this.failPreparation(
            'received',
            error
          );
        },
      });
  }

  private runExtraction(
    batchId: string
  ): void {
    this.setStepStatus(
      'analysed',
      'running'
    );
    this.currentActivity =
      'Reviewing the structure of the uploaded information...';

    this.dataPreparationApi
      .extractFiles(batchId)
      .subscribe({
        next: () => {
          this.runDetection(batchId);
        },
        error: (error) => {
          this.failPreparation(
            'analysed',
            error
          );
        },
      });
  }

  private runDetection(
    batchId: string
  ): void {
    this.dataPreparationApi
      .detectTables(batchId)
      .subscribe({
        next: (result) => {
          this.detectionResult =
            result;
          this.setStepStatus(
            'analysed',
            'completed'
          );
          this.runMapping(batchId);
        },
        error: (error) => {
          this.failPreparation(
            'analysed',
            error
          );
        },
      });
  }

  private runMapping(
    batchId: string
  ): void {
    this.setStepStatus(
      'standardised',
      'running'
    );
    this.currentActivity =
      'Standardising the available sustainability information...';

    this.dataPreparationApi
      .runColumnMapping(batchId)
      .subscribe({
        next: (result) => {
          this.mappingResult = result;
          this.runCanonicalBuild(
            batchId
          );
        },
        error: (error) => {
          this.failPreparation(
            'standardised',
            error
          );
        },
      });
  }

  private runCanonicalBuild(
    batchId: string
  ): void {
    this.dataPreparationApi
      .buildCanonical(batchId)
      .subscribe({
        next: (result) => {
          this.canonicalResult =
            result;
          this.setStepStatus(
            'standardised',
            'completed'
          );
          this.runQualityValidation(
            batchId
          );
        },
        error: (error) => {
          this.failPreparation(
            'standardised',
            error
          );
        },
      });
  }

  private runQualityValidation(
    batchId: string
  ): void {
    this.setStepStatus(
      'quality',
      'running'
    );
    this.currentActivity =
      'Checking completeness and data quality...';

    this.dataPreparationApi
      .validateCanonical(batchId)
      .subscribe({
        next: (result) => {
          this.validationResult =
            result;

          if (!result.is_valid) {
            this.setStepStatus(
              'quality',
              'failed'
            );
            this.loading = false;
            this.currentActivity =
              'Some information needs attention before preparation can continue.';
            this.errorMessage =
              'The uploaded information contains blocking quality issues.';
            return;
          }

          this.setStepStatus(
            'quality',
            'completed'
          );
          this.runDisclosurePreparation(
            batchId
          );
        },
        error: (error) => {
          this.failPreparation(
            'quality',
            error
          );
        },
      });
  }

  private runDisclosurePreparation(
    batchId: string
  ): void {
    this.setStepStatus(
      'ready',
      'running'
    );
    this.currentActivity =
      'Preparing the disclosure information for reporting...';

    this.dataPreparationApi
      .runNotebookPipeline(batchId)
      .subscribe({
        next: (result) => {
          this.payloadResult = result;
          this.setStepStatus(
            'ready',
            'completed'
          );
          this.loading = false;
          this.completedAt =
            new Date();

          const manifests =
            result.payload_manifests ??
            [];

          if (manifests.length > 0) {
            this.selectManifest(
              manifests[0]
            );
          }

          this.currentActivity =
            'Preparation completed successfully.';

          this.successMessage =
            this.activeManifest
              ? (
                  `${this.activeManifest.bank_name} is ready for report generation.`
                )
              : (
                  'The disclosure information is ready for report generation.'
                );
        },
        error: (error) => {
          this.failPreparation(
            'ready',
            error
          );
        },
      });
  }

  private failPreparation(
    stepKey: PreparationStepKey,
    error: unknown
  ): void {
    console.error(
      'Data preparation failed:',
      error
    );

    this.setStepStatus(
      stepKey,
      'failed'
    );
    this.loading = false;
    this.currentActivity =
      'Preparation stopped because an item needs attention.';
    this.errorMessage =
      this.getFriendlyErrorMessage(
        error,
        stepKey
      );
  }

  private getFriendlyErrorMessage(
    error: any,
    stepKey: PreparationStepKey
  ): string {
    const rawMessage = String(
      error?.error?.detail ??
      error?.error?.error ??
      error?.error?.message ??
      error?.message ??
      ''
    ).toLowerCase();

    if (
      rawMessage.includes('no csv')
    ) {
      return (
        'No supported source data was found. ' +
        'Select CSV files or a valid ZIP archive.'
      );
    }

    if (
      stepKey === 'quality'
    ) {
      return (
        'The uploaded information contains items ' +
        'that must be reviewed before continuing.'
      );
    }

    if (
      stepKey === 'ready'
    ) {
      return (
        'The disclosure information could not be ' +
        'prepared. Review the source files and try again.'
      );
    }

    return (
      'Data preparation could not be completed. ' +
      'Review the selected files and try again.'
    );
  }

  private buildAutomaticBatchName(): string {
    return (
      `Data preparation ${
        new Date().toISOString()
      }`
    );
  }

  private isSupportedFile(
    file: File
  ): boolean {
    const name =
      file.name.toLowerCase();

    return (
      name.endsWith('.csv') ||
      name.endsWith('.zip')
    );
  }

  private getStepStatus(
    stepKey: PreparationStepKey
  ): StepStatus {
    return (
      this.steps.find(
        (step) =>
          step.key === stepKey
      )?.status ??
      'pending'
    );
  }

  private setStepStatus(
    stepKey: PreparationStepKey,
    status: StepStatus
  ): void {
    this.steps =
      this.steps.map(
        (step) =>
          step.key === stepKey
            ? {
                ...step,
                status,
              }
            : step
      );
  }

  private resetProcessingState(): void {
    this.errorMessage = '';
    this.successMessage = '';
    this.completedAt = null;

    this.uploadResult = null;
    this.detectionResult = null;
    this.mappingResult = null;
    this.canonicalResult = null;
    this.validationResult = null;
    this.payloadResult = null;
    this.activeManifest = null;

    this.steps =
      this.steps.map(
        (step) => ({
          ...step,
          status: 'pending',
        })
      );
  }

  private storeActivePayloadManifest(
    manifest: GeneratedPayloadManifest
  ): void {
    localStorage.setItem(
      'activePayloadManifestId',
      String(manifest.id)
    );
    localStorage.setItem(
      'activeReportBankCode',
      manifest.bank_code
    );
    localStorage.setItem(
      'activeReportingYear',
      String(
        manifest.reporting_year
      )
    );
    localStorage.setItem(
      'activePayloadManifestVersion',
      manifest.version
    );

    if (this.currentBatch) {
      localStorage.setItem(
        'activeDataPreparationBatchId',
        this.currentBatch.id
      );
    }
  }

  private clearActivePayloadManifest(): void {
    localStorage.removeItem(
      'activePayloadManifestId'
    );
    localStorage.removeItem(
      'activeReportBankCode'
    );
    localStorage.removeItem(
      'activeReportingYear'
    );
    localStorage.removeItem(
      'activePayloadManifestVersion'
    );
    localStorage.removeItem(
      'activeDataPreparationBatchId'
    );
  }
}