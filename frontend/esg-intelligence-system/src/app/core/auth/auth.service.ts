import { Injectable } from '@angular/core';
import { HttpClient, HttpHeaders  } from '@angular/common/http';
import { Observable, tap } from 'rxjs';
import { LoginRequest, LoginResponse } from './auth.models';
import { TokenService } from './token.service';

@Injectable({
  providedIn: 'root'
})
export class AuthService {
  private apiUrl = 'http://127.0.0.1:8000/api';

  constructor(
    private http: HttpClient,
    private tokenService: TokenService
  ) {}

  login(payload: LoginRequest): Observable<LoginResponse> {
    return this.http.post<LoginResponse>(`${this.apiUrl}/auth/login/`, payload).pipe(
      tap((response) => {
        if (response.mfa_required) {
          this.tokenService.setMfaToken(response.mfa_token);
          return;
        }

        this.tokenService.setTokens(response.access, response.refresh);
        this.tokenService.setUser(response.user);
      })
    );
  }

  logout(): void {
    this.tokenService.logout();
  }



  verifyMfaLogin(code: string) {
  const mfaToken = this.tokenService.getMfaToken();

  return this.http.post<any>(`${this.apiUrl}/auth/mfa/verify-login/`, {
    mfa_token: mfaToken,
    code
  }).pipe(
    tap((response) => {
      this.tokenService.setTokens(response.access, response.refresh);
      this.tokenService.setUser(response.user);
      this.tokenService.clearMfaToken();
    })
  );
}


getMfaSetupQr() {
  const token = this.tokenService.getAccessToken();

  const headers = new HttpHeaders({
    Authorization: `Bearer ${token}`
  });

  return this.http.get<any>(`${this.apiUrl}/auth/mfa/setup/`, { headers });
}

verifyMfaSetup(code: string) {
  const token = this.tokenService.getAccessToken();

  const headers = new HttpHeaders({
    Authorization: `Bearer ${token}`
  });

  return this.http.post<any>(
    `${this.apiUrl}/auth/mfa/verify-setup/`,
    { code },
    { headers }
  ).pipe(
    tap((response) => {
      this.tokenService.setUser(response.user);
    })
  );
}
}

