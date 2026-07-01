import { HttpInterceptorFn } from '@angular/common/http';
import { inject } from '@angular/core';
import { TokenService } from './core/auth/token.service';

/**
 * Attaches the stored JWT access token to every outgoing request as a
 * Bearer header. None of the existing services (auth.service.ts included)
 * attached this automatically — auth.service.ts only stores the token.
 * Without this, every call from the new Risk service (and any other
 * authenticated endpoint) returns 401, the same way the upload endpoint
 * does if you call it without a header.
 *
 * Registered in app.config.ts via provideHttpClient(withInterceptors([...])).
 */
export const authInterceptor: HttpInterceptorFn = (req, next) => {
  const tokenService = inject(TokenService);
  const token = tokenService.getAccessToken();

  if (!token) {
    return next(req);
  }

  const cloned = req.clone({
    setHeaders: { Authorization: `Bearer ${token}` },
  });
  return next(cloned);
};
