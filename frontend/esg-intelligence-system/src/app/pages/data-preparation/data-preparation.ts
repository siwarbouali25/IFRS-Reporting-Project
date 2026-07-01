import { Component } from '@angular/core';
import { CommonModule } from '@angular/common';
import { RouterLink } from '@angular/router';

@Component({
  selector: 'app-data-preparation',
  imports: [CommonModule, RouterLink],
  templateUrl: './data-preparation.html',
  styleUrl: './data-preparation.css',
})
export class DataPreparation {
  overview = [
    { label: 'Prepared Datasets', value: '8', icon: 'pi pi-database' },
    { label: 'Ready for Reporting', value: '8', icon: 'pi pi-check-circle' },
    { label: 'Calculated Metrics', value: '127', icon: 'pi pi-chart-line' },
    { label: 'Data Quality Score', value: '96%', icon: 'pi pi-shield' }
  ];

  domains = [
    { name: 'Governance & Strategy', icon: 'pi pi-building', metrics: 31, quality: '98%', updated: 'Today' },
    { name: 'Climate Risks & Opportunities', icon: 'pi pi-globe', metrics: 42, quality: '95%', updated: 'Today' },
    { name: 'Carbon & Emissions', icon: 'pi pi-sync', metrics: 18, quality: '94%', updated: 'Today' },
    { name: 'Operations & Energy', icon: 'pi pi-bolt', metrics: 14, quality: '96%', updated: 'Today' },
    { name: 'Financial Exposure', icon: 'pi pi-chart-bar', metrics: 12, quality: '97%', updated: 'Today' },
    { name: 'Workforce', icon: 'pi pi-users', metrics: 10, quality: '99%', updated: 'Today' }
  ];

  indicators = [
    'Governance disclosure metrics prepared',
    'Climate risk indicators calculated',
    'Carbon exposure metrics generated',
    'Financial exposure data normalized',
    'Prepared datasets ready for IFRS S1/S2 generation'
  ];
}
