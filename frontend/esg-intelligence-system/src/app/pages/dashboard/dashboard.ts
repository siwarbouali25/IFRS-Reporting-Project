import { Component } from '@angular/core';
import { CommonModule } from '@angular/common';
import { ChartModule } from 'primeng/chart';

@Component({
  selector: 'app-dashboard',
  imports: [CommonModule, ChartModule],
  templateUrl: './dashboard.html',
  styleUrl: './dashboard.css'
})
export class DashboardComponent {
  currentPhase = 3;

  kpis = [
    {
      title: 'Scope 1 + 2 emissions',
      value: '4,820',
      suffix: null,
      change: '+2.1% vs last year',
      deltaClass: 'down'
    },
    {
      title: 'KPIs collected',
      value: '84',
      suffix: '/ 100',
      change: '16 still pending',
      deltaClass: 'flat'
    },
    {
      title: 'Open risks',
      value: '9',
      suffix: null,
      change: '2 escalated this week',
      deltaClass: 'down'
    },
    {
      title: 'Disclosures ready',
      value: '6',
      suffix: '/ 8',
      change: '75% complete',
      deltaClass: 'up'
    }
  ];

  risks = [
    {
      name: 'Climate transition risk',
      level: 'High',
      status: 'Needs review'
    },
    {
      name: 'Data quality risk',
      level: 'Medium',
      status: 'In progress'
    },
    {
      name: 'Governance disclosure gap',
      level: 'Low',
      status: 'Controlled'
    }
  ];

  activities = [
    {
      text: 'ESG_metrics_2024.csv uploaded to the workspace',
      time: '09:24'
    },
    {
      text: 'Emirates dataset passed preparation checks',
      time: '10:12'
    },
    {
      text: 'IFRS S2 climate section generated',
      time: '11:35'
    },
    {
      text: 'Draft report sent for expert review',
      time: '14:08'
    }
  ];

  private axisStyle = {
    ticks: {
      color: '#737b84',
      font: {
        size: 11,
        family: 'Inter, system-ui, sans-serif'
      }
    },
    grid: {
      color: 'rgba(255,255,255,0.045)'
    }
  };

  carbonData = {
    labels: ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun'],
    datasets: [
      {
        label: 'tCO₂e',
        data: [42, 39, 36, 34, 31, 28],
        tension: 0.35,
        borderColor: '#c8df30',
        borderWidth: 2,
        pointBackgroundColor: '#0e1012',
        pointBorderColor: '#c8df30',
        pointBorderWidth: 2,
        pointRadius: 3,
        pointHoverRadius: 5,
        backgroundColor: 'rgba(200, 223, 48, 0.08)',
        fill: true
      }
    ]
  };

  carbonOptions = {
    responsive: true,
    maintainAspectRatio: false,
    plugins: {
      legend: {
        display: false
      },
      tooltip: {
        backgroundColor: '#1c1e20',
        borderColor: '#272b2f',
        borderWidth: 1,
        titleColor: '#eceef0',
        bodyColor: '#9da5ad',
        padding: 10,
        callbacks: {
          label: (ctx: any) => ` ${ctx.parsed.y} tCO₂e`
        }
      }
    },
    scales: {
      x: this.axisStyle,
      y: {
        ...this.axisStyle,
        ticks: {
          ...this.axisStyle.ticks,
          callback: (value: any) => `${value}t`
        }
      }
    }
  };

  kpiData = {
    labels: ['Environment', 'Social', 'Governance', 'Climate'],
    datasets: [
      {
        label: 'Completion',
        data: [78, 64, 82, 55],
        backgroundColor: [
          'rgba(200, 223, 48, 0.75)',
          'rgba(120, 142, 150, 0.65)',
          'rgba(200, 223, 48, 0.72)',
          'rgba(120, 142, 150, 0.62)'
        ],
        hoverBackgroundColor: [
          '#c8df30',
          '#8a929b',
          '#c8df30',
          '#8a929b'
        ],
        borderRadius: 6,
        borderSkipped: false
      }
    ]
  };

  kpiOptions = {
    responsive: true,
    maintainAspectRatio: false,
    plugins: {
      legend: {
        display: false
      },
      tooltip: {
        backgroundColor: '#1c1e20',
        borderColor: '#272b2f',
        borderWidth: 1,
        titleColor: '#eceef0',
        bodyColor: '#9da5ad',
        padding: 10,
        callbacks: {
          label: (ctx: any) => ` ${ctx.parsed.y}% complete`
        }
      }
    },
    scales: {
      x: {
        ...this.axisStyle,
        grid: {
          display: false
        }
      },
      y: {
        ...this.axisStyle,
        min: 0,
        max: 100,
        ticks: {
          ...this.axisStyle.ticks,
          callback: (value: any) => `${value}%`
        }
      }
    }
  };

  riskData = {
    labels: ['High', 'Medium', 'Low'],
    datasets: [
      {
        data: [3, 6, 9],
        backgroundColor: [
          'rgba(217, 112, 112, 0.85)',
          'rgba(201, 162, 78, 0.85)',
          'rgba(138, 146, 155, 0.55)'
        ],
        hoverBackgroundColor: [
          '#d97070',
          '#c9a24e',
          '#8a929b'
        ],
        borderColor: '#161819',
        borderWidth: 4,
        hoverOffset: 4
      }
    ]
  };

  riskOptions = {
    responsive: true,
    maintainAspectRatio: false,
    cutout: '72%',
    plugins: {
      legend: {
        display: false
      },
      tooltip: {
        backgroundColor: '#1c1e20',
        borderColor: '#272b2f',
        borderWidth: 1,
        titleColor: '#eceef0',
        bodyColor: '#9da5ad',
        padding: 10,
        callbacks: {
          label: (ctx: any) => ` ${ctx.label}: ${ctx.parsed} risks`
        }
      }
    }
  };
}