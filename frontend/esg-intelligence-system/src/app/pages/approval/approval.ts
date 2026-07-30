import { CommonModule } from '@angular/common';
import { Component, OnDestroy, OnInit } from '@angular/core';
import { FormsModule } from '@angular/forms';
import {
  DomSanitizer,
  SafeResourceUrl,
} from '@angular/platform-browser';
import {
  ActivatedRoute,
  Router,
  RouterLink,
} from '@angular/router';
import {
  Observable,
  catchError,
  forkJoin,
  of,
} from 'rxjs';

import { AuthUser } from '../../core/auth/auth.models';
import { TokenService } from '../../core/auth/token.service';
import {
  GenerationWarning,
  Report,
  ReportArtifact,
  ReportSection,
  ReportVersion,
  ReportVersionStatus,
} from '../../core/services/report';

type CheckState = 'pass' | 'warning' | 'fail' | 'pending';

interface ValidationCheck {
  label: string;
  detail: string;
  state: CheckState;
}

@Component({
  selector: 'app-approval',
  imports: [CommonModule, FormsModule, RouterLink],
  templateUrl: './approval.html',
  styleUrl: './approval.css',
})
export class Approval implements OnInit, OnDestroy {
  versions: ReportVersion[] = [];
  currentVersion: ReportVersion | null = null;
  selectedVersionId = '';
  warnings: GenerationWarning[] = [];
  artifacts: ReportArtifact[] = [];
  reviewComment = '';
  currentUser: AuthUser | null = null;

  pdfPreviewUrl: SafeResourceUrl | null = null;
  private pdfObjectUrl: string | null = null;

  isLoadingVersions = false;
  isLoadingWorkspace = false;
  isPreviewLoading = false;
  isActionRunning = false;
  errorMessage = '';
  successMessage = '';

  constructor(
    private reportService: Report,
    private tokenService: TokenService,
    private sanitizer: DomSanitizer,
    private route: ActivatedRoute,
    private router: Router
  ) {}

  ngOnInit(): void {
    this.currentUser = this.tokenService.getUser();
    this.loadVersions(
      this.route.snapshot.queryParamMap.get('report')
    );
  }

  ngOnDestroy(): void {
    this.clearPdfPreview();
  }

  loadVersions(preferredVersionId?: string | null): void {
    this.isLoadingVersions = true;
    this.errorMessage = '';
    this.successMessage = '';

    this.reportService.getReportVersions().subscribe({
      next: (versions) => {
        this.versions = [...versions].sort(
          (left, right) =>
            new Date(right.created_at).getTime() -
            new Date(left.created_at).getTime()
        );
        this.isLoadingVersions = false;

        if (this.versions.length === 0) {
          this.resetWorkspace();
          return;
        }

        const preferred = this.versions.find(
          (version) => version.id === preferredVersionId
        );
        const current = this.versions.find(
          (version) => version.id === this.currentVersion?.id
        );
        this.selectVersion(
          (preferred ?? current ?? this.versions[0]).id
        );
      },
      error: (error) => {
        this.isLoadingVersions = false;
        this.errorMessage = this.extractErrorMessage(
          error,
          'Could not load report versions.'
        );
      },
    });
  }

  selectVersion(reportVersionId: string): void {
    if (!reportVersionId) {
      return;
    }

    this.selectedVersionId = reportVersionId;
    this.isLoadingWorkspace = true;
    this.errorMessage = '';
    this.successMessage = '';
    this.warnings = [];
    this.artifacts = [];
    this.clearPdfPreview();

    void this.router.navigate([], {
      relativeTo: this.route,
      queryParams: { report: reportVersionId },
      queryParamsHandling: 'merge',
      replaceUrl: true,
    });

    this.reportService
      .getReportVersion(reportVersionId)
      .subscribe({
        next: (version) => {
          this.currentVersion = version;
          this.reviewComment =
            version.status === 'pending_review'
              ? ''
              : version.review_comment ?? '';
          this.replaceVersion(version);
          this.loadWorkspaceDetails(version);
        },
        error: (error) => {
          this.isLoadingWorkspace = false;
          this.errorMessage = this.extractErrorMessage(
            error,
            'Could not load the selected report.'
          );
        },
      });
  }

  private loadWorkspaceDetails(version: ReportVersion): void {
    forkJoin({
      warnings: this.reportService
        .getWarnings(version.job_id)
        .pipe(
          catchError(() => of([] as GenerationWarning[]))
        ),
      artifacts: this.reportService
        .getArtifacts(version.job_id)
        .pipe(
          catchError(() => of([] as ReportArtifact[]))
        ),
    }).subscribe({
      next: ({ warnings, artifacts }) => {
        this.warnings = warnings;
        this.artifacts = artifacts;
        this.isLoadingWorkspace = false;

        if (this.finalPdfArtifact) {
          this.previewPdf(this.finalPdfArtifact);
        }
      },
      error: () => {
        this.isLoadingWorkspace = false;
        this.errorMessage =
          'The report loaded, but its review files could not be retrieved.';
      },
    });
  }

  previewPdf(artifact: ReportArtifact): void {
    this.clearPdfPreview();
    this.isPreviewLoading = true;

    this.reportService
      .downloadArtifact(artifact.id, true)
      .subscribe({
        next: (blob) => {
          this.pdfObjectUrl =
            window.URL.createObjectURL(blob);
          this.pdfPreviewUrl =
            this.sanitizer.bypassSecurityTrustResourceUrl(
              this.pdfObjectUrl
            );
          this.isPreviewLoading = false;
        },
        error: () => {
          this.isPreviewLoading = false;
          this.errorMessage =
            'Could not load the PDF preview.';
        },
      });
  }

  openPdfFullScreen(): void {
    if (!this.pdfObjectUrl) {
      if (this.finalPdfArtifact) {
        this.previewPdf(this.finalPdfArtifact);
      }
      return;
    }

    window.open(
      this.pdfObjectUrl,
      '_blank',
      'noopener,noreferrer'
    );
  }

  downloadArtifact(artifact: ReportArtifact): void {
    this.reportService
      .downloadArtifact(artifact.id)
      .subscribe({
        next: (blob) => {
          const url = window.URL.createObjectURL(blob);
          const link = document.createElement('a');
          link.href = url;
          link.download = this.getArtifactFilename(artifact);
          link.click();
          window.URL.revokeObjectURL(url);
        },
        error: () => {
          this.errorMessage =
            'Could not download the selected report file.';
        },
      });
  }

  submitForReview(): void {
    if (!this.currentVersion?.can_submit) {
      return;
    }

    this.runApprovalAction(
      this.reportService.submitForReview(
        this.currentVersion.id,
        this.reviewComment
      ),
      'The report was submitted for independent review.'
    );
  }

  approveReport(): void {
    if (!this.currentVersion?.can_review) {
      return;
    }

    this.runApprovalAction(
      this.reportService.approveReport(
        this.currentVersion.id,
        this.reviewComment
      ),
      'The report version was approved and locked.'
    );
  }

  requestChanges(): void {
    if (
      !this.currentVersion?.can_review ||
      !this.reviewComment.trim()
    ) {
      this.errorMessage =
        'Add a clear review comment before requesting changes.';
      return;
    }

    this.runApprovalAction(
      this.reportService.requestChanges(
        this.currentVersion.id,
        this.reviewComment
      ),
      'The change request was recorded.'
    );
  }

  rejectReport(): void {
    if (
      !this.currentVersion?.can_review ||
      !this.reviewComment.trim()
    ) {
      this.errorMessage =
        'Add a rejection reason before rejecting the report.';
      return;
    }

    if (!window.confirm('Reject this report version?')) {
      return;
    }

    this.runApprovalAction(
      this.reportService.rejectReport(
        this.currentVersion.id,
        this.reviewComment
      ),
      'The report version was rejected.'
    );
  }

  private runApprovalAction(
    request: Observable<ReportVersion>,
    successMessage: string
  ): void {
    this.isActionRunning = true;
    this.errorMessage = '';
    this.successMessage = '';

    request.subscribe({
      next: (version) => {
        this.currentVersion = version;
        this.reviewComment = version.review_comment ?? '';
        this.replaceVersion(version);
        this.isActionRunning = false;
        this.successMessage = successMessage;
      },
      error: (error) => {
        this.isActionRunning = false;
        this.errorMessage = this.extractErrorMessage(
          error,
          'The review action could not be completed.'
        );
      },
    });
  }

  private replaceVersion(version: ReportVersion): void {
    const index = this.versions.findIndex(
      (item) => item.id === version.id
    );
    if (index < 0) {
      this.versions = [version, ...this.versions];
      return;
    }

    this.versions[index] = version;
    this.versions = [...this.versions];
  }

  private resetWorkspace(): void {
    this.currentVersion = null;
    this.selectedVersionId = '';
    this.warnings = [];
    this.artifacts = [];
    this.reviewComment = '';
    this.clearPdfPreview();
  }

  private clearPdfPreview(): void {
    if (this.pdfObjectUrl) {
      window.URL.revokeObjectURL(this.pdfObjectUrl);
      this.pdfObjectUrl = null;
    }
    this.pdfPreviewUrl = null;
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
        (artifact) =>
          artifact.artifact_type === 'final_markdown'
      ) ?? null
    );
  }

  get relatedVersions(): ReportVersion[] {
    if (!this.currentVersion) {
      return [];
    }

    return this.versions
      .filter(
        (version) =>
          version.bank_code ===
            this.currentVersion?.bank_code &&
          version.reporting_year ===
            this.currentVersion?.reporting_year
      )
      .sort(
        (left, right) =>
          right.version_number - left.version_number
      );
  }

  get validationChecks(): ValidationCheck[] {
    if (!this.currentVersion) {
      return [];
    }

    const generationComplete = [
      'completed',
      'completed_with_warnings',
    ].includes(this.currentVersion.generation_status);

    return [
      {
        label: 'Generation completed',
        detail: generationComplete
          ? 'The report generation job reached a final deliverable.'
          : 'The generation job is not in a completed state.',
        state: generationComplete ? 'pass' : 'fail',
      },
      {
        label: 'Review files available',
        detail:
          this.finalPdfArtifact &&
          this.finalMarkdownArtifact
            ? 'PDF and Markdown deliverables are available.'
            : this.finalPdfArtifact
              ? 'PDF is available; Markdown is missing.'
              : 'The final PDF is not available.',
        state:
          this.finalPdfArtifact &&
          this.finalMarkdownArtifact
            ? 'pass'
            : this.finalPdfArtifact
              ? 'warning'
              : 'fail',
      },
      {
        label: 'Generation warnings',
        detail:
          this.warnings.length > 0
            ? `${this.warnings.length} warning${this.warnings.length === 1 ? '' : 's'} require reviewer attention.`
            : 'No generation warnings were recorded.',
        state:
          this.warnings.length > 0
            ? 'warning'
            : 'pass',
      },
      {
        label: 'Approval decision',
        detail:
          this.currentVersion.status === 'approved'
            ? 'This version is approved and locked.'
            : this.currentVersion.status ===
                'pending_review'
              ? 'An independent review decision is pending.'
              : 'The version has not been approved.',
        state:
          this.currentVersion.status === 'approved'
            ? 'pass'
            : this.currentVersion.status ===
                  'changes_requested' ||
                this.currentVersion.status === 'rejected'
              ? 'warning'
              : 'pending',
      },
    ];
  }

  get permissionMessage(): string {
    if (!this.currentVersion) {
      return '';
    }
    if (this.currentVersion.is_locked) {
      return 'This approved version is locked. Create a new version to make further changes.';
    }
    if (this.currentVersion.can_review) {
      return 'You can approve, request changes, or reject this pending version.';
    }
    if (this.currentVersion.can_submit) {
      return 'You can submit this version for independent review.';
    }
    if (this.currentUser?.role === 'expert_reviewer') {
      return 'A review decision becomes available when the report is pending review.';
    }
    return 'You have read-only access to this report version.';
  }

  sectionLabel(section: ReportSection): string {
    return section.section_key
      .replaceAll('_', ' ')
      .replace(/\b\w/g, (character) =>
        character.toUpperCase()
      );
  }

  formatStatus(status: string): string {
    return status
      .replaceAll('_', ' ')
      .replace(/\b\w/g, (character) =>
        character.toUpperCase()
      );
  }

  getStatusClass(
    status?: ReportVersionStatus | string
  ): string {
    if (status === 'approved' || status === 'completed') {
      return 'success';
    }
    if (
      status === 'changes_requested' ||
      status === 'rejected' ||
      status === 'failed' ||
      status === 'validation_failed'
    ) {
      return 'danger';
    }
    if (
      status === 'pending_review' ||
      status === 'warning' ||
      status === 'completed_with_warnings'
    ) {
      return 'warning';
    }
    return 'active';
  }

  checkIcon(state: CheckState): string {
    if (state === 'pass') {
      return 'pi pi-check';
    }
    if (state === 'fail') {
      return 'pi pi-times';
    }
    if (state === 'warning') {
      return 'pi pi-exclamation-triangle';
    }
    return 'pi pi-clock';
  }

  getArtifactFilename(artifact: ReportArtifact): string {
    const parts = artifact.object_key.split('/');
    return (
      parts[parts.length - 1] ||
      `${artifact.artifact_type}.file`
    );
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

  private extractErrorMessage(
    error: any,
    fallback: string
  ): string {
    if (error?.status === 0) {
      return (
        'Could not reach the Django API at 127.0.0.1:8000. ' +
        'Start Django and refresh the page.'
      );
    }
    if (error?.status === 401) {
      return 'Your session has expired. Sign in again.';
    }

    const apiError = error?.error;
    if (typeof apiError === 'string') {
      return apiError;
    }
    if (apiError?.detail) {
      return String(apiError.detail);
    }
    if (Array.isArray(apiError?.comment)) {
      return String(apiError.comment[0]);
    }
    return fallback;
  }
}