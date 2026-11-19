import { useEffect, useState } from "react";
import { Check, LoaderCircle, Sparkles } from "lucide-react";
import { post, put, request } from "../api";
import type { DatasetDetail, FieldMeaning, FieldProfile } from "../types";
const roles = {
  unknown: "暂不指定",
  identifier: "编号",
  subject: "同一人的编号",
  categorical: "类别或分组",
  numeric: "数值指标",
  ordinal: "等级",
  time: "日期或时间",
};
export function UnderstandingPanel({
  pid,
  datasetId,
  onSave,
}: {
  pid: string;
  datasetId: string;
  onSave: () => Promise<void>;
}) {
  const [file, setFile] = useState<DatasetDetail | null>(null),
    [description, setDescription] = useState(""),
    [fields, setFields] = useState<FieldProfile[]>([]),
    [column, setColumn] = useState(""),
    [busy, setBusy] = useState(""),
    [error, setError] = useState(""),
    [changed, setChanged] = useState(false),
    [draft, setDraft] = useState<FieldMeaning[] | null>(null);
  useEffect(() => {
    let active = true;
    request<DatasetDetail>(`/projects/${pid}/datasets/${datasetId}`)
      .then((d) => {
        if (active) {
          setFile(d);
          setDescription(d.field_profile.description);
          setFields(d.field_profile.fields);
        }
      })
      .catch((e) => active && setError(e.message));
    return () => {
      active = false;
    };
  }, [pid, datasetId]);
  const field = fields.find((f) => f.name === column);
  function change(patch: Partial<FieldMeaning>) {
    setFields((fs) =>
      fs.map((f) => (f.name === column ? { ...f, ...patch } : f)),
    );
    setChanged(true);
  }
  async function save() {
    if (!file) return;
    setBusy("save");
    setError("");
    try {
      await put(`/projects/${pid}/datasets/${datasetId}/understanding`, {
        description,
        fields: fields
          .filter(
            (f) =>
              f.confirmed ||
              f.meaning ||
              f.unit ||
              f.encoding ||
              f.role !== "unknown",
          )
          .map(({ name, meaning, role, unit, encoding }) => ({
            name,
            meaning,
            role,
            unit,
            encoding,
          })),
        expected_revision: file.field_profile.revision,
      });
      const d = await request<DatasetDetail>(
        `/projects/${pid}/datasets/${datasetId}`,
      );
      setFile(d);
      setFields(d.field_profile.fields);
      setChanged(false);
      await onSave();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy("");
    }
  }
  if (!file) return <p>{error || "正在读取…"}</p>;
  return (
    <div className="file-context">
      <label>
        这张表记录了什么？
        <textarea
          aria-label="文件背景"
          rows={2}
          placeholder="例如：每行是一位参与者；年龄单位是岁；1 表示男、2 表示女。清楚的列名不用重复解释。"
          value={description}
          onChange={(e) => {
            setDescription(e.target.value);
            setChanged(true);
          }}
        />
      </label>
      <button
        className="text-button"
        disabled={!!busy || !description.trim()}
        onClick={async () => {
          setBusy("suggest");
          setError("");
          try {
            const r = await post<{ fields: FieldMeaning[] }>(
              `/projects/${pid}/datasets/${datasetId}/understanding/suggest`,
              { description },
            );
            setDraft(r.fields);
          } catch (e) {
            setError((e as Error).message);
          } finally {
            setBusy("");
          }
        }}
      >
        {busy === "suggest" ? (
          <LoaderCircle className="spin" size={15} />
        ) : (
          <Sparkles size={15} />
        )}
        帮我整理这段说明
      </button>
      {draft && (
        <section className="meaning-proposal">
          <h3>核对后再应用</h3>
          {draft.length ? (
            draft.map((f) => (
              <p key={f.name}>
                <strong>{f.name}</strong>：{f.meaning || roles[f.role]} {f.unit}{" "}
                {f.encoding}
              </p>
            ))
          ) : (
            <p>未提取到需要补充的列。</p>
          )}
          <div className="form-actions">
            <button className="secondary" onClick={() => setDraft(null)}>
              取消
            </button>
            <button
              className="primary"
              onClick={() => {
                const byName = Object.fromEntries(
                  draft.map((f) => [f.name, f]),
                );
                setFields((fs) =>
                  fs.map((f) =>
                    byName[f.name] ? { ...f, ...byName[f.name] } : f,
                  ),
                );
                setChanged(true);
                setDraft(null);
              }}
            >
              应用说明
            </button>
          </div>
        </section>
      )}
      {!!fields.length && (
        <div className="column-note">
          <label>
            或者，只解释某一列
            <select
              aria-label="需要解释的列"
              value={column}
              onChange={(e) => setColumn(e.target.value)}
            >
              <option value="">选择一列</option>
              {fields.map((f) => (
                <option key={f.name}>{f.name}</option>
              ))}
            </select>
          </label>
          {field && (
            <>
              <div className="column-examples">
                文件里的值：
                {field.values.length
                  ? field.values.join("、")
                  : `${field.numeric_count} 个数值，${field.missing_count} 个空缺`}
              </div>
              <div className="form-grid">
                <label>
                  这列表示什么
                  <input
                    value={field.meaning}
                    placeholder={field.name}
                    onChange={(e) => change({ meaning: e.target.value })}
                  />
                </label>
                <label>
                  用哪种方式理解
                  <select
                    value={field.role}
                    onChange={(e) =>
                      change({ role: e.target.value as FieldMeaning["role"] })
                    }
                  >
                    {Object.entries(roles).map(([k, v]) => (
                      <option key={k} value={k}>
                        {v}
                      </option>
                    ))}
                  </select>
                </label>
                <label>
                  单位
                  <input
                    value={field.unit}
                    placeholder="没有可留空"
                    onChange={(e) => change({ unit: e.target.value })}
                  />
                </label>
                <label>
                  特殊值或编码的含义
                  <input
                    value={field.encoding}
                    placeholder="如：1=男，2=女"
                    onChange={(e) => change({ encoding: e.target.value })}
                  />
                </label>
              </div>
            </>
          )}
        </div>
      )}
      {error && (
        <p role="alert" className="form-error">
          {error}
        </p>
      )}
      <div className="form-actions">
        <button
          className="primary"
          disabled={!!busy || !changed}
          onClick={save}
        >
          {busy === "save" ? (
            <LoaderCircle size={15} className="spin" />
          ) : (
            <Check size={15} />
          )}
          保存补充信息
        </button>
      </div>
    </div>
  );
}
