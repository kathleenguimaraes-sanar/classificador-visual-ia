export type ViewName = "connection" | "import" | "processing" | "results";

export interface AuthSession {
  auth_enabled: boolean;
  authenticated: boolean;
  username: string;
}

export interface ServiceStatus {
  gemini: boolean;
  claude: boolean;
  ollama_enabled: boolean;
  jw_agent: boolean;
}

export interface Library {
  name: string;
  propertyId: string;
  url: string;
}

export interface JWStatus {
  state: "connected" | "connecting" | "disconnected" | "attention" | "error";
  connected?: boolean;
  message?: string;
  property_id?: string;
  library?: string;
  library_name?: string;
  library_url?: string;
}

export interface FilterSummary {
  total: number;
  eligible: number;
  filtered: number;
  no_date: number;
  errors: number;
  will_be_analyzed: number;
}

export interface ImportResult {
  run_id: number;
  rows: number;
  unique_media: number;
  reused_media: number;
  pending_media: number;
  filter: FilterSummary;
  library: string;
  property_id: string;
}

export type JobState =
  | "queued"
  | "running"
  | "paused"
  | "completed"
  | "error"
  | "cancelled";

export interface Job {
  id: string;
  media_id?: string;
  jwplayer_id?: string;
  state: JobState;
  stage: string;
  message: string;
  provider?: string;
  model?: string;
  created_at?: string;
  result?: Record<string, unknown>;
}

export interface Video {
  record_id?: string;
  lesson_name?: string;
  professor_name?: string;
  jwplayer_id: string;
  keywords?: string;
  publish_date?: string | null;
  status?: string;
  final_category?: string;
  ai_category?: string;
  summary?: string;
  confidence?: number | null;
  validation_status?: string;
  duration?: number | null;
  error_message?: string | null;
  macrotema?: string | null;
  microtema?: string | null;
  nanotema?: string | null;
}

export interface AnalysisSettings {
  provider: "Gemini" | "Claude" | "Ollama";
  model: string;
  analysisMode: "frames" | "hybrid";
  frameCount: number;
  whisperModel: "base" | "small" | "medium";
}
