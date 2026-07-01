export type UserRole = 'admin' | 'auditor' | 'expert_reviewer';

export interface AuthUser {
  id: number;
  full_name: string;
  email: string;
  role: UserRole;
  department: string;
  mfa_enabled: boolean;
}

export interface LoginRequest {
  email: string;
  password: string;
}

export interface LoginSuccessResponse {
  refresh: string;
  access: string;
  mfa_required: false;
  mfa_setup_required?: boolean;
  user: AuthUser;
}

export interface MfaRequiredResponse {
  mfa_required: true;
  mfa_token: string;
  detail: string;
}

export type LoginResponse = LoginSuccessResponse | MfaRequiredResponse;