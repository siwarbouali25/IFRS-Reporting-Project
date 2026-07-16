import { TestBed } from '@angular/core/testing';

import { KpiDashboard } from './kpi-dashboard';

describe('KpiDashboard', () => {
  let service: KpiDashboard;

  beforeEach(() => {
    TestBed.configureTestingModule({});
    service = TestBed.inject(KpiDashboard);
  });

  it('should be created', () => {
    expect(service).toBeTruthy();
  });
});
