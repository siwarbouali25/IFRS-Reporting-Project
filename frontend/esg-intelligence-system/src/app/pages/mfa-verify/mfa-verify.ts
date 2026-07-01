import { CommonModule } from '@angular/common';
import { Component } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { Router } from '@angular/router';
import { AuthService } from '../../core/auth/auth.service';
import { TokenService } from '../../core/auth/token.service';

@Component({
  selector: 'app-mfa-verify',
  imports: [CommonModule, FormsModule],
  templateUrl: './mfa-verify.html',
  styleUrl: './mfa-verify.css'
})
export class MfaVerify {
  code = '';
  errorMessage = '';
  isLoading = false;

  constructor(
    private authService: AuthService,
    private tokenService: TokenService,
    private router: Router
  ) {}

  verifyCode(): void {
    this.errorMessage = '';

    if (!this.tokenService.getMfaToken()) {
      this.errorMessage = 'MFA session expired. Please login again.';
      return;
    }

    if (this.code.length !== 6) {
      this.errorMessage = 'Please enter the 6-digit code.';
      return;
    }

    this.isLoading = true;

    this.authService.verifyMfaLogin(this.code).subscribe({
      next: () => {
        this.isLoading = false;
        this.router.navigate(['/dashboard']);
      },
      error: (error) => {
        this.isLoading = false;
        this.errorMessage = error.error?.detail || 'Invalid MFA code.';
      }
    });
  }

  backToLogin(): void {
    this.tokenService.logout();
    this.router.navigate(['/login']);
  }
}