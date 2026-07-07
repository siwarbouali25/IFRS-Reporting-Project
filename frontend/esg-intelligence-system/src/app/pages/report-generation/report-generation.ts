import { Component, OnDestroy, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { RouterLink } from '@angular/router';
import { FormsModule } from '@angular/forms';

import {
  GenerationJob,
  GenerationJobStatus,
  GenerationWarning,
  Report,
  ReportArtifact,
  StartGenerationRequest,
} from '../../core/services/report';

@Component({
  selector: 'app-report-generation',
  imports: [CommonModule, RouterLink, FormsModule],
  templateUrl: './report-generation.html',
  styleUrl: './report-generation.css',
})
export class ReportGeneration implements OnInit, OnDestroy {
  bankCode = 'BANK01';
  reportingYear = 2024;
  payloadManifestId = 1;
  ifrsAssetVersion = 'ifrs_s1_s2_2024';
  styleAssetVersion = 'bank01_style_v1';
  maxRevisions = 2;

  jobs: GenerationJob[] = [];
  currentJob: GenerationJob | null = null;
  warnings: GenerationWarning[] = [];
  artifacts: ReportArtifact[] = [];

  selectedPreviewArtifact: ReportArtifact | null = null;
  previewText = '';

  isStarting = false;
  isLoadingJobs = false;
  isPolling = false;
  isPreviewLoading = false;
  errorMessage = '';

  private pollingTimeout?: ReturnType<typeof setTimeout>;
  private pollingStartedAt = 0;

  constructor(private reportService: Report) {}

  ngOnInit(): void {
    this.loadJobs();
  }

  ngOnDestroy(): void {
    this.stopPolling();
  }

  generateDraft(): void {
    this.errorMessage = '';
    this.warnings = [];
    this.artifacts = [];
    this.selectedPreviewArtifact = null;
    this.previewText = '';
    this.isStarting = true;

    const payload: StartGenerationRequest = {
      bank_code: this.bankCode,
      reporting_year: this.reportingYear,
      payload_manifest_id: this.payloadManifestId,
      ifrs_asset_version: this.ifrsAssetVersion,
      style_asset_version: this.styleAssetVersion,
      output_formats: ['markdown'],
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
    this.selectedPreviewArtifact = null;
    this.previewText = '';
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

        const nextDelay = this.getPollingDelayMs();

        this.pollingTimeout = setTimeout(() => {
          this.pollJob(jobId);
        }, nextDelay);
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

    // First 2 minutes: refresh every 5 seconds.
    if (elapsedMs < 2 * 60 * 1000) {
      return 5000;
    }

    // After that: report generation is long-running, so reduce backend pressure.
    return 60000;
  }

  private stopPolling(): void {
    if (this.pollingTimeout) {
      clearTimeout(this.pollingTimeout);
      this.pollingTimeout = undefined;
    }

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
        this.errorMessage = 'Report generated, but warnings could not be loaded.';
      },
    });
  }

  private loadArtifacts(jobId: string): void {
    this.reportService.getArtifacts(jobId).subscribe({
      next: (artifacts) => {
        this.artifacts = artifacts;

        const finalReport = this.finalReportArtifact;

        if (finalReport) {
          this.previewArtifact(finalReport);
        }
      },
      error: () => {
        this.errorMessage = 'Report generated, but artifacts could not be loaded.';
      },
    });
  }

  previewArtifact(artifact: ReportArtifact): void {
    if (!this.canPreviewArtifact(artifact)) {
      this.downloadArtifact(artifact);
      return;
    }

    this.selectedPreviewArtifact = artifact;
    this.previewText = '';
    this.isPreviewLoading = true;

    this.reportService.downloadArtifact(artifact.id).subscribe({
      next: async (blob) => {
        const text = await blob.text();

        if (artifact.content_type === 'application/json' || artifact.object_key.endsWith('.json')) {
          try {
            this.previewText = JSON.stringify(JSON.parse(text), null, 2);
          } catch {
            this.previewText = text;
          }
        } else {
          this.previewText = text;
        }

        this.isPreviewLoading = false;
      },
      error: () => {
        this.isPreviewLoading = false;
        this.errorMessage = 'Could not preview artifact.';
      },
    });
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
        this.errorMessage = 'Could not download artifact.';
      },
    });
  }

  private upsertJob(job: GenerationJob): void {
    const index = this.jobs.findIndex((item) => item.job_id === job.job_id);

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

  get sortedArtifacts(): ReportArtifact[] {
    return [...this.artifacts].sort(
      (a, b) => this.getArtifactPriority(a) - this.getArtifactPriority(b)
    );
  }

  get finalReportArtifact(): ReportArtifact | null {
    return (
      this.artifacts.find((artifact) => artifact.artifact_type === 'final_markdown') ||
      null
    );
  }

  get statusLabel(): string {
    if (!this.currentJob) {
      return 'Not started';
    }

    return this.formatStatus(this.currentJob.status);
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

    const totalSeconds = Math.max(0, Math.floor((end - start) / 1000));
    const minutes = Math.floor(totalSeconds / 60);
    const seconds = totalSeconds % 60;

    if (minutes <= 0) {
      return `${seconds}s`;
    }

    return `${minutes}m ${seconds}s`;
  }

  getArtifactFilename(artifact: ReportArtifact): string {
    const parts = artifact.object_key.split('/');
    return parts[parts.length - 1] || `${artifact.artifact_type}.txt`;
  }

  getArtifactLabel(artifact: ReportArtifact): string {
    if (artifact.artifact_type === 'final_markdown') {
      return 'Approved Report Markdown';
    }

    if (artifact.artifact_type === 'audit_summary') {
      return 'Audit Summary';
    }

    if (
      artifact.artifact_type === 'log' &&
      artifact.object_key.includes('handoff_manifest')
    ) {
      return 'PDF Handoff Manifest';
    }

    if (artifact.artifact_type === 'warning_summary') {
      return 'Final Generation Summary';
    }

    return artifact.artifact_type
      .replaceAll('_', ' ')
      .replace(/\b\w/g, (char) => char.toUpperCase());
  }

  getArtifactDescription(artifact: ReportArtifact): string {
    if (artifact.artifact_type === 'final_markdown') {
      return 'Final IFRS S1/S2 report ready for review and approval.';
    }

    if (artifact.artifact_type === 'audit_summary') {
      return 'Internal audit trail and generation summary.';
    }

    if (
      artifact.artifact_type === 'log' &&
      artifact.object_key.includes('handoff_manifest')
    ) {
      return 'Manifest used for PDF handoff and document assembly.';
    }

    if (artifact.artifact_type === 'warning_summary') {
      return 'Final execution summary produced by the generation workflow.';
    }

    return artifact.object_key;
  }

  getArtifactPriority(artifact: ReportArtifact): number {
    if (artifact.artifact_type === 'final_markdown') {
      return 1;
    }

    if (artifact.artifact_type === 'audit_summary') {
      return 2;
    }

    if (
      artifact.artifact_type === 'log' &&
      artifact.object_key.includes('handoff_manifest')
    ) {
      return 3;
    }

    if (artifact.artifact_type === 'warning_summary') {
      return 4;
    }

    return 99;
  }

  canPreviewArtifact(artifact: ReportArtifact): boolean {
    return (
      artifact.content_type?.startsWith('text/') ||
      artifact.content_type === 'application/json' ||
      artifact.object_key.endsWith('.md') ||
      artifact.object_key.endsWith('.json') ||
      artifact.object_key.endsWith('.txt')
    );
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

  private extractErrorMessage(error: any, fallback: string): string {
    if (typeof error?.error === 'string') {
      return error.error;
    }

    return (
      error?.error?.detail ||
      error?.error?.non_field_errors?.[0] ||
      error?.error?.message ||
      fallback
    );
  }
}