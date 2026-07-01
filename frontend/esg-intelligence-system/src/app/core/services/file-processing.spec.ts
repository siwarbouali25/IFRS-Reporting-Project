import { TestBed } from '@angular/core/testing';

import { FileProcessing } from './file-processing';

describe('FileProcessing', () => {
  let service: FileProcessing;

  beforeEach(() => {
    TestBed.configureTestingModule({});
    service = TestBed.inject(FileProcessing);
  });

  it('should be created', () => {
    expect(service).toBeTruthy();
  });
});
