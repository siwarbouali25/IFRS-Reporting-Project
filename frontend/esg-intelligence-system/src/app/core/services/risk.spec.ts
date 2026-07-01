import { TestBed } from '@angular/core/testing';

import { Risk } from './risk';

describe('Risk', () => {
  let service: Risk;

  beforeEach(() => {
    TestBed.configureTestingModule({});
    service = TestBed.inject(Risk);
  });

  it('should be created', () => {
    expect(service).toBeTruthy();
  });
});
