import { useState } from "react";
import { LoaderCircle } from "lucide-react";
import type { Project } from "../types";

export function ProjectForm({
  initial,
  onSubmit,
}: {
  initial?: Project | null;
  onSubmit: (name: string, description: string) => Promise<void>;
}) {
  const [name, setName] = useState(initial?.name || ""),
    [description, setDescription] = useState(initial?.description || ""),
    [busy, setBusy] = useState(false),
    [error, setError] = useState("");
  return (
    <form
      onSubmit={async (e) => {
        e.preventDefault();
        if (!name.trim()) return;
        setBusy(true);
        setError("");
        try {
          await onSubmit(name.trim(), description);
        } catch (e) {
          setError((e as Error).message);
        } finally {
          setBusy(false);
        }
      }}
    >
      <label>
        项目名称
        <input
          autoFocus
          required
          maxLength={120}
          placeholder="例如：肠道菌群与临床指标研究"
          value={name}
          onChange={(e) => setName(e.target.value)}
        />
      </label>
      <label>
        项目备注 <span className="muted">选填</span>
        <textarea
          rows={3}
          maxLength={3000}
          placeholder="记录研究目的、数据来源，或留给自己的提醒"
          value={description}
          onChange={(e) => setDescription(e.target.value)}
        />
      </label>
      {error && (
        <p role="alert" className="form-error">
          {error}
        </p>
      )}
      <button className="primary wide-button" disabled={busy || !name.trim()}>
        {busy && <LoaderCircle size={16} className="spin" />}
        {initial ? "保存项目" : "创建项目"}
      </button>
    </form>
  );
}
