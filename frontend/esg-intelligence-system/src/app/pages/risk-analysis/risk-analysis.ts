import { Component, ElementRef, ViewChild } from '@angular/core';
import { CommonModule } from '@angular/common';
import { ChartModule } from 'primeng/chart';
import { HttpErrorResponse } from '@angular/common/http';
import {
  AssessmentResult,
  EvidenceItem,
  ProcessedBundle,
  Risk as RiskService,
  RiskAnalysis as RiskAnalysisModel,
} from '../../core/services/risk';

type ViewState = 'empty' | 'uploading' | 'ready' | 'error';

@Component({
  selector: 'app-risk-analysis',
  imports: [CommonModule, ChartModule],
  templateUrl: './risk-analysis.html',
  styleUrl: './risk-analysis.css',
})
export class RiskAnalysis {
  @ViewChild('fileInput') fileInput!: ElementRef<HTMLInputElement>;

  state: ViewState = 'empty';
  errorMessage = '';
  analysis: RiskAnalysisModel | null = null;
  bundle: ProcessedBundle | null = null;

  assessmentLoading = false;
  assessment: AssessmentResult | null = null;
  hoveredEvidenceId: string | null = null;

  /** index into evidence[] for O(1) lookup when rendering hover markers */
  private evidenceMap: Record<string, EvidenceItem> = {};

  constructor(private riskService: RiskService) {}

  // --------------------------------------------------------------------- //
  // upload workflow
  // --------------------------------------------------------------------- //

  triggerFilePicker(): void {
    this.fileInput.nativeElement.click();
  }

  onFileSelected(event: Event): void {
    const input = event.target as HTMLInputElement;
    const file = input.files?.[0];
    if (!file) {
      return;
    }
    this.uploadFile(file);
    input.value = '';
  }

  onDrop(event: DragEvent): void {
    event.preventDefault();
    const file = event.dataTransfer?.files?.[0];
    if (file) {
      this.uploadFile(file);
    }
  }

  onDragOver(event: DragEvent): void {
    event.preventDefault();
  }

  private uploadFile(file: File): void {
    if (!file.name.toLowerCase().endsWith('.json')) {
      this.state = 'error';
      this.errorMessage = 'Please upload the reporting payload as a .json file.';
      return;
    }

    this.state = 'uploading';
    this.errorMessage = '';
    this.analysis = null;
    this.bundle = null;
    this.assessment = null;

    this.riskService.upload(file).subscribe({
      next: (analysis) => this.handleAnalysisReady(analysis),
      error: (err: HttpErrorResponse) => this.handleUploadError(err),
    });
  }

  private handleAnalysisReady(analysis: RiskAnalysisModel): void {
    this.analysis = analysis;

    if (analysis.status === 'failed') {
      this.state = 'error';
      this.errorMessage =
        analysis.error_message ||
        'The uploaded file is missing required sections and could not be processed.';
      return;
    }

    this.bundle = analysis.processed;
    this.evidenceMap = Object.fromEntries((this.bundle?.evidence || []).map((e) => [e.id, e]));
    this.state = 'ready';
    this.buildChartConfigs();
    this.requestAssessment();
  }

  private handleUploadError(err: HttpErrorResponse): void {
    this.state = 'error';
    if (err.status === 422) {
      this.errorMessage =
        err.error?.error_message ||
        'This file is missing required sections (bank, reporting_kpis, financial_summary) and cannot be processed.';
    } else if (err.status === 401) {
      this.errorMessage = 'Your session has expired. Please log in again.';
    } else if (err.status === 0) {
      this.errorMessage = 'Could not reach the server. Check that the backend is running.';
    } else {
      this.errorMessage = err.error?.detail || 'Something went wrong while processing the file.';
    }
  }

  reset(): void {
    this.state = 'empty';
    this.analysis = null;
    this.bundle = null;
    this.assessment = null;
    this.errorMessage = '';
  }

  // --------------------------------------------------------------------- //
  // assessment
  // --------------------------------------------------------------------- //

  private requestAssessment(): void {
    if (!this.analysis) return;
    this.assessmentLoading = true;
    this.riskService.generateAssessment(this.analysis.id).subscribe({
      next: (result) => {
        this.assessment = result;
        this.assessmentLoading = false;
      },
      error: () => {
        // The backend itself falls back to a deterministic template on any
        // LLM failure and still returns 201 — so a network-level error here
        // means the backend call itself didn't go through. Show inline
        // rather than blocking the rest of the dashboard.
        this.assessmentLoading = false;
        this.assessment = null;
      },
    });
  }

  regenerateAssessment(): void {
    this.assessment = null;
    this.requestAssessment();
  }

  /** Splits the assessment text on [E#] markers for hover-evidence rendering. */
  get assessmentSegments(): Array<{ text: string; evidenceId: string | null }> {
    if (!this.assessment) return [];
    const parts = this.assessment.assessment_text.split(/(\[E\d+\])/g);
    return parts.map((p) => {
      const m = p.match(/^\[(E\d+)\]$/);
      if (m && this.evidenceMap[m[1]]) {
        return { text: m[1], evidenceId: m[1] };
      }
      return { text: p, evidenceId: null };
    });
  }

  evidenceFor(id: string | null): EvidenceItem | null {
    return id ? this.evidenceMap[id] ?? null : null;
  }

  // --------------------------------------------------------------------- //
  // chart configs — built from whatever the backend computed; no chart
  // here has hardcoded labels/values, only presentation (colours, axis
  // formatting) is fixed.
  // --------------------------------------------------------------------- //

  intensityChartData: any;
  intensityChartOptions: any;
  opEmissionsChartData: any;
  opEmissionsChartOptions: any;
  financedCompositionData: any;
  financedCompositionOptions: any;
  riskByCategoryData: any;
  riskByCategoryOptions: any;
  physByHazardData: any;
  physByHazardOptions: any;
  scenariosData: any;
  scenariosOptions: any;
  dataQualityPieData: any;
  dataQualityPieOptions: any;
  peerBenchmarkData: any;
  peerBenchmarkOptions: any;
  sensitivityData: any;
  sensitivityOptions: any;

  private theme = {
    accent: '#c8df30',
    purple: '#9b5cff',
    red: '#d97070',
    amber: '#c9a24e',
    green: '#a8c93e',
    grey: '#7e8a92',
    synth: '#6e7681',
    muted: '#8a929b',
    mutedSoft: '#5e666e',
    surfaceSoft: '#1c1e20',
    border: '#272b2f',
  };

  private axisStyle = {
    ticks: { color: this.theme.mutedSoft, font: { size: 11, family: 'Inter, system-ui, sans-serif' } },
    grid: { color: 'rgba(255,255,255,0.045)' },
  };

  private tooltipBase = {
    backgroundColor: this.theme.surfaceSoft,
    borderColor: this.theme.border,
    borderWidth: 1,
    titleColor: '#eceef0',
    bodyColor: this.theme.muted,
    padding: 10,
  };

  private buildChartConfigs(): void {
    const b = this.bundle;
    if (!b) return;

    // --- carbon intensity vs NZBA milestones ---
    this.intensityChartData = {
      labels: b.intensity_trend.map((r) => r.year),
      datasets: [
        {
          label: 'Actual',
          data: b.intensity_trend.map((r) => r.actual),
          borderColor: this.theme.accent,
          backgroundColor: 'rgba(200,223,48,0.08)',
          pointBackgroundColor: '#0e1012',
          pointBorderColor: this.theme.accent,
          pointBorderWidth: 2,
          pointRadius: 3,
          tension: 0.3,
          fill: true,
          spanGaps: true,
        },
        {
          label: 'NZBA milestone',
          data: b.intensity_trend.map((r) => r.target),
          borderColor: this.theme.purple,
          borderDash: [5, 4],
          pointBackgroundColor: '#0e1012',
          pointBorderColor: this.theme.purple,
          pointBorderWidth: 2,
          pointRadius: 3,
          tension: 0,
          fill: false,
          spanGaps: true,
        },
      ],
    };
    this.intensityChartOptions = {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { labels: { color: this.theme.muted, font: { size: 11 } } },
        tooltip: { ...this.tooltipBase, callbacks: { label: (ctx: any) => ` ${ctx.dataset.label}: ${ctx.parsed.y ?? '—'} t/M€` } },
      },
      scales: { x: this.axisStyle, y: this.axisStyle },
    };

    // --- operational emissions stacked bars ---
    const opKeys = ['Scope 1', 'Scope 2 (market)', 'Scope 3 travel'];
    const opColors = [this.theme.accent, this.theme.grey, this.theme.purple];
    this.opEmissionsChartData = {
      labels: b.op_emissions.map((r) => r['year']),
      datasets: opKeys.map((key, i) => ({
        label: key,
        data: b.op_emissions.map((r) => r[key] ?? 0),
        backgroundColor: opColors[i],
        stack: 'op',
      })),
    };
    this.opEmissionsChartOptions = {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { labels: { color: this.theme.muted, font: { size: 11 } } },
        tooltip: { ...this.tooltipBase, callbacks: { label: (ctx: any) => ` ${ctx.dataset.label}: ${ctx.parsed.y} t` } },
      },
      scales: {
        x: { ...this.axisStyle, stacked: true },
        y: { ...this.axisStyle, stacked: true },
      },
    };

    // --- financed emissions composition (donut) ---
    const fc = b.financed_composition || [];
    this.financedCompositionData = {
      labels: fc.map((r) => r.name),
      datasets: [
        {
          data: fc.map((r) => r.value),
          backgroundColor: fc.map((r, i) => (r.proxy ? 'rgba(155,92,255,0.45)' : [this.theme.accent, this.theme.grey, this.theme.purple][i % 3])),
          borderColor: '#161819',
          borderWidth: 3,
          hoverOffset: 4,
        },
      ],
    };
    this.financedCompositionOptions = {
      responsive: true,
      maintainAspectRatio: false,
      cutout: '60%',
      plugins: {
        legend: { position: 'bottom', labels: { color: this.theme.muted, font: { size: 10.5 } } },
        tooltip: {
          ...this.tooltipBase,
          callbacks: {
            label: (ctx: any) => {
              const row = fc[ctx.dataIndex];
              const mt = (ctx.parsed / 1e6).toFixed(2);
              return ` ${row.name}: ${mt} Mt CO₂e${row.proxy ? ' (proxy)' : ''}`;
            },
          },
        },
      },
    };

    // --- risk register by category (stacked horizontal) ---
    const rbc = b.risk_by_category || [];
    const ratingKeys = Array.from(
      new Set(rbc.flatMap((r) => Object.keys(r).filter((k) => !['name', 'total'].includes(k))))
    );
    const ratingColors: Record<string, string> = {
      critical: this.theme.red,
      high: '#e08a4e',
      medium: this.theme.amber,
      low: this.theme.green,
    };
    this.riskByCategoryData = {
      labels: rbc.map((r) => r['name']),
      datasets: ratingKeys.map((key) => ({
        label: key,
        data: rbc.map((r) => r[key] ?? 0),
        backgroundColor: ratingColors[key] || this.theme.grey,
        stack: 'risk',
      })),
    };
    this.riskByCategoryOptions = {
      indexAxis: 'y',
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { labels: { color: this.theme.muted, font: { size: 11 } } },
        tooltip: this.tooltipBase,
      },
      scales: {
        x: { ...this.axisStyle, stacked: true, ticks: { ...this.axisStyle.ticks, precision: 0 } },
        y: { ...this.axisStyle, stacked: true },
      },
    };

    // --- physical risk by hazard (horizontal bar) ---
    const hz = b.physical_by_hazard || [];
    this.physByHazardData = {
      labels: hz.map((r) => r.hazard),
      datasets: [
        {
          data: hz.map((r) => r.exposure),
          backgroundColor: hz.map((_, i) => (i === 0 ? this.theme.red : `rgba(200,223,48,${Math.max(0.25, 0.78 - i * 0.1)})`)),
          borderRadius: 4,
        },
      ],
    };
    this.physByHazardOptions = {
      indexAxis: 'y',
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { display: false },
        tooltip: {
          ...this.tooltipBase,
          callbacks: {
            label: (ctx: any) => {
              const row = hz[ctx.dataIndex];
              return ` €${row.exposure.toFixed(0)}M · ${row.count} counterparties · ${row.high} high-risk`;
            },
          },
        },
      },
      scales: { x: this.axisStyle, y: this.axisStyle },
    };

    // --- scenario revenue at risk by horizon ---
    const sc = b.scenarios || [];
    const scenarioTypes = Array.from(new Set(sc.flatMap((r) => Object.keys(r).filter((k) => k !== 'horizon'))));
    const scenarioColors: Record<string, string> = {
      orderly: this.theme.green,
      disorderly: this.theme.amber,
      hot_house: this.theme.red,
    };
    this.scenariosData = {
      labels: sc.map((r) => r['horizon']),
      datasets: scenarioTypes.map((key) => ({
        label: key.replace('_', ' '),
        data: sc.map((r) => r[key] ?? null),
        backgroundColor: scenarioColors[key] || this.theme.grey,
      })),
    };
    this.scenariosOptions = {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { labels: { color: this.theme.muted, font: { size: 11 } } },
        tooltip: { ...this.tooltipBase, callbacks: { label: (ctx: any) => ` ${ctx.dataset.label}: €${ctx.parsed.y}M` } },
      },
      scales: { x: this.axisStyle, y: this.axisStyle },
    };

    // --- data quality donut ---
    const dq = b.data_quality_summary;
    if (dq?.audited_report_pct != null) {
      this.dataQualityPieData = {
        labels: ['Audited report', 'CDP disclosure', 'Estimated / economic', 'Proxy model'],
        datasets: [
          {
            data: [dq.audited_report_pct, dq.cdp_disclosure_pct, dq.estimated_economic_pct, dq.proxy_model_pct],
            backgroundColor: [this.theme.green, this.theme.accent, this.theme.synth, 'rgba(110,118,129,0.55)'],
            borderColor: '#161819',
            borderWidth: 3,
          },
        ],
      };
      this.dataQualityPieOptions = {
        responsive: true,
        maintainAspectRatio: false,
        cutout: '55%',
        plugins: {
          legend: { position: 'bottom', labels: { color: this.theme.muted, font: { size: 10.5 } } },
          tooltip: { ...this.tooltipBase, callbacks: { label: (ctx: any) => ` ${ctx.label}: ${ctx.parsed}%` } },
        },
      };
    }

    // --- peer benchmark (synthetic) ---
    const pb = b.peer_benchmark;
    if (pb) {
      const rows = [pb.bank_own, ...pb.peers, pb.sector_average];
      this.peerBenchmarkData = {
        labels: rows.map((r) => r.peer_name.replace(' (large universal)', '').replace(' (bank)', '')),
        datasets: [
          {
            label: 'Carbon intensity (t/M€)',
            data: rows.map((r) => r.carbon_intensity_tco2e_per_meur),
            backgroundColor: rows.map((r) => (r.is_synthetic ? 'rgba(110,118,129,0.55)' : this.theme.accent)),
            borderRadius: 4,
          },
        ],
      };
      this.peerBenchmarkOptions = {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: { display: false },
          tooltip: {
            ...this.tooltipBase,
            callbacks: {
              label: (ctx: any) => {
                const row = rows[ctx.dataIndex];
                return ` ${row.carbon_intensity_tco2e_per_meur} t/M€${row.is_synthetic ? ' (synthetic)' : ''}`;
              },
            },
          },
        },
        scales: { x: this.axisStyle, y: this.axisStyle },
      };
    }

    // --- scenario sensitivity band ---
    const sens = b.scenario_sensitivity || [];
    if (sens.length) {
      this.sensitivityData = {
        labels: sens.map((r) => r.horizon),
        datasets: [
          { label: 'High', data: sens.map((r) => r.high), borderColor: this.theme.synth, borderDash: [3, 3], pointRadius: 0, fill: false, tension: 0.3 },
          { label: 'Point estimate', data: sens.map((r) => r.mid), borderColor: this.theme.amber, pointBackgroundColor: '#0e1012', pointBorderColor: this.theme.amber, pointBorderWidth: 2, pointRadius: 3, fill: false, tension: 0.3 },
          { label: 'Low', data: sens.map((r) => r.low), borderColor: this.theme.synth, borderDash: [3, 3], pointRadius: 0, fill: false, tension: 0.3 },
        ],
      };
      this.sensitivityOptions = {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: { labels: { color: this.theme.muted, font: { size: 11 } } },
          tooltip: { ...this.tooltipBase, callbacks: { label: (ctx: any) => ` ${ctx.dataset.label}: €${ctx.parsed.y}M` } },
        },
        scales: { x: this.axisStyle, y: this.axisStyle },
      };
    }
  }
}
