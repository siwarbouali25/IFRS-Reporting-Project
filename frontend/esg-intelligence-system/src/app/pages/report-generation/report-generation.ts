import { Component } from '@angular/core';
import { CommonModule } from '@angular/common';
import { RouterLink } from '@angular/router';
@Component({
  selector: 'app-report-generation',
  imports: [CommonModule, RouterLink],
  templateUrl: './report-generation.html',
  styleUrl: './report-generation.css',
})
export class ReportGeneration {
  sections = [
    { name: 'Governance', standard: 'IFRS S1', status: 'Generated', score: '96%' },
    { name: 'Strategy', standard: 'IFRS S1/S2', status: 'Generated', score: '93%' },
    { name: 'Risk Management', standard: 'IFRS S2', status: 'Generated', score: '91%' },
    { name: 'Metrics & Targets', standard: 'IFRS S2', status: 'Generated', score: '94%' }
  ];

  reportChecks = [
    'Prepared ESG datasets loaded',
    'IFRS S1/S2 sections generated',
    'Climate risk disclosures included',
    'Metrics and targets mapped',
    'Expert approval required before final download'
  ];
}
