import { Routes } from '@angular/router';
import { DashboardComponent } from './pages/dashboard/dashboard';
import { Login } from './pages/login/login';
import { SignUp } from './pages/sign-up/sign-up';
import { MainLayout } from './layout/main-layout/main-layout';
import { Profile } from './pages/profile/profile';
import { DataUpload } from './pages/data-upload/data-upload';
import { DataPreparation } from './pages/data-preparation/data-preparation';
import { ReportGeneration } from './pages/report-generation/report-generation';
import { MfaVerify } from './pages/mfa-verify/mfa-verify';
import { MfaSetup } from './pages/mfa-setup/mfa-setup';
import { RiskAnalysis } from './pages/risk-analysis/risk-analysis';
import { Assistant } from './pages/assistant/assistant';

export const routes: Routes = [
  { path: '', redirectTo: 'login', pathMatch: 'full' },
  { path: 'mfa/verify', component: MfaVerify },
  { path: 'mfa/setup', component: MfaSetup },
  {
    path: '',
    component: MainLayout,
    children: [
      { path: 'dashboard', component: DashboardComponent },
      { path: 'profile', component: Profile },
      { path: 'data-upload', component: DataUpload },
      { path: 'data-preparation', component: DataPreparation },
      { path: 'report-generation', component: ReportGeneration },
      { path: 'risk-analysis', component: RiskAnalysis },
    ]
  },
  { path: 'login', component: Login },
  { path: 'sign-up', component: SignUp }
];
