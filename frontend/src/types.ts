import type { components } from "./generated-api";
export interface Entity {
  id: string;
  project_id?: string;
  created_at: string;
  updated_at: string;
}
export interface Dataset extends Entity {
  filename: string;
  transformations?: { sheet?: string; operation?: string }[];
  data_type: "taxonomy" | "functional" | "metadata" | "table";
  source: string;
  unit: string;
  samples: string[];
  features: number;
  columns: string[];
  warnings: string[];
  revision: number;
  alignment?: {
    matched: number;
    reference_samples: number;
    needs_confirmation: boolean;
  };
  source_sha256: string;
  summary: {
    rows?: number;
    columns?: number;
    rank_counts?: Record<string, number>;
    stratified_rows?: number;
    total_pathways?: number;
    zero_samples?: string[];
  };
}
export interface Artifact extends Entity {
  artifact_type: "png" | "svg" | "chart" | "table" | "code" | "audit";
  filename: string;
  title: string;
  sha256: string;
}
export interface Evidence {
  upstream_inputs?: Record<string, unknown>;
  id: string;
  statement: string;
  values: Record<string, unknown>;
  artifact_ids: string[];
  dataset_ids: string[];
  parameters: Record<string, unknown>;
}
export interface Result {
  skill: string;
  step_id: string;
  status: "success" | "skipped" | "failed";
  failure?: {
    step_id: string;
    message: string;
    detail: string;
    retryable: boolean;
  };
  summary: string;
  method: string;
  warnings: string[];
  artifacts: Artifact[];
  evidence: Evidence[];
  metrics: Record<string, unknown>;
  reused_from?: string;
  report_id?: string;
}
export type Parameters = Required<
  Pick<
    components["schemas"]["SkillParams"],
    | "rank"
    | "top_n"
    | "palette"
    | "title"
    | "group_order"
    | "pathway"
    | "prevalence"
    | "permutations"
    | "seed"
    | "group_a"
    | "group_b"
    | "variable"
  >
> & {
  dataset_id?: string | null;
  x?: string | null;
  y?: string | null;
  source?: string | null;
  target?: string | null;
  weight?: string | null;
  fields?: string[];
  samples?: string[];
  group_values?: string[];
  group_by?: string | null;
} & Partial<components["schemas"]["SkillParams"]>;
export interface FieldOption {
  dataset_id: string;
  field: string;
  values: string[];
}
export interface Choice {
  value: string;
  label: string;
  hint: string;
}
// One thing that stops a plan, with the input that resolves it.
export interface Clarification {
  id: string;
  kind:
    | "bind_field"
    | "unit"
    | "encoding"
    | "choice"
    | "text"
    | "select"
    | "samples";
  prompt: string;
  concept: string;
  dataset_id?: string | null;
  field?: string | null;
  options?: FieldOption[];
  values?: string[];
  choices?: string[];
  source?: "planner" | "check";
  target?: string;
  items?: Choice[];
  min_pick?: number;
  max_pick?: number;
  required?: boolean;
  action?: "" | "data";
}
export type ChatBody = components["schemas"]["ChatRequest"];

export interface Step {
  id: string;
  skill: string;
  reason?: string;
  parameters: Parameters;
  depends_on: string[];
  inputs?: Record<string, components["schemas"]["ResultInput"]>;
  cohort_from?: string | null;
  program?: components["schemas"]["AnalysisProgram"] | null;
}
export interface Plan extends Entity {
  research_design?: components["schemas"]["ResearchDesign"] | null;
  preparation_preview?: {
    step_id: string;
    included: number;
    excluded: number;
    exclusion_reasons: Record<string, number>;
    operations: {
      op: string;
      column: string;
      output: string;
      before: number;
      after: number;
      low_threshold?: number;
      high_threshold?: number;
      boundary?: string;
      counts?: Record<string, number>;
    }[];
  }[];
  request_mode?: ChatBody["mode"];
  skill_id?: string;
  snapshot?: { datasets: Record<string, string> };
  objective: string;
  summary: string;
  steps: Step[];
  questions: string[];
  clarifications?: Clarification[];
  clarification_log?: { question: string; answer: string }[];
  origin: "guided" | "model";
}
export interface Run extends Entity {
  partial?: boolean;
  status: string;
  progress: number;
  current_step: number;
  plan: Plan;
  plan_id: string;
  results: Result[];
  error?: string;
  snapshot: unknown;
}
export interface ReportSection {
  id: string;
  title: string;
  text: string;
  evidence_ids: string[];
  artifact_ids: string[];
}
export interface Report extends Entity {
  title: string;
  sections: ReportSection[];
  revision: number;
  evidence: Evidence[];
  stale: boolean;
  ai_status: string;
  ai_warning: string;
  run_id: string;
}
export interface Message extends Entity {
  role: "user" | "assistant";
  content: string;
  plan_id?: string;
}
export interface Project extends Entity {
  name: string;
  description: string;
  synthetic?: boolean;
  active_datasets: Record<string, string>;
  study: {
    group_column: string | null;
    independent: boolean;
    excluded_samples: string[];
  };
}
export interface Detail extends Project {
  context?: {
    contains_example_data?: boolean;
    fields: {
      name: string;
      meaning?: string;
      role?: string;
      continuous: boolean;
      numeric_count: number;
      missing_count: number;
    }[];
    matched_metadata: number;
    reference_samples: number;
  };
  group_counts?: Record<string, number>;
  datasets: Dataset[];
  runs: Run[];
  reports: Report[];
  messages: Message[];
  plans: Plan[];
}
export interface Skill {
  id: string;
  name: string;
  description: string;
  requires: string;
  version: string;
}
export interface Preview {
  columns: string[];
  rows: (string | number | null)[][];
}
export interface DatasetDetail extends Dataset {
  field_profile: Understanding;
  preview: Preview;
  suggestions: {
    mapping: Record<string, string>;
    unmatched: string[];
    needs_confirmation: boolean;
    reference: string | null;
  };
}

export interface FieldMeaning {
  name: string;
  meaning: string;
  unit: string;
  encoding: string;
  role:
    | "unknown"
    | "identifier"
    | "subject"
    | "categorical"
    | "numeric"
    | "ordinal"
    | "time";
}
export interface FieldProfile extends FieldMeaning {
  confirmed: boolean;
  numeric_count: number;
  missing_count: number;
  unique_count: number;
  numeric_candidate: boolean;
  values: string[];
}
export interface Understanding {
  dataset_id: string;
  revision: number;
  description: string;
  fields: FieldProfile[];
}
