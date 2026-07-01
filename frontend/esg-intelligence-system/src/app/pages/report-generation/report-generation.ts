import { Component, OnDestroy } from '@angular/core';
import { CommonModule } from '@angular/common';
import { RouterLink } from '@angular/router';
import { FormsModule } from '@angular/forms';
import { Subscription, timer } from 'rxjs';
import { switchMap, takeWhile } from 'rxjs/operators';

import {
  GenerationJob,
  GenerationWarning,
  Report,
  StartGenerationRequest,
} from '../../core/services/report';

@Component({
  selector: 'app-report-generation',
  imports: [CommonModule, RouterLink, FormsModule],
  templateUrl: './report-generation.html',
  styleUrl: './report-generation.css',
})
export class ReportGeneration implements OnDestroy {
  bankCode = 'BANK01';
  reportingYear = 2024;
  payloadManifestId = 1;
  ifrsAssetVersion = 'ifrs_s1_s2_2024';
  styleAssetVersion = 'bank01_style_v1';
  maxRevisions = 2;

  currentJob: GenerationJob | null = null;
  warnings: GenerationWarning[] = [];

  isStarting = false;
  isPolling = false;
  errorMessage = '';

  private pollingSubscription?: Subscription;

  sections = [
    { name: 'Governance', standard: 'IFRS S1', status: 'Waiting', score: '-' },
    { name: 'Strategy', standard: 'IFRS S1/S2', status: 'Waiting', score: '-' },
    { name: 'Risk Management', standard: 'IFRS S2', status: 'Waiting', score: '-' },
    { name: 'Metrics & Targets', standard: 'IFRS S2', status: 'Waiting', score: '-' },
  ];

  constructor(private reportService: Report) {}

  ngOnDestroy(): void {
    this.stopPolling();
  }

  generateDraft(): void {
    this.errorMessage = '';
    this.warnings = [];
    this.currentJob = null;
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
        this.currentJob = job;
        this.isStarting = false;
        this.startPolling(job.job_id);
      },
      error: (error) => {
        this.isStarting = false;
        this.errorMessage =
          error?.error?.detail ||
          error?.error?.non_field_errors?.[0] ||
          error?.error ||
          'Could not start report generation.';
      },
    });
  }

  private startPolling(jobId: string): void {
    this.stopPolling();
    this.isPolling = true;

    this.pollingSubscription = timer(0, 2000)
      .pipe(
        switchMap(() => this.reportService.getGenerationJob(jobId)),
        takeWhile(
          (job) => job.status === 'queued' || job.status === 'running',
          true
        )
      )
      .subscribe({
        next: (job) => {
          this.currentJob = job;
          this.updateSectionMockStatus(job);

          if (
            job.status === 'completed' ||
            job.status === 'completed_with_warnings' ||
            job.status === 'failed' ||
            job.status === 'cancelled'
          ) {
            this.isPolling = false;

            if (job.warning_count > 0) {
              this.loadWarnings(job.job_id);
            }
          }
        },
        error: () => {
          this.isPolling = false;
          this.errorMessage = 'Could not refresh report generation status.';
        },
      });
  }

  private stopPolling(): void {
    if (this.pollingSubscription) {
      this.pollingSubscription.unsubscribe();
      this.pollingSubscription = undefined;
    }

    this.isPolling = false;
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

  private updateSectionMockStatus(job: GenerationJob): void {
    if (job.progress_percent < 60) {
      this.sections = this.sections.map((section) => ({
        ...section,
        status: 'Waiting',
        score: '-',
      }));
      return;
    }

    if (job.progress_percent < 100) {
      this.sections = this.sections.map((section) => ({
        ...section,
        status: 'Generating',
        score: '-',
      }));
      return;
    }

    this.sections = [
      { name: 'Governance', standard: 'IFRS S1', status: 'Generated', score: '96%' },
      { name: 'Strategy', standard: 'IFRS S1/S2', status: 'Generated', score: '93%' },
      { name: 'Risk Management', standard: 'IFRS S2', status: 'Generated', score: '91%' },
      { name: 'Metrics & Targets', standard: 'IFRS S2', status: 'Generated', score: '94%' },
    ];
  }

  get statusLabel(): string {
    if (!this.currentJob) {
      return 'Not Started';
    }

    if (this.currentJob.status === 'completed_with_warnings') {
      return 'Completed with warnings';
    }

    return this.currentJob.status.replace('_', ' ');
  }

  get canSubmitForApproval(): boolean {
    return (
      this.currentJob?.status === 'completed' ||
      this.currentJob?.status === 'completed_with_warnings'
    );
  }
}