import { ComponentFixture, TestBed } from '@angular/core/testing';

import { ReportGeneration } from './report-generation';

describe('ReportGeneration', () => {
  let component: ReportGeneration;
  let fixture: ComponentFixture<ReportGeneration>;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [ReportGeneration],
    }).compileComponents();

    fixture = TestBed.createComponent(ReportGeneration);
    component = fixture.componentInstance;
    await fixture.whenStable();
  });

  it('should create', () => {
    expect(component).toBeTruthy();
  });
});
