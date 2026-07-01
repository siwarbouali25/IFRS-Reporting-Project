import { ComponentFixture, TestBed } from '@angular/core/testing';

import { DataPreparation } from './data-preparation';

describe('DataPreparation', () => {
  let component: DataPreparation;
  let fixture: ComponentFixture<DataPreparation>;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [DataPreparation],
    }).compileComponents();

    fixture = TestBed.createComponent(DataPreparation);
    component = fixture.componentInstance;
    await fixture.whenStable();
  });

  it('should create', () => {
    expect(component).toBeTruthy();
  });
});
