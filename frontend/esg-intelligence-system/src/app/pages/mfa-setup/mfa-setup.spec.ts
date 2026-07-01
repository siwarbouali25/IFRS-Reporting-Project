import { CommonModule } from '@angular/common';
import { Component, OnInit } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { Router } from '@angular/router';
import { AuthService } from '../../core/auth/auth.service';

@Component({
  selector: 'app-mfa-setup',
  imports: [CommonModule, FormsModule],
  templateUrl: './mfa-setup.html',
  styleUrl: './mfa-setup.css'
})
export class MfaSetup implements OnInit {
  qrCode = '';
  code = '';
  errorMessage = '';
  isLoading = false;
  isVerifying = false;

  constructor(
    private authService: AuthService,
    private router: Router
  ) {}

  ngOnInit(): void {
    this.loadQrCode();
  }

  loadQrCode(): void {
    this.isLoading = true;
    this.errorMessage = '';

    this.authService.getMfaSetupQr().subscribe({
      next: (response) => {
        this.qrCode = response.qr_code;
        this.isLoading = false;
      },
      error: (error) => {
        this.isLoading = false;
        this.errorMessage = error.error?.detail || 'Could not generate MFA QR code.';
      }
    });
  }

  verifySetup(): void {
    this.errorMessage = '';

    if (this.code.length !== 6) {
      this.errorMessage = 'Please enter the 6-digit code from your authenticator app.';
      return;
    }

    this.isVerifying = true;

    this.authService.verifyMfaSetup(this.code).subscribe({
      next: () => {
        this.isVerifying = false;
        this.router.navigate(['/dashboard']);
      },
      error: (error) => {
        this.isVerifying = false;
        this.errorMessage = error.error?.detail || 'Invalid MFA code.';
      }
    });
  }
}