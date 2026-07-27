import { Component, OnDestroy, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import {
  DomSanitizer,
  SafeResourceUrl,
} from '@angular/platform-browser';
import { RouterLink } from '@angular/router';

import {
  GenerationJob,
  GenerationJobStatus,
  GenerationWarning,
  PayloadManifestSummary,
  Report,
  ReportArtifact,
  ReportVersion,
  ReportVersionStatus,
  StartGenerationRequest,
} from '../../core/services/report';

@Component({
  selector: 'app-report-generation',
  imports: [CommonModule, RouterLink],
  templateUrl: './report-generation.html',
  styleUrl: './report-generation.css',
})
export class ReportGeneration implements OnInit, OnDestroy {
  bankCode =
    localStorage.getItem('activeReportBankCode') ?? 'BANK01';
  reportingYear = Number(
    localStorage.getItem('activeReportingYear') ?? 2024
  );
  payloadManifestId = Number(
    localStorage.getItem('activePayloadManifestId') ?? 0
  );
  activePayloadManifest: PayloadManifestSummary | null = null;
  maxRevisions = 2;

  jobs: GenerationJob[] = [];
  currentJob: GenerationJob | null = null;
  warnings: GenerationWarning[] = [];
  artifacts: ReportArtifact[] = [];

  selectedPreviewArtifact: ReportArtifact | null = null;
  pdfPreviewUrl: SafeResourceUrl | null = null;
  currentReportVersion: ReportVersion | null = null;

  isStarting = false;
  isLoadingJobs = false;
  isLoadingPayloadManifest = false;
  isPolling = false;
  isPreviewLoading = false;
  errorMessage = '';

  private pollingTimeout?: ReturnType<typeof setTimeout>;
  private pollingStartedAt = 0;
  private progressTimer?: ReturnType<typeof setInterval>;
  private pdfObjectUrl: string | null = null;

  uiNow = Date.now();
  estimatedGenerationDurationMs = 35 * 60 * 1000;

  constructor(
    private reportService: Report,
    private sanitizer: DomSanitizer
  ) {}

  ngOnInit(): void {
    this.loadActivePayloadManifest();
    this.loadJobs();
  }

  ngOnDestroy(): void {
    this.stopPolling();
    this.stopProgressTimer();
    this.clearPdfPreview();
  }

  generateDraft(): void {
    this.errorMessage = '';

    if (!this.payloadManifestId) {
      this.errorMessage =
        'Generate payloads in Data Preparation before starting report generation.';
      return;
    }

    this.warnings = [];
    this.artifacts = [];
    this.currentReportVersion = null;
    this.clearPdfPreview();
    this.isStarting = true;

    const payload: StartGenerationRequest = {
      bank_code: this.bankCode,
      reporting_year: this.reportingYear,
      payload_manifest_id: this.payloadManifestId,
      output_formats: ['markdown', 'pdf'],
      max_revisions: this.maxRevisions,
    };

    this.reportService.startGenerationJob(payload).subscribe({
      next: (job) => {
        this.isStarting = false;
        this.currentJob = job;
        this.upsertJob(job);
        this.startPolling(job.job_id);
      },
      error: (error) => {
        this.isStarting = false;
        this.errorMessage = this.extractErrorMessage(
          error,
          'Could not start report generation.'
        );
      },
    });
  }

  private loadActivePayloadManifest(): void {
    this.isLoadingPayloadManifest = true;

    this.reportService
      .getPayloadManifests(
        this.bankCode,
        this.reportingYear
      )
      .subscribe({
        next: (manifests) => {
          this.isLoadingPayloadManifest = false;

          const selected = manifests.find(
            (manifest) =>
              manifest.id ===
              this.payloadManifestId &&
              manifest.status ===
                'available'
          );

          if (selected) {
            this.applyPayloadManifest(selected);
            return;
          }

          this.selectLatestPayloadManifest(
            manifests
          );

          if (!this.payloadManifestId) {
            this.errorMessage =
              'No prepared dataset is available. Complete Data Preparation first.';
          }
        },
        error: (error) => {
          this.isLoadingPayloadManifest = false;
          this.errorMessage =
            this.extractErrorMessage(
              error,
              'No prepared payload manifest could be loaded.'
            );
        },
      });
  }

  private selectLatestPayloadManifest(
    manifests: PayloadManifestSummary[]
  ): void {
    const available = manifests
      .filter((manifest) => manifest.status === 'available')
      .sort(
        (left, right) =>
          new Date(right.created_at).getTime() -
          new Date(left.created_at).getTime()
      );

    if (available.length === 0) {
      this.activePayloadManifest = null;
      this.payloadManifestId = 0;
      return;
    }

    this.applyPayloadManifest(available[0]);
  }

  private applyPayloadManifest(
    manifest: PayloadManifestSummary
  ): void {
    this.activePayloadManifest = manifest;
    this.payloadManifestId = manifest.id;
    this.bankCode = manifest.bank_code;
    this.reportingYear = manifest.reporting_year;

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
      String(manifest.reporting_year)
    );
    localStorage.setItem(
      'activePayloadManifestVersion',
      manifest.version
    );
  }

  loadJobs(): void {
    this.isLoadingJobs = true;
    this.errorMessage = '';

    this.reportService.getGenerationJobs().subscribe({
      next: (jobs) => {
        this.jobs = jobs;

        if (!this.currentJob && jobs.length > 0) {
          this.selectJob(jobs[0]);
        }

        this.isLoadingJobs = false;
      },
      error: (error) => {
        this.isLoadingJobs = false;
        this.errorMessage = this.extractErrorMessage(
          error,
          'Could not load report generation jobs.'
        );
      },
    });
  }

  selectJob(job: GenerationJob): void {
    this.stopPolling();
    this.currentJob = job;
    this.warnings = [];
    this.artifacts = [];
    this.currentReportVersion = null;
    this.clearPdfPreview();
    this.errorMessage = '';

    this.refreshCurrentJob(false);

    if (this.isTerminalStatus(job.status)) {
      this.loadJobOutputs(job.job_id);
    } else {
      this.startPolling(job.job_id);
    }
  }

  refreshCurrentJob(showLoadingError = true): void {
    if (!this.currentJob) {
      return;
    }

    const jobId = this.currentJob.job_id;

    this.reportService.getGenerationJob(jobId).subscribe({
      next: (job) => {
        this.currentJob = job;
        this.upsertJob(job);

        if (this.isTerminalStatus(job.status)) {
          this.stopPolling();
          this.loadJobOutputs(job.job_id);
        }
      },
      error: (error) => {
        if (showLoadingError) {
          this.errorMessage = this.extractErrorMessage(
            error,
            'Could not refresh job status.'
          );
        }
      },
    });
  }

  private startPolling(jobId: string): void {
    this.stopPolling();
    this.isPolling = true;
    this.pollingStartedAt = Date.now();
    this.startProgressTimer();
    this.pollJob(jobId);
  }

  private pollJob(jobId: string): void {
    this.reportService.getGenerationJob(jobId).subscribe({
      next: (job) => {
        this.currentJob = job;
        this.upsertJob(job);

        if (this.isTerminalStatus(job.status)) {
          this.stopPolling();
          this.loadJobOutputs(job.job_id);
          return;
        }

        this.pollingTimeout = setTimeout(() => {
          this.pollJob(jobId);
        }, this.getPollingDelayMs());
      },
      error: (error) => {
        this.stopPolling();
        this.errorMessage = this.extractErrorMessage(
          error,
          'Could not refresh report generation status.'
        );
      },
    });
  }

  private getPollingDelayMs(): number {
    const elapsedMs = Date.now() - this.pollingStartedAt;
    return elapsedMs < 2 * 60 * 1000 ? 5000 : 60000;
  }

  private stopPolling(): void {
    if (this.pollingTimeout) {
      clearTimeout(this.pollingTimeout);
      this.pollingTimeout = undefined;
    }

    this.stopProgressTimer();
    this.isPolling = false;
  }

  loadJobOutputs(jobId: string): void {
    this.loadWarnings(jobId);
    this.loadArtifacts(jobId);
  }

  private loadWarnings(jobId: string): void {
    this.reportService.getWarnings(jobId).subscribe({
      next: (warnings) => {
        this.warnings = warnings;
      },
      error: () => {
        this.errorMessage =
          'Report generated, but warnings could not be loaded.';
      },
    });
  }

  private loadArtifacts(jobId: string): void {
    this.reportService.getArtifacts(jobId).subscribe({
      next: (artifacts) => {
        this.artifacts = artifacts;

        if (this.finalPdfArtifact) {
          this.previewPdfArtifact(this.finalPdfArtifact);
        }

        const reportVersionId =
          this.finalPdfArtifact?.report_version ??
          this.finalMarkdownArtifact?.report_version ??
          this.currentJob?.report_version_id;

        if (reportVersionId) {
          this.loadReportVersion(reportVersionId);
        }
      },
      error: () => {
        this.errorMessage =
          'Report generated, but final report files could not be loaded.';
      },
    });
  }

  private loadReportVersion(reportVersionId: string): void {
    this.reportService.getReportVersion(reportVersionId).subscribe({
      next: (version) => {
        this.currentReportVersion = version;
      },
      error: () => {
        this.errorMessage =
          'The report files are ready, but approval information could not be loaded.';
      },
    });
  }

  previewPdfArtifact(artifact: ReportArtifact): void {
    if (
      artifact.artifact_type !== 'final_pdf' &&
      artifact.content_type !== 'application/pdf'
    ) {
      return;
    }

    this.clearPdfPreview();
    this.selectedPreviewArtifact = artifact;
    this.isPreviewLoading = true;

    this.reportService.downloadArtifact(artifact.id, true).subscribe({
      next: (blob) => {
        this.pdfObjectUrl = window.URL.createObjectURL(blob);
        this.pdfPreviewUrl =
          this.sanitizer.bypassSecurityTrustResourceUrl(
            this.pdfObjectUrl
          );
        this.isPreviewLoading = false;
      },
      error: () => {
        this.isPreviewLoading = false;
        this.errorMessage = 'Could not load the PDF preview.';
      },
    });
  }

  private clearPdfPreview(): void {
    if (this.pdfObjectUrl) {
      window.URL.revokeObjectURL(this.pdfObjectUrl);
      this.pdfObjectUrl = null;
    }

    this.pdfPreviewUrl = null;
    this.selectedPreviewArtifact = null;
  }

  downloadArtifact(artifact: ReportArtifact): void {
    this.reportService.downloadArtifact(artifact.id).subscribe({
      next: (blob) => {
        const url = window.URL.createObjectURL(blob);
        const link = document.createElement('a');
        link.href = url;
        link.download = this.getArtifactFilename(artifact);
        link.click();
        window.URL.revokeObjectURL(url);
      },
      error: () => {
        this.errorMessage = 'Could not download the report file.';
      },
    });
  }

  private upsertJob(job: GenerationJob): void {
    const index = this.jobs.findIndex(
      (item) => item.job_id === job.job_id
    );

    if (index >= 0) {
      this.jobs[index] = job;
      this.jobs = [...this.jobs];
      return;
    }

    this.jobs = [job, ...this.jobs];
  }

  private isTerminalStatus(status: GenerationJobStatus): boolean {
    return (
      status === 'completed' ||
      status === 'completed_with_warnings' ||
      status === 'failed' ||
      status === 'cancelled'
    );
  }


  get recentJobs(): GenerationJob[] {
    return this.jobs.slice(0, 3);
  }

  get visibleArtifacts(): ReportArtifact[] {
    return [...this.artifacts].sort(
      (left, right) =>
        this.getArtifactPriority(left) -
        this.getArtifactPriority(right)
    );
  }

  get finalPdfArtifact(): ReportArtifact | null {
    return (
      this.artifacts.find(
        (artifact) => artifact.artifact_type === 'final_pdf'
      ) ?? null
    );
  }

  get finalMarkdownArtifact(): ReportArtifact | null {
    return (
      this.artifacts.find(
        (artifact) => artifact.artifact_type === 'final_markdown'
      ) ?? null
    );
  }

  get finalReportArtifact(): ReportArtifact | null {
    return this.finalPdfArtifact ?? this.finalMarkdownArtifact;
  }

  get statusLabel(): string {
    return this.currentJob
      ? this.formatStatus(this.currentJob.status)
      : 'Not started';
  }

  get canSubmitForApproval(): boolean {
    return (
      this.currentJob?.status === 'completed' ||
      this.currentJob?.status === 'completed_with_warnings'
    );
  }

  get isRunningJob(): boolean {
    return (
      this.currentJob?.status === 'queued' ||
      this.currentJob?.status === 'running'
    );
  }

  get generationDuration(): string {
    if (!this.currentJob?.started_at) {
      return 'Not started';
    }

    const start = new Date(this.currentJob.started_at).getTime();
    const end = this.currentJob.completed_at
      ? new Date(this.currentJob.completed_at).getTime()
      : Date.now();
    const totalSeconds = Math.max(
      0,
      Math.floor((end - start) / 1000)
    );
    const minutes = Math.floor(totalSeconds / 60);
    const seconds = totalSeconds % 60;
    return minutes <= 0 ? `${seconds}s` : `${minutes}m ${seconds}s`;
  }

  getArtifactFilename(artifact: ReportArtifact): string {
    const parts = artifact.object_key.split('/');
    return parts[parts.length - 1] || `${artifact.artifact_type}.file`;
  }

  getArtifactLabel(artifact: ReportArtifact): string {
    if (artifact.artifact_type === 'final_pdf') {
      return 'IFRS S1/S2 Report PDF';
    }
    if (artifact.artifact_type === 'final_markdown') {
      return 'Source Markdown';
    }
    return artifact.artifact_type
      .replaceAll('_', ' ')
      .replace(/\b\w/g, (character) => character.toUpperCase());
  }

  getArtifactDescription(artifact: ReportArtifact): string {
    if (artifact.artifact_type === 'final_pdf') {
      return 'Final formatted report for review, approval, and download.';
    }
    return 'Editable source version of the generated report.';
  }

  getArtifactPriority(artifact: ReportArtifact): number {
    if (artifact.artifact_type === 'final_pdf') {
      return 1;
    }
    if (artifact.artifact_type === 'final_markdown') {
      return 2;
    }
    return 99;
  }

  formatStatus(status: string): string {
    return status.replaceAll('_', ' ');
  }

  getStatusClass(status?: string): string {
    if (!status) {
      return 'neutral';
    }
    if (status === 'completed') {
      return 'success';
    }
    if (status === 'completed_with_warnings') {
      return 'warning';
    }
    if (status === 'failed' || status === 'cancelled') {
      return 'danger';
    }
    if (status === 'running' || status === 'queued') {
      return 'active';
    }
    return 'neutral';
  }

  getApprovalStatusClass(status?: ReportVersionStatus): string {
    if (status === 'approved') {
      return 'success';
    }
    if (status === 'changes_requested' || status === 'rejected') {
      return 'danger';
    }
    if (status === 'pending_review') {
      return 'warning';
    }
    return 'active';
  }

  formatBytes(bytes?: number): string {
    if (!bytes) {
      return '-';
    }
    if (bytes < 1024) {
      return `${bytes} B`;
    }
    if (bytes < 1024 * 1024) {
      return `${(bytes / 1024).toFixed(1)} KB`;
    }
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  }

  get displayProgressPercent(): number {
    if (!this.currentJob) {
      return 0;
    }
    if (
      this.currentJob.status === 'completed' ||
      this.currentJob.status === 'completed_with_warnings' ||
      this.currentJob.status === 'failed'
    ) {
      return 100;
    }
    if (
      this.currentJob.progress_percent &&
      this.currentJob.progress_percent > 0
    ) {
      return this.currentJob.progress_percent;
    }
    if (this.currentJob.status === 'queued') {
      return 6;
    }
    if (this.currentJob.status === 'running') {
      const startTime = this.currentJob.started_at
        ? new Date(this.currentJob.started_at).getTime()
        : new Date(this.currentJob.created_at).getTime();
      const elapsed = Math.max(0, this.uiNow - startTime);
      const estimated = Math.round(
        10 +
          (elapsed / this.estimatedGenerationDurationMs) * 82
      );
      return Math.min(92, Math.max(10, estimated));
    }
    return 0;
  }

  private startProgressTimer(): void {
    this.stopProgressTimer();
    this.uiNow = Date.now();
    this.progressTimer = setInterval(() => {
      this.uiNow = Date.now();
    }, 1000);
  }

  private stopProgressTimer(): void {
    if (this.progressTimer) {
      clearInterval(this.progressTimer);
      this.progressTimer = undefined;
    }
  }

  get userFriendlyStage(): string {
    if (!this.currentJob) {
      return 'Not started';
    }
    if (this.currentJob.status === 'queued') {
      return 'Preparing your report request';
    }
    if (this.currentJob.status === 'running') {
      return 'Generating the IFRS S1/S2 report';
    }
    if (this.currentJob.status === 'completed') {
      return 'Report ready for review';
    }
    if (this.currentJob.status === 'completed_with_warnings') {
      return 'Report ready with review notes';
    }
    if (this.currentJob.status === 'failed') {
      return 'Report generation failed';
    }
    return this.formatStatus(this.currentJob.status);
  }

  private extractErrorMessage(error: any, fallback: string): string {
    if (error?.status === 0) {
      return (
        'Could not reach the Django API at 127.0.0.1:8000. ' +
        'Start Django and refresh the page.'
      );
    }

    if (error?.status === 401) {
      return 'Your session has expired. Sign in again.';
    }

    if (typeof error?.error === 'string') {
      return error.error;
    }

    const apiError = error?.error;

    if (
      apiError &&
      typeof apiError === 'object'
    ) {
      const preferredFields = [
        'payload_manifest_id',
        'ifrs_asset_version',
        'style_asset_version',
        'non_field_errors',
        'detail',
        'message',
      ];

      for (
        const field of preferredFields
      ) {
        const value = apiError[field];

        if (
          Array.isArray(value) &&
          value.length > 0
        ) {
          return String(value[0]);
        }

        if (
          typeof value === 'string'
        ) {
          return value;
        }
      }

      const firstField =
        Object.keys(apiError)[0];
      const firstValue =
        firstField
          ? apiError[firstField]
          : null;

      if (
        Array.isArray(firstValue) &&
        firstValue.length > 0
      ) {
        return String(firstValue[0]);
      }

      if (
        typeof firstValue === 'string'
      ) {
        return firstValue;
      }
    }

    return fallback;
  }
}
