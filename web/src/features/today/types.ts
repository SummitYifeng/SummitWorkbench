import type { BriefData } from '../../brief-card';
import type { ProjectState } from '../projects/types';

export interface TodayStatus {
  pending_review: number;
  backlog: { oldest_age_days: number | null };
}

export interface TodayState {
  day: string;
  status: TodayStatus;
  brief_md: string | null;
  brief_generated: boolean;
  brief?: BriefData | null;
  projects: ProjectState[];
}

export interface TodayRenderOptions {
  state: TodayState | null;
  importing: boolean;
  importOpen: boolean;
  capturing?: boolean;
  loadError?: string | null;
  importResult?: {
    fileName: string;
    bytes: number;
    status: 'processing' | 'success' | 'error';
    message: string;
    details?: string[];
    estimate?: { est_cost?: number; currency?: string; crosses_soft_budget?: boolean };
  } | null;
  readStatus?: { lastSuccessfulAt: string | null; error: string | null };
  health: { tone: string; label: string };
}

export interface TodayActions {
  capture: (text: string) => Promise<{ ok: boolean }>;
  importFile: (file: File) => Promise<void>;
  toggleImport: (open: boolean) => void;
  refresh: () => void;
}
