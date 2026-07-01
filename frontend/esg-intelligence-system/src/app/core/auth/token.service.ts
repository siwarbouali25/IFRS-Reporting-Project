import { Injectable } from '@angular/core';
import { AuthUser } from './auth.models';

@Injectable({
  providedIn: 'root'
})
export class TokenService {
  private accessKey = 'access_token';
  private refreshKey = 'refresh_token';
  private userKey = 'auth_user';
  private mfaTokenKey = 'mfa_token';

  setTokens(access: string, refresh: string): void {
    localStorage.setItem(this.accessKey, access);
    localStorage.setItem(this.refreshKey, refresh);
  }

  getAccessToken(): string | null {
    return localStorage.getItem(this.accessKey);
  }

  getRefreshToken(): string | null {
    return localStorage.getItem(this.refreshKey);
  }

  setUser(user: AuthUser): void {
    localStorage.setItem(this.userKey, JSON.stringify(user));
  }

  getUser(): AuthUser | null {
    const user = localStorage.getItem(this.userKey);
    return user ? JSON.parse(user) : null;
  }

  setMfaToken(token: string): void {
    sessionStorage.setItem(this.mfaTokenKey, token);
  }

  getMfaToken(): string | null {
    return sessionStorage.getItem(this.mfaTokenKey);
  }

  clearMfaToken(): void {
    sessionStorage.removeItem(this.mfaTokenKey);
  }

  isLoggedIn(): boolean {
    return !!this.getAccessToken();
  }

  logout(): void {
    localStorage.removeItem(this.accessKey);
    localStorage.removeItem(this.refreshKey);
    localStorage.removeItem(this.userKey);
    sessionStorage.removeItem(this.mfaTokenKey);
  }
}