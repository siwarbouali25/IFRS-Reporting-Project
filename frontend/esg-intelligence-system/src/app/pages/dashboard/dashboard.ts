import { Component, OnInit, inject } from '@angular/core';
import { CommonModule } from '@angular/common';
import { ChartModule } from 'primeng/chart';
import { finalize } from 'rxjs';

import {
  BasicChartData,
  DashboardCharts,
  GovernanceTile,
  KpiDashboardResponse,
  KpiDashboardService,
  MethodologyNote,
  MiniKpi,
  RiskMatrixCell,
} from '../../core/services/kpi-dashboard';

@Component({
  selector: 'app-dashboard',
  imports: [CommonModule, ChartModule],
  templateUrl: './dashboard.html',
  styleUrl: './dashboard.css',
})
export class DashboardComponent implements OnInit {
  private readonly kpiDashboardService = inject(KpiDashboardService);

  batchId = 'a0a4d84f-6e3a-4905-b249-9acec68b1993';
  bankId = 'BANK01';
  reportingYear = 2024;

  loading = false;
  errorMessage = '';

  dashboard: KpiDashboardResponse | null = null;

  miniKpis: MiniKpi[] = [];
  riskMatrixCells: RiskMatrixCell[] = [];
  governanceTiles: GovernanceTile[] = [];
  methodologyNotes: MethodologyNote[] = [];

  footprintFinancedPct = '—';
  footprintOperationsPct = '—';
  footprintOperations = '—';

  operationsTrendData: any = { labels: [], datasets: [] };
  financedTrendData: any = { labels: [], datasets: [] };
  scope3CategoryData: any = { labels: [], datasets: [] };
  dataQualityData: any = { labels: [], datasets: [] };
  scenarioData: any = { labels: [], datasets: [] };
  physicalHazardData: any = { labels: [], datasets: [] };
  countryExposureData: any = { labels: [], datasets: [] };
  opportunitiesData: any = { labels: [], datasets: [] };
  investmentEmissionsData: any = { labels: [], datasets: [] };

private readonly palette = [
  'rgba(200, 223, 48, 0.82)',
  'rgba(79, 143, 191, 0.70)',
  'rgba(168, 201, 62, 0.62)',
  'rgba(138, 146, 155, 0.55)',
  'rgba(201, 162, 78, 0.65)',
  'rgba(217, 112, 112, 0.62)',
  'rgba(79, 143, 191, 0.46)',
  'rgba(200, 223, 48, 0.48)',
];

private readonly borderPalette = [
  '#c8df30',
  '#4f8fbf',
  '#a8c93e',
  '#8a929b',
  '#c9a24e',
  '#d97070',
  '#4f8fbf',
  '#c8df30',
];

  private readonly axisStyle = {
    ticks: {
      color: '#737b84',
      font: {
        size: 11,
        family: 'Aptos, Segoe UI, Helvetica Neue, Arial, sans-serif',
      },
    },
    grid: {
      color: 'rgba(255,255,255,0.045)',
    },
  };

  mixedOperationsOptions: any = {
    responsive: true,
    maintainAspectRatio: false,
    interaction: {
      mode: 'index',
      intersect: false,
    },
    plugins: {
      legend: {
        labels: {
          color: '#8a929b',
          boxWidth: 10,
          boxHeight: 10,
          usePointStyle: true,
        },
      },
      tooltip: this.tooltipOptions('tCO₂e'),
    },
    scales: {
      x: {
        stacked: true,
        ...this.axisStyle,
        grid: {
          display: false,
        },
      },
      y: {
        stacked: true,
        ...this.axisStyle,
        ticks: {
          ...this.axisStyle.ticks,
          callback: (value: any) => this.formatLargeNumber(value),
        },
      },
    },
  };

  financedOptions: any = {
    responsive: true,
    maintainAspectRatio: false,
    interaction: {
      mode: 'index',
      intersect: false,
    },
    plugins: {
      legend: {
        labels: {
          color: '#8a929b',
          boxWidth: 10,
          boxHeight: 10,
          usePointStyle: true,
        },
      },
      tooltip: this.tooltipOptions(''),
    },
    scales: {
      x: {
        ...this.axisStyle,
        grid: {
          display: false,
        },
      },
      y: {
        type: 'linear',
        position: 'left',
        ...this.axisStyle,
        title: {
          display: true,
          text: 'Mt CO₂e',
          color: '#5e666e',
        },
      },
      y1: {
        type: 'linear',
        position: 'right',
        ...this.axisStyle,
        grid: {
          drawOnChartArea: false,
        },
        title: {
          display: true,
          text: 'tCO₂e / €m',
          color: '#5e666e',
        },
      },
    },
  };

  barOptions: any = {
    responsive: true,
    maintainAspectRatio: false,
    plugins: {
      legend: {
        display: false,
      },
      tooltip: this.tooltipOptions(''),
    },
    scales: {
      x: {
        ...this.axisStyle,
        grid: {
          display: false,
        },
      },
      y: {
        ...this.axisStyle,
        ticks: {
          ...this.axisStyle.ticks,
          callback: (value: any) => this.formatLargeNumber(value),
        },
      },
    },
  };

  horizontalBarOptions: any = {
    indexAxis: 'y',
    responsive: true,
    maintainAspectRatio: false,
    plugins: {
      legend: {
        display: false,
      },
      tooltip: this.tooltipOptions(''),
    },
    scales: {
      x: {
        ...this.axisStyle,
        ticks: {
          ...this.axisStyle.ticks,
          callback: (value: any) => this.formatLargeNumber(value),
        },
      },
      y: {
        ...this.axisStyle,
        grid: {
          display: false,
        },
      },
    },
  };

  percentBarOptions: any = {
    responsive: true,
    maintainAspectRatio: false,
    plugins: {
      legend: {
        labels: {
          color: '#8a929b',
          boxWidth: 10,
          boxHeight: 10,
          usePointStyle: true,
        },
      },
      tooltip: this.tooltipOptions('%'),
    },
    scales: {
      x: {
        ...this.axisStyle,
        grid: {
          display: false,
        },
      },
      y: {
        ...this.axisStyle,
        ticks: {
          ...this.axisStyle.ticks,
          callback: (value: any) => `${value}%`,
        },
      },
    },
  };

  doughnutOptions: any = {
    responsive: true,
    maintainAspectRatio: false,
    cutout: '68%',
    plugins: {
      legend: {
        position: 'bottom',
        labels: {
          color: '#8a929b',
          boxWidth: 10,
          boxHeight: 10,
          usePointStyle: true,
          padding: 14,
        },
      },
      tooltip: this.tooltipOptions('%'),
    },
  };

  ngOnInit(): void {
    this.loadDashboard();
  }

  loadDashboard(): void {
    this.loading = true;
    this.errorMessage = '';

    this.kpiDashboardService
      .getDashboard(this.batchId, this.bankId, this.reportingYear)
      .pipe(finalize(() => (this.loading = false)))
      .subscribe({
        next: (response) => {
          this.dashboard = response;
          this.bindCharts(response.charts);
        },
        error: (error) => {
          this.errorMessage =
            error?.error?.detail ||
            error?.error?.message ||
            error?.message ||
            'Unable to load KPI dashboard.';
        },
      });
  }

  formatScore(value: number | null | undefined): string {
    if (value === null || value === undefined) {
      return '—';
    }

    return Number(value).toFixed(2);
  }

  private bindCharts(charts: DashboardCharts): void {
    this.miniKpis = charts.mini_kpis || [];

    const financedPct = charts.materiality?.financed_emissions_pct;

    this.footprintFinancedPct = this.formatNumber(financedPct, 2);

    if (financedPct === null || financedPct === undefined) {
      this.footprintOperationsPct = '—';
    } else {
      this.footprintOperationsPct = Math.max(0, 100 - Number(financedPct)).toFixed(2);
    }

    this.footprintOperations = this.formatLargeNumber(
      Number(charts.materiality?.operations_emissions_tco2e || 0)
    );

    this.operationsTrendData = this.toPrimeChartData(
      charts.operations_trend,
      'operations'
    );

    this.financedTrendData = this.toPrimeChartData(
      charts.financed_emissions_trend,
      'financed'
    );

    this.scope3CategoryData = this.toPrimeChartData(
      charts.scope3_categories,
      'horizontal'
    );

    this.dataQualityData = this.toPrimeChartData(
      charts.data_quality,
      'doughnut'
    );

    this.scenarioData = this.toPrimeChartData(
      charts.scenario_analysis,
      'grouped'
    );

    this.physicalHazardData = this.toPrimeChartData(
      charts.physical_risk_by_hazard,
      'horizontal'
    );

    this.countryExposureData = this.toPrimeChartData(
      charts.country_exposure,
      'financed'
    );

    this.opportunitiesData = this.toPrimeChartData(
      charts.opportunities,
      'horizontal'
    );

    this.investmentEmissionsData = this.toPrimeChartData(
      charts.investment_emissions,
      'horizontal'
    );

    this.riskMatrixCells = charts.risk_matrix || [];
    this.governanceTiles = charts.governance_tiles || [];
    this.methodologyNotes = charts.methodology_notes || [];
  }

  private toPrimeChartData(
    chart: BasicChartData | undefined,
    mode: 'operations' | 'financed' | 'horizontal' | 'doughnut' | 'grouped'
  ): any {
    if (!chart) {
      return { labels: [], datasets: [] };
    }

    return {
      labels: chart.labels || [],
      datasets: (chart.datasets || []).map((dataset, index) => {
        const type = dataset.type || (mode === 'doughnut' ? undefined : 'bar');
        const isLine = type === 'line';

        return {
          ...dataset,
          type,
          yAxisID: dataset.y_axis_id || dataset.yAxisID,
          backgroundColor:
            mode === 'doughnut'
              ? this.palette
              : isLine
                ? this.borderPalette[index % this.borderPalette.length]
                : this.palette[index % this.palette.length],
          borderColor: isLine
            ? this.borderPalette[index % this.borderPalette.length]
            : '#161819',
          pointBackgroundColor: this.borderPalette[index % this.borderPalette.length],
          pointBorderColor: this.borderPalette[index % this.borderPalette.length],
          tension: isLine ? 0.35 : undefined,
          pointRadius: isLine ? 3 : undefined,
          pointHoverRadius: isLine ? 5 : undefined,
          borderRadius: isLine ? undefined : 6,
          borderSkipped: false,
          borderWidth: mode === 'doughnut' ? 4 : isLine ? 2 : 0,
          hoverOffset: mode === 'doughnut' ? 4 : undefined,
        };
      }),
    };
  }

  private tooltipOptions(unit: string): any {
    return {
      backgroundColor: '#1c1e20',
      borderColor: '#272b2f',
      borderWidth: 1,
      titleColor: '#eceef0',
      bodyColor: '#9da5ad',
      padding: 10,
      callbacks: {
        label: (ctx: any) => {
          const value =
            ctx.parsed?.y ??
            ctx.parsed?.x ??
            ctx.parsed ??
            0;

          const suffix = unit ? ` ${unit}` : '';
          return ` ${ctx.dataset?.label || ctx.label}: ${this.formatLargeNumber(value)}${suffix}`;
        },
      },
    };
  }

  private formatNumber(value: number | null | undefined, decimals = 2): string {
    if (value === null || value === undefined) {
      return '—';
    }

    return Number(value).toFixed(decimals);
  }

  private formatLargeNumber(value: number): string {
    const numericValue = Number(value);

    if (Number.isNaN(numericValue)) {
      return String(value);
    }

    if (Math.abs(numericValue) >= 1_000_000) {
      return `${(numericValue / 1_000_000).toFixed(1)}M`;
    }

    if (Math.abs(numericValue) >= 1_000) {
      return `${(numericValue / 1_000).toFixed(1)}K`;
    }

    if (Number.isInteger(numericValue)) {
      return numericValue.toString();
    }

    return numericValue.toFixed(2);
  }
}