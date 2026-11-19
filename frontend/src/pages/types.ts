import type {
  ChatBody,
  Detail,
  Evidence,
  Parameters,
  Run,
  Plan,
  Skill,
} from "../types";
export interface WorkspacePageProps {
  detail: Detail;
  fileId: string | null;
  setFileId: (value: string | null) => void;
  busy: string;
  confirm: (plan: Plan) => Promise<void>;
  setModal: (value: "new" | "upload" | "settings" | null) => void;
  plan: (
    mode: ChatBody["mode"],
    message: string,
    parameters?: Parameters,
    skillId?: string,
    datasetIds?: string[],
    study?: import("../types").Project["study"],
  ) => Promise<void>;
  setTab: (
    value: "project" | "overview" | "data" | "analysis" | "report" | "skills",
  ) => void;
  setRunId: (value: string | null) => void;
  selected: string | null;
  refresh: () => Promise<void>;
  setNotice: (value: string) => void;
  setError: (value: string) => void;
  names: Record<string, string>;
  action: (key: string, fn: () => Promise<void>) => Promise<void>;
  currentRun: Run | undefined;
  setEvidence: (value: Evidence) => void;
  skills: Skill[];
  defaults: Parameters;
  openDataset: (id: string) => Promise<void>;
}
