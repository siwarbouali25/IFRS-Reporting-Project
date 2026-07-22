import {
  Component,
  OnInit,
} from '@angular/core';
import {
  CommonModule,
} from '@angular/common';
import {
  HttpErrorResponse,
} from '@angular/common/http';
import {
  ChartModule,
} from 'primeng/chart';

import {
  AssessmentResult,
  EvidenceItem,
  PayloadManifestSummary,
  ProcessedBundle,
  Risk as RiskService,
  RiskAnalysis as RiskAnalysisModel,
  RiskAnalysisSummary,
  RiskMatrixItem,
} from '../../core/services/risk';

type ViewState =
  | 'loading'
  | 'empty'
  | 'running'
  | 'ready'
  | 'error';

interface AssessmentSegment {
  text: string;
  evidenceId: string | null;
}

interface MatrixCell {
  likelihood: number;
  severity: number;
  score: number;
  level:
    | 'low'
    | 'medium'
    | 'high'
    | 'critical';
  items: RiskMatrixItem[];
}

@Component({
  selector: 'app-risk-analysis',
  imports: [
    CommonModule,
    ChartModule,
  ],
  templateUrl: './risk-analysis.html',
  styleUrl: './risk-analysis.css',
})
export class RiskAnalysis
  implements OnInit {
  readonly Math = Math;
  state: ViewState = 'loading';
  errorMessage = '';

  manifests:
    PayloadManifestSummary[] = [];
  selectedManifest:
    PayloadManifestSummary | null = null;

  analyses:
    RiskAnalysisSummary[] = [];
  analysis:
    RiskAnalysisModel | null = null;
  bundle: ProcessedBundle | null = null;

  assessmentLoading = false;
  assessment:
    AssessmentResult | null = null;
  hoveredEvidenceId:
    string | null = null;

  private evidenceMap:
    Record<string, EvidenceItem> = {};

  intensityChartData: any = null;
  intensityChartOptions: any = null;
  financedCompositionData: any = null;
  financedCompositionOptions: any = null;
  riskByCategoryData: any = null;
  riskByCategoryOptions: any = null;
  physicalByHazardData: any = null;
  physicalByHazardOptions: any = null;
  scenariosData: any = null;
  scenariosOptions: any = null;
  dataQualityPieData: any = null;
  dataQualityPieOptions: any = null;

  private readonly theme = {
    acid: '#d6f000',
    blue: '#4d9fff',
    blueLight: '#9ec7ff',
    red: '#d97070',
    amber: '#c9a24e',
    green: '#a8c93e',
    grey: '#7e8a92',
    muted: '#8a929b',
    mutedSoft: '#5e666e',
    surfaceSoft: '#1c1e20',
    border: '#272b2f',
  };

  private readonly axisStyle = {
    ticks: {
      color: this.theme.mutedSoft,
      font: {
        size: 11,
        family:
          'Inter, system-ui, sans-serif',
      },
    },
    grid: {
      color:
        'rgba(255,255,255,0.045)',
    },
  };

  private readonly tooltipBase = {
    backgroundColor:
      this.theme.surfaceSoft,
    borderColor: this.theme.border,
    borderWidth: 1,
    titleColor: '#eceef0',
    bodyColor: this.theme.muted,
    padding: 10,
  };

  constructor(
    private riskService: RiskService
  ) {}

  ngOnInit(): void {
    this.loadPage();
  }

  get recentAnalyses():
    RiskAnalysisSummary[] {
    return this.analyses.slice(0, 3);
  }

  get canRunAnalysis(): boolean {
    return (
      this.selectedManifest !== null &&
      this.state !== 'running'
    );
  }

  get institutionName(): string {
    return (
      this.bundle?.bank.bank_name ??
      this.analysis?.bank_name ??
      this.selectedManifest?.bank_name ??
      'Reporting institution'
    );
  }

  get reportingYear():
    number | string {
    return (
      this.bundle?.metadata.reporting_year ??
      this.analysis?.reporting_year ??
      this.selectedManifest
        ?.reporting_year ??
      '—'
    );
  }

  get assessmentSegments():
    AssessmentSegment[] {
    if (!this.assessment) {
      return [];
    }

    const parts =
      this.assessment.assessment_text
        .split(/(\[E\d+\])/g);

    return parts.map((part) => {
      const match = part.match(
        /^\[(E\d+)\]$/
      );

      if (
        match &&
        this.evidenceMap[match[1]]
      ) {
        return {
          text: match[1],
          evidenceId: match[1],
        };
      }

      return {
        text: part,
        evidenceId: null,
      };
    });
  }

  get citedEvidence():
    EvidenceItem[] {
    if (!this.assessment) {
      return [];
    }

    const sourceEvidence =
      this.assessment.evidence?.length
        ? this.assessment.evidence
        : (
            this.bundle?.evidence ??
            []
          );

    const evidenceById =
      Object.fromEntries(
        sourceEvidence.map(
          (item) => [
            item.id,
            item,
          ]
        )
      ) as Record<
        string,
        EvidenceItem
      >;

    const orderedIds: string[] = [];
    const seen = new Set<string>();

    for (
      const match of
        this.assessment
          .assessment_text
          .matchAll(/\[(E\d+)\]/g)
    ) {
      const evidenceId = match[1];

      if (
        seen.has(evidenceId) ||
        !evidenceById[evidenceId]
      ) {
        continue;
      }

      seen.add(evidenceId);
      orderedIds.push(evidenceId);
    }

    return orderedIds.map(
      (evidenceId) =>
        evidenceById[evidenceId]
    );
  }

  get riskMatrixCells():
    MatrixCell[] {
    const items =
      this.bundle?.risk_matrix ?? [];
    const cells: MatrixCell[] = [];

    for (
      let severity = 5;
      severity >= 1;
      severity -= 1
    ) {
      for (
        let likelihood = 1;
        likelihood <= 5;
        likelihood += 1
      ) {
        const score =
          likelihood * severity;

        cells.push({
          likelihood,
          severity,
          score,
          level:
            this.getMatrixLevel(
              score
            ),
          items: items.filter(
            (item) =>
              item.x === likelihood &&
              item.y === severity
          ),
        });
      }
    }

    return cells;
  }

  get matrixHasData(): boolean {
    return (
      (this.bundle?.risk_matrix.length ??
        0) > 0
    );
  }

  loadPage(): void {
    this.state = 'loading';
    this.errorMessage = '';

    this.riskService
      .getPayloadManifests()
      .subscribe({
        next: (manifests) => {
          this.manifests =
            [...manifests].sort(
              (a, b) =>
                new Date(
                  b.created_at
                ).getTime() -
                new Date(
                  a.created_at
                ).getTime()
            );

          if (
            this.manifests.length === 0
          ) {
            this.state = 'empty';
            return;
          }

          const storedId = Number(
            localStorage.getItem(
              'activePayloadManifestId'
            )
          );

          this.selectedManifest =
            this.manifests.find(
              (manifest) =>
                manifest.id === storedId
            ) ??
            this.manifests[0];

          this.loadAnalysisHistory(
            true
          );
        },
        error: (
          error: HttpErrorResponse
        ) => {
          this.state = 'error';
          this.errorMessage =
            this.getErrorMessage(error);
        },
      });
  }

  selectManifest(
    manifest: PayloadManifestSummary
  ): void {
    if (
      this.state === 'running'
    ) {
      return;
    }

    this.selectedManifest = manifest;
    this.analysis = null;
    this.bundle = null;
    this.assessment = null;
    this.evidenceMap = {};
    this.resetCharts();

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

    this.loadAnalysisHistory(
      true
    );
  }

  runAnalysis(
    force = false
  ): void {
    if (
      !this.selectedManifest ||
      !this.canRunAnalysis
    ) {
      return;
    }

    this.state = 'running';
    this.errorMessage = '';
    this.analysis = null;
    this.bundle = null;
    this.assessment = null;
    this.evidenceMap = {};
    this.resetCharts();

    this.riskService
      .startAnalysis(
        this.selectedManifest.id,
        force
      )
      .subscribe({
        next: (analysis) => {
          this.handleAnalysisReady(
            analysis
          );
          this.loadAnalysisHistory(
            false
          );
        },
        error: (
          error: HttpErrorResponse
        ) => {
          this.state = 'error';
          this.errorMessage =
            this.getErrorMessage(error);
        },
      });
  }

  selectAnalysis(
    item: RiskAnalysisSummary
  ): void {
    if (
      this.state === 'running'
    ) {
      return;
    }

    this.state = 'loading';
    this.errorMessage = '';

    this.riskService
      .get(item.id)
      .subscribe({
        next: (analysis) =>
          this.handleAnalysisReady(
            analysis
          ),
        error: (
          error: HttpErrorResponse
        ) => {
          this.state = 'error';
          this.errorMessage =
            this.getErrorMessage(error);
        },
      });
  }

  regenerateAssessment(): void {
    if (!this.analysis) {
      return;
    }

    this.assessment = null;
    this.assessmentLoading = true;

    this.riskService
      .generateAssessment(
        this.analysis.id
      )
      .subscribe({
        next: (result) => {
          this.assessment = result;
          this.assessmentLoading =
            false;
        },
        error: () => {
          this.assessmentLoading =
            false;
          this.assessment = null;
        },
      });
  }

  evidenceFor(
    id: string | null
  ): EvidenceItem | null {
    if (!id) {
      return null;
    }

    return (
      this.evidenceMap[id] ??
      null
    );
  }

  formatStatus(
    status:
      | string
      | null
      | undefined
  ): string {
    if (!status) {
      return 'Not started';
    }

    return status
      .replaceAll('_', ' ')
      .replace(
        /\b\w/g,
        (character) =>
          character.toUpperCase()
      );
  }

  getStatusClass(
    status:
      | string
      | null
      | undefined
  ): string {
    if (status === 'ready') {
      return 'success';
    }

    if (status === 'failed') {
      return 'error';
    }

    return 'running';
  }

  getMatrixCellTitle(
    cell: MatrixCell
  ): string {
    if (
      cell.items.length === 0
    ) {
      return (
        `Likelihood ${cell.likelihood}, ` +
        `severity ${cell.severity}: ` +
        'no risks'
      );
    }

    return cell.items
      .map(
        (item) =>
          `${item.name} ` +
          `(${item.rating})`
      )
      .join(' · ');
  }

  trackManifest(
    _index: number,
    manifest: PayloadManifestSummary
  ): number {
    return manifest.id;
  }

  trackAnalysis(
    _index: number,
    analysis: RiskAnalysisSummary
  ): string {
    return analysis.id;
  }

  trackEvidence(
    _index: number,
    evidence: EvidenceItem
  ): string {
    return evidence.id;
  }

  private loadAnalysisHistory(
    loadLatest: boolean
  ): void {
    const manifestId =
      this.selectedManifest?.id;

    if (!manifestId) {
      this.state = 'empty';
      return;
    }

    this.riskService
      .list(manifestId)
      .subscribe({
        next: (analyses) => {
          this.analyses =
            [...analyses].sort(
              (a, b) =>
                new Date(
                  b.created_at
                ).getTime() -
                new Date(
                  a.created_at
                ).getTime()
            );

          if (
            loadLatest &&
            this.analyses.length > 0
          ) {
            this.selectAnalysis(
              this.analyses[0]
            );
            return;
          }

          if (
            loadLatest &&
            this.analyses.length === 0
          ) {
            this.state = 'empty';
          }
        },
        error: (
          error: HttpErrorResponse
        ) => {
          this.state = 'error';
          this.errorMessage =
            this.getErrorMessage(error);
        },
      });
  }

  private handleAnalysisReady(
    analysis: RiskAnalysisModel
  ): void {
    this.analysis = analysis;

    if (
      analysis.status === 'failed'
    ) {
      this.state = 'error';
      this.errorMessage =
        analysis.error_message ||
        (
          'The prepared information could ' +
          'not be analysed.'
        );
      return;
    }

    if (!analysis.processed) {
      this.state = 'error';
      this.errorMessage =
        'The analysis result is empty.';
      return;
    }

    this.bundle =
      analysis.processed;
    this.evidenceMap =
      Object.fromEntries(
        this.bundle.evidence.map(
          (item) => [
            item.id,
            item,
          ]
        )
      );

    this.state = 'ready';
    this.buildChartConfigs();
    this.loadLatestAssessment();
  }

  private loadLatestAssessment():
    void {
    if (!this.analysis) {
      return;
    }

    this.assessmentLoading = true;
    this.assessment = null;

    this.riskService
      .getLatestAssessment(
        this.analysis.id
      )
      .subscribe({
        next: (result) => {
          this.assessment = result;
          this.assessmentLoading =
            false;
        },
        error: (
          error: HttpErrorResponse
        ) => {
          if (error.status === 404) {
            this.regenerateAssessment();
            return;
          }

          this.assessmentLoading =
            false;
        },
      });
  }

  private getMatrixLevel(
    score: number
  ):
    | 'low'
    | 'medium'
    | 'high'
    | 'critical' {
    if (score >= 15) {
      return 'critical';
    }

    if (score >= 8) {
      return 'high';
    }

    if (score >= 3) {
      return 'medium';
    }

    return 'low';
  }

  private resetCharts(): void {
    this.intensityChartData = null;
    this.intensityChartOptions =
      null;
    this.financedCompositionData =
      null;
    this.financedCompositionOptions =
      null;
    this.riskByCategoryData = null;
    this.riskByCategoryOptions =
      null;
    this.physicalByHazardData =
      null;
    this.physicalByHazardOptions =
      null;
    this.scenariosData = null;
    this.scenariosOptions = null;
    this.dataQualityPieData = null;
    this.dataQualityPieOptions =
      null;
  }

  private buildChartConfigs(): void {
    this.resetCharts();

    const bundle = this.bundle;

    if (!bundle) {
      return;
    }

    this.buildIntensityChart(
      bundle
    );
    this.buildFinancedChart(
      bundle
    );
    this.buildRiskCategoryChart(
      bundle
    );
    this.buildPhysicalChart(
      bundle
    );
    this.buildScenarioChart(
      bundle
    );
    this.buildDataQualityChart(
      bundle
    );
  }

  private buildIntensityChart(
    bundle: ProcessedBundle
  ): void {
    if (
      bundle.intensity_trend.length ===
      0
    ) {
      return;
    }

    this.intensityChartData = {
      labels:
        bundle.intensity_trend.map(
          (row) => row.year
        ),
      datasets: [
        {
          label: 'Actual',
          data:
            bundle.intensity_trend.map(
              (row) => row.actual
            ),
          borderColor:
            this.theme.acid,
          backgroundColor:
            'rgba(214,240,0,0.08)',
          pointBackgroundColor:
            '#0e1012',
          pointBorderColor:
            this.theme.acid,
          pointBorderWidth: 2,
          pointRadius: 3,
          tension: 0.3,
          fill: true,
          spanGaps: true,
        },
        {
          label: 'Target',
          data:
            bundle.intensity_trend.map(
              (row) => row.target
            ),
          borderColor:
            this.theme.blue,
          borderDash: [5, 4],
          pointBackgroundColor:
            '#0e1012',
          pointBorderColor:
            this.theme.blue,
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
        legend: {
          labels: {
            color:
              this.theme.muted,
            font: {
              size: 11,
            },
          },
        },
        tooltip: {
          ...this.tooltipBase,
          callbacks: {
            label: (context: any) =>
              (
                ` ${context.dataset.label}: ` +
                `${context.parsed.y ?? '—'} t/M€`
              ),
          },
        },
      },
      scales: {
        x: this.axisStyle,
        y: this.axisStyle,
      },
    };
  }

  private buildFinancedChart(
    bundle: ProcessedBundle
  ): void {
    const rows =
      bundle.financed_composition;

    if (rows.length === 0) {
      return;
    }

    this.financedCompositionData = {
      labels: rows.map(
        (row) => row.name
      ),
      datasets: [
        {
          data: rows.map(
            (row) => row.value
          ),
          backgroundColor:
            rows.map(
              (row, index) =>
                row.proxy
                  ? (
                      'rgba(77,159,255,0.45)'
                    )
                  : [
                      this.theme.acid,
                      this.theme.grey,
                      this.theme.blue,
                      this.theme.green,
                      this.theme.amber,
                    ][index % 5]
            ),
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
        legend: {
          position: 'bottom',
          labels: {
            color:
              this.theme.muted,
            font: {
              size: 10.5,
            },
          },
        },
        tooltip: {
          ...this.tooltipBase,
          callbacks: {
            label: (context: any) => {
              const row =
                rows[
                  context.dataIndex
                ];
              const value =
                (
                  context.parsed /
                  1_000_000
                ).toFixed(2);

              return (
                ` ${row.name}: ` +
                `${value} Mt CO₂e` +
                (
                  row.proxy
                    ? ' (proxy)'
                    : ''
                )
              );
            },
          },
        },
      },
    };
  }

  private buildRiskCategoryChart(
    bundle: ProcessedBundle
  ): void {
    const rows =
      bundle.risk_by_category;

    if (rows.length === 0) {
      return;
    }

    const excludedKeys = new Set(
      ['name', 'total']
    );
    const ratingKeys =
      Array.from(
        new Set(
          rows.flatMap(
            (row) =>
              Object.keys(row)
                .filter(
                  (key) =>
                    !excludedKeys.has(
                      key
                    )
                )
          )
        )
      );

    const colors:
      Record<string, string> = {
        critical: this.theme.red,
        high: '#e08a4e',
        medium: this.theme.amber,
        low: this.theme.green,
        unrated: this.theme.grey,
      };

    this.riskByCategoryData = {
      labels: rows.map(
        (row) => row['name']
      ),
      datasets:
        ratingKeys.map(
          (key) => ({
            label:
              this.formatStatus(key),
            data: rows.map(
              (row) =>
                row[key] ?? 0
            ),
            backgroundColor:
              colors[key] ??
              this.theme.grey,
            stack: 'risk',
          })
        ),
    };

    this.riskByCategoryOptions = {
      indexAxis: 'y',
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: {
          labels: {
            color:
              this.theme.muted,
            font: {
              size: 11,
            },
          },
        },
        tooltip:
          this.tooltipBase,
      },
      scales: {
        x: {
          ...this.axisStyle,
          stacked: true,
          ticks: {
            ...this.axisStyle
              .ticks,
            precision: 0,
          },
        },
        y: {
          ...this.axisStyle,
          stacked: true,
        },
      },
    };
  }

  private buildPhysicalChart(
    bundle: ProcessedBundle
  ): void {
    const rows =
      bundle.physical_by_hazard;

    if (rows.length === 0) {
      return;
    }

    this.physicalByHazardData = {
      labels: rows.map(
        (row) => row.hazard
      ),
      datasets: [
        {
          data: rows.map(
            (row) => row.exposure
          ),
          backgroundColor:
            rows.map(
              (_row, index) =>
                index === 0
                  ? this.theme.red
                  : (
                      `rgba(77,159,255,` +
                      `${Math.max(
                        0.25,
                        0.78 -
                          index * 0.1
                      )})`
                    )
            ),
          borderRadius: 4,
        },
      ],
    };

    this.physicalByHazardOptions = {
      indexAxis: 'y',
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: {
          display: false,
        },
        tooltip: {
          ...this.tooltipBase,
          callbacks: {
            label: (context: any) => {
              const row =
                rows[
                  context.dataIndex
                ];

              return (
                ` €${row.exposure.toFixed(
                  0
                )}M · ` +
                `${row.count} exposure rows · ` +
                `${row.high} high-risk`
              );
            },
          },
        },
      },
      scales: {
        x: this.axisStyle,
        y: this.axisStyle,
      },
    };
  }

  private buildScenarioChart(
    bundle: ProcessedBundle
  ): void {
    const rows =
      bundle.scenarios;

    if (rows.length === 0) {
      return;
    }

    const scenarioTypes =
      Array.from(
        new Set(
          rows.flatMap(
            (row) =>
              Object.keys(row)
                .filter(
                  (key) =>
                    key !==
                    'horizon'
                )
          )
        )
      );

    const palette = [
      this.theme.green,
      this.theme.amber,
      this.theme.red,
      this.theme.blue,
      this.theme.grey,
    ];

    this.scenariosData = {
      labels: rows.map(
        (row) =>
          row['horizon']
      ),
      datasets:
        scenarioTypes.map(
          (key, index) => ({
            label:
              this.formatStatus(key),
            data: rows.map(
              (row) =>
                row[key] ?? null
            ),
            backgroundColor:
              palette[
                index %
                  palette.length
              ],
          })
        ),
    };

    this.scenariosOptions = {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: {
          labels: {
            color:
              this.theme.muted,
            font: {
              size: 11,
            },
          },
        },
        tooltip: {
          ...this.tooltipBase,
          callbacks: {
            label: (context: any) =>
              (
                ` ${context.dataset.label}: ` +
                `€${context.parsed.y}M`
              ),
          },
        },
      },
      scales: {
        x: this.axisStyle,
        y: this.axisStyle,
      },
    };
  }

  private buildDataQualityChart(
    bundle: ProcessedBundle
  ): void {
    const summary =
      bundle.data_quality_summary;

    const values = [
      summary.audited_report_pct,
      summary.cdp_disclosure_pct,
      summary.estimated_economic_pct,
      summary.proxy_model_pct,
    ];

    if (
      values.every(
        (value) =>
          value === null ||
          value === undefined
      )
    ) {
      return;
    }

    this.dataQualityPieData = {
      labels: [
        'Audited report',
        'CDP disclosure',
        'Estimated / economic',
        'Proxy model',
      ],
      datasets: [
        {
          data: values.map(
            (value) =>
              value ?? 0
          ),
          backgroundColor: [
            this.theme.green,
            this.theme.acid,
            this.theme.blue,
            'rgba(77,159,255,0.45)',
          ],
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
        legend: {
          position: 'bottom',
          labels: {
            color:
              this.theme.muted,
            font: {
              size: 10.5,
            },
          },
        },
        tooltip: {
          ...this.tooltipBase,
          callbacks: {
            label: (context: any) =>
              (
                ` ${context.label}: ` +
                `${context.parsed}%`
              ),
          },
        },
      },
    };
  }

  private getErrorMessage(
    error: HttpErrorResponse
  ): string {
    if (error.status === 401) {
      return (
        'Your session has expired. ' +
        'Please log in again.'
      );
    }

    if (error.status === 0) {
      return (
        'The server could not be reached.'
      );
    }

    const fieldError =
      error.error
        ?.payload_manifest_id;

    if (
      Array.isArray(fieldError)
    ) {
      return (
        fieldError[0] ??
        'The prepared dataset is unavailable.'
      );
    }

    return (
      error.error?.error_message ??
      error.error?.detail ??
      error.error?.message ??
      (
        'Risk analysis could not be ' +
        'completed.'
      )
    );
  }
}
