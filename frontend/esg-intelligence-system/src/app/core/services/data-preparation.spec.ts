import { TestBed } from '@angular/core/testing';

import { DataPreparation } from './data-preparation';

describe('DataPreparation', () => {
  let service: DataPreparation;

  beforeEach(() => {
    TestBed.configureTestingModule({});
    service = TestBed.inject(DataPreparation);
  });

  it('should be created', () => {
    expect(service).toBeTruthy();
  });
});
