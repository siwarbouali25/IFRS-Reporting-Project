import { Component } from '@angular/core';
import { CommonModule } from '@angular/common';

@Component({
  selector: 'app-data-upload',
  imports: [CommonModule],
  templateUrl: './data-upload.html',
  styleUrl: './data-upload.css'
})
export class DataUpload {
  totalFiles = 24;
  uploadedFiles = 17;
  missingFiles = 7;
  completionRate = 71;

  categories = [
    {
      name: 'Governance & Strategy',
      icon: 'pi pi-building',
      uploaded: 2,
      total: 3,
      files: [
        { name: 'governance.csv', uploaded: true },
        { name: 'board_minutes_extract.csv', uploaded: true },
        { name: 'source_systems.csv', uploaded: false }
      ]
    },
    {
      name: 'Climate Risks & Opportunities',
      icon: 'pi pi-globe',
      uploaded: 4,
      total: 4,
      files: [
        { name: 'climate_risk_register.csv', uploaded: true },
        { name: 'climate_opportunities.csv', uploaded: true },
        { name: 'climate_scenarios.csv', uploaded: true },
        { name: 'physical_risk_exposures.csv', uploaded: true }
      ]
    },
    {
      name: 'Carbon & Emissions',
      icon: 'pi pi-sync',
      uploaded: 1,
      total: 3,
      files: [
        { name: 'counterparty_emissions.csv', uploaded: true },
        { name: 'carbon_credits.csv', uploaded: false },
        { name: 'internal_carbon_price.csv', uploaded: false }
      ]
    },
    {
      name: 'Operations & Energy',
      icon: 'pi pi-bolt',
      uploaded: 2,
      total: 4,
      files: [
        { name: 'utility_invoices.csv', uploaded: true },
        { name: 'facilities.csv', uploaded: true },
        { name: 'vehicles.csv', uploaded: false },
        { name: 'travel_records.csv', uploaded: false }
      ]
    },
    {
      name: 'Financial Exposure',
      icon: 'pi pi-chart-bar',
      uploaded: 5,
      total: 6,
      files: [
        { name: 'banks.csv', uploaded: true },
        { name: 'financial_summary.csv', uploaded: true },
        { name: 'investments.csv', uploaded: true },
        { name: 'exposures.csv', uploaded: true },
        { name: 'collateral.csv', uploaded: true },
        { name: 'counterparties.csv', uploaded: false }
      ]
    },
    {
      name: 'Workforce',
      icon: 'pi pi-users',
      uploaded: 1,
      total: 1,
      files: [{ name: 'employees.csv', uploaded: true }]
    },
    {
      name: 'Targets & Commitments',
      icon: 'pi pi-flag',
      uploaded: 1,
      total: 2,
      files: [
        { name: 'targets.csv', uploaded: true },
        { name: 'rec_registry.csv', uploaded: false }
      ]
    },
    {
      name: 'Value Chain',
      icon: 'pi pi-sitemap',
      uploaded: 1,
      total: 1,
      files: [{ name: 'value_chain_map.csv', uploaded: true }]
    }
  ];

  getStatus(category: any): string {
    return category.uploaded === category.total ? 'Complete' : 'Missing data';
  }
}