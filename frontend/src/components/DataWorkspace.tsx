import { useState } from "react";

import {
  Check,
  ChevronRight,
  LoaderCircle,
  FileText,
  Trash2,
  Upload,
} from "lucide-react";
import { post, request } from "../api";
import type { DatasetDetail, Preview } from "../types";

type SheetInfo = { name: string; columns: string[]; rows: number };
type ReadOptions = {
  kind: string;
  unit: string;
  sheet: string;
  id_column: string;
  transpose: boolean;
  header_row: number;
  encoding: string;
  delimiter: string;
};
type ImportFile = {
  file: File;
  options: ReadOptions;
  sheets: SheetInfo[];
  columns: string[];
  preview: Preview | null;
  rows: number;
  done: boolean;
  checked: boolean;
  error: string;
};
const readingDefaults: ReadOptions = {
  kind: "auto",
  unit: "auto",
  sheet: "",
  id_column: "",
  transpose: false,
  header_row: 1,
  encoding: "auto",
  delimiter: "auto",
};
export function UploadPanel({
  pid,
  onDone,
}: {
  pid: string;
  onDone: () => Promise<void>;
}) {
  const [items, setItems] = useState<ImportFile[]>([]),
    [busy, setBusy] = useState(false),
    [chosen, setChosen] = useState(0),
    [error, setError] = useState("");
  const patch = (i: number, value: Partial<ImportFile>) =>
    setItems((xs) => xs.map((x, n) => (n === i ? { ...x, ...value } : x)));
  async function probe(item: ImportFile) {
    const form = new FormData();
    form.append("file", item.file);
    form.append(
      "options",
      JSON.stringify({
        ...item.options,
        sheet: item.options.sheet || null,
        id_column: item.options.id_column || null,
      }),
    );
    const result = await request<{
      sheets: SheetInfo[];
      columns: string[];
      rows: number;
      preview: Preview | null;
      inferred: string;
      issue?: string;
    }>(`/projects/${pid}/import-preview`, { method: "POST", body: form });
    return {
      ...item,
      sheets: result.sheets,
      columns: result.columns,
      rows: result.rows,
      preview: result.preview,
      checked: !!result.preview,
      error: result.issue || "",
      options: {
        ...item.options,
        sheet: item.options.sheet || result.sheets[0]?.name || "",
        kind:
          item.options.kind === "auto" ? result.inferred : item.options.kind,
      },
    };
  }
  async function choose(list: FileList | null) {
    if (busy) return;
    setBusy(true);
    setError("");
    const next: ImportFile[] = [];
    for (const file of Array.from(list || [])) {
      let item: ImportFile = {
        file,
        options: { ...readingDefaults },
        sheets: [],
        columns: [],
        preview: null,
        rows: 0,
        checked: false,
        done: false,
        error: "",
      };
      try {
        item = await probe(item);
      } catch (e) {
        item.error = (e as Error).message;
      }
      next.push(item);
    }
    setItems((xs) => [...xs, ...next]);
    setChosen(items.length);
    setBusy(false);
  }
  async function updatePreview(i: number) {
    setBusy(true);
    try {
      patch(i, await probe(items[i]));
    } catch (e) {
      patch(i, { checked: false, error: (e as Error).message });
    } finally {
      setBusy(false);
    }
  }
  function setOption(i: number, value: Partial<ReadOptions>, recheck = false) {
    patch(i, {
      options: { ...items[i].options, ...value },
      ...(recheck ? { checked: false } : {}),
    });
  }
  async function upload() {
    setBusy(true);
    setError("");
    let failed = false;
    for (let i = 0; i < items.length; i++) {
      const item = items[i];
      if (item.done) continue;
      if (!item.checked) {
        failed = true;
        patch(i, { error: "先更新预览，核对内容后再添加。" });
        continue;
      }
      try {
        const form = new FormData();
        form.append("file", item.file);
        form.append(
          "options",
          JSON.stringify({
            ...item.options,
            sheet: item.options.sheet || null,
            id_column: item.options.id_column || null,
          }),
        );
        await request(`/projects/${pid}/datasets`, {
          method: "POST",
          body: form,
        });
        patch(i, { done: true, error: "" });
      } catch (e) {
        patch(i, { error: (e as Error).message });
        failed = true;
        setChosen(i);
      }
    }
    if (!failed) await onDone();
    setBusy(false);
  }
  const item = items[chosen];
  return (
    <>
      <label
        className="dropzone compact-drop"
        onDragOver={(e) => e.preventDefault()}
        onDrop={(e) => {
          e.preventDefault();
          void choose(e.dataTransfer.files);
        }}
      >
        <Upload size={25} />
        <strong>{busy ? "正在读取文件…" : "选择文件，或拖到这里"}</strong>
        <span>Excel · CSV · TSV · JSON 记录表</span>
        <input
          type="file"
          multiple
          accept=".xlsx,.csv,.tsv,.txt,.json"
          disabled={busy}
          onChange={(e) => void choose(e.target.files)}
        />
      </label>
      {items.length > 0 && (
        <>
          <div className="upload-file-tabs">
            {items.map((x, i) => (
              <button
                key={i}
                className={chosen === i ? "selected" : ""}
                onClick={() => setChosen(i)}
              >
                {x.done && <Check size={14} />} {x.file.name}
                {x.options.sheet && ` · ${x.options.sheet}`}
              </button>
            ))}
          </div>
          {item && (
            <section className="upload-reading">
              <div className="section-title">
                <h3>{item.file.name}</h3>
                <span>
                  {item.rows} 行 · {item.columns.length} 列
                </span>
              </div>
              {item.preview ? (
                <DataTable preview={item.preview} />
              ) : (
                <p className="form-error">
                  {item.error || "这份文件还没有读取成功。"}
                </p>
              )}
              {item.sheets.length > 1 && (
                <div className="workbook-picker">
                  <label>
                    查看工作表
                    <select
                      aria-label="查看工作表"
                      value={item.options.sheet}
                      disabled={busy || item.done}
                      onChange={(e) =>
                        setOption(
                          chosen,
                          { sheet: e.target.value, kind: "auto" },
                          true,
                        )
                      }
                    >
                      {item.sheets.map((sh) => (
                        <option key={sh.name}>{sh.name}</option>
                      ))}
                    </select>
                  </label>
                  <button
                    className="text-button"
                    disabled={busy}
                    onClick={() => {
                      const sheet =
                        item.sheets.find((sh) => sh.name !== item.options.sheet)
                          ?.name || "";
                      setItems((xs) => [
                        ...xs,
                        {
                          ...item,
                          done: false,
                          checked: false,
                          preview: null,
                          error: "",
                          options: { ...item.options, sheet, kind: "auto" },
                        },
                      ]);
                      setChosen(items.length);
                    }}
                  >
                    再添加一个工作表
                  </button>
                </div>
              )}
              <details className="reading-options">
                <summary>读出来的内容不对？调整读取方式</summary>
                <div className="form-grid">
                  {!item.file.name.toLowerCase().endsWith(".json") && (
                    <>
                      <label>
                        列名在第几行
                        <input
                          aria-label="列名行"
                          type="number"
                          min={1}
                          max={1000}
                          value={item.options.header_row}
                          disabled={busy || item.done}
                          onChange={(e) =>
                            setOption(
                              chosen,
                              {
                                header_row: Number(e.target.value) || 1,
                                kind: "auto",
                              },
                              true,
                            )
                          }
                        />
                      </label>
                    </>
                  )}
                  {!item.file.name.toLowerCase().endsWith(".xlsx") &&
                    !item.file.name.toLowerCase().endsWith(".json") && (
                      <>
                        <label>
                          分隔方式
                          <select
                            value={item.options.delimiter}
                            disabled={busy || item.done}
                            onChange={(e) =>
                              setOption(
                                chosen,
                                { delimiter: e.target.value },
                                true,
                              )
                            }
                          >
                            <option value="auto">自动识别</option>
                            <option value="comma">逗号</option>
                            <option value="tab">制表符</option>
                            <option value="semicolon">分号</option>
                          </select>
                        </label>
                        <label>
                          文字编码
                          <select
                            value={item.options.encoding}
                            disabled={busy || item.done}
                            onChange={(e) =>
                              setOption(
                                chosen,
                                { encoding: e.target.value },
                                true,
                              )
                            }
                          >
                            <option value="auto">自动识别</option>
                            <option value="utf-8-sig">UTF-8</option>
                            <option value="gb18030">GB18030</option>
                          </select>
                        </label>
                      </>
                    )}
                  <label>
                    这是什么表
                    <select
                      value={item.options.kind}
                      disabled={busy || item.done}
                      onChange={(e) =>
                        setOption(chosen, { kind: e.target.value })
                      }
                    >
                      <option value="table">普通数据表</option>
                      <option value="metadata">一行一个样本的信息表</option>
                      <option value="taxonomy">物种丰度矩阵</option>
                      <option value="functional">功能通路矩阵</option>
                      <option value="auto">自动识别</option>
                    </select>
                  </label>
                  {item.options.kind !== "table" && (
                    <label>
                      用于对应样本的编号列
                      <select
                        value={item.options.id_column}
                        disabled={busy || item.done}
                        onChange={(e) =>
                          setOption(chosen, { id_column: e.target.value })
                        }
                      >
                        <option value="">自动识别</option>
                        {item.columns.map((c) => (
                          <option key={c}>{c}</option>
                        ))}
                      </select>
                    </label>
                  )}
                  {["taxonomy", "functional"].includes(item.options.kind) && (
                    <>
                      <label>
                        矩阵数值的单位
                        <select
                          value={item.options.unit}
                          disabled={busy || item.done}
                          onChange={(e) =>
                            setOption(chosen, { unit: e.target.value })
                          }
                        >
                          <option value="auto">自动识别</option>
                          <option value="fraction">比例（0–1）</option>
                          <option value="percent">百分比（0–100）</option>
                          <option value="counts">整数计数</option>
                          <option value="other">其他标准化数值</option>
                        </select>
                      </label>
                      <label className="check-label">
                        <input
                          type="checkbox"
                          checked={item.options.transpose}
                          disabled={busy || item.done}
                          onChange={(e) =>
                            setOption(chosen, { transpose: e.target.checked })
                          }
                        />
                        原表每行是一个样本
                      </label>
                    </>
                  )}
                </div>
              </details>
              {!item.checked && (
                <button
                  className="secondary"
                  disabled={busy || item.done}
                  onClick={() => void updatePreview(chosen)}
                >
                  更新预览
                </button>
              )}
              {item.error && item.preview && (
                <p role="alert" className="form-error">
                  {item.error}
                </p>
              )}
            </section>
          )}
        </>
      )}
      {error && (
        <p role="alert" className="form-error">
          {error}
        </p>
      )}
      <button
        className="primary wide-button"
        disabled={
          busy || !items.length || items.some((x) => !x.done && !x.checked)
        }
        onClick={upload}
      >
        {busy ? (
          <LoaderCircle size={16} className="spin" />
        ) : (
          <Check size={16} />
        )}
        内容正确，添加到项目
      </button>
    </>
  );
}
export function DataTable({ preview }: { preview: Preview }) {
  return (
    <div className="table-scroll">
      <table>
        <thead>
          <tr>
            {preview.columns.map((c, i) => (
              <th key={i}>{c}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {preview.rows.map((row, i) => (
            <tr key={i}>
              {row.map((x, j) => (
                <td key={j} title={String(x ?? "")}>
                  {typeof x === "number"
                    ? Number.isInteger(x)
                      ? x
                      : x.toPrecision(4)
                    : String(x ?? "NA")}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
export function DatasetPanel({
  dataset,
  onConfirm,
  onRemove,
}: {
  dataset: DatasetDetail;
  onConfirm: (m: Record<string, string>, e: string[]) => Promise<void>;
  onRemove: () => Promise<void>;
}) {
  const [mapping, setMapping] = useState(dataset.suggestions.mapping),
    [excluded, setExcluded] = useState<string[]>([]),
    [search, setSearch] = useState(""),
    [page, setPage] = useState(0),
    [busy, setBusy] = useState(false),
    [error, setError] = useState("");
  const filtered = dataset.samples.filter((s) =>
    s.toLowerCase().includes(search.toLowerCase()),
  );
  const shown = filtered.slice(page * 10, page * 10 + 10);
  return (
    <>
      <div className="compact-stats">
        <span>{dataset.samples.length} 个样本</span>
        <span>{dataset.features.toLocaleString()} 个条目</span>
        <span>单位：{dataset.unit}</span>
      </div>
      {dataset.warnings.map((w) => (
        <p className="small-warning" key={w}>
          {w}
        </p>
      ))}
      <DatasetType
        dataset={dataset}
        onDone={() => window.dispatchEvent(new Event("yanji:dataset-updated"))}
      />
      <h3>数据预览</h3>
      <DataTable preview={dataset.preview} />
      {dataset.data_type !== "table" && (
        <details className="details">
          <summary>跨文件分析时，核对编号对应</summary>
          <div className="section-title">
            <h3>样本对应与排除</h3>
            <span>
              {dataset.suggestions.needs_confirmation
                ? "候选对应需要你确认"
                : "可以修改样本名或明确排除样本"}
            </span>
          </div>
          <input
            placeholder="搜索样本…"
            value={search}
            onChange={(e) => {
              setSearch(e.target.value);
              setPage(0);
            }}
          />
          <div className="mapping-list">
            {shown.map((s) => (
              <div key={s}>
                <span title={s}>{s}</span>
                <ChevronRight size={14} />
                <input
                  aria-label={"目标样本 " + s}
                  value={mapping[s] ?? s}
                  onChange={(e) =>
                    setMapping({ ...mapping, [s]: e.target.value })
                  }
                />
                <label className="check-label">
                  <input
                    type="checkbox"
                    checked={excluded.includes(s)}
                    onChange={(e) =>
                      setExcluded(
                        e.target.checked
                          ? [...excluded, s]
                          : excluded.filter((x) => x !== s),
                      )
                    }
                  />
                  排除
                </label>
              </div>
            ))}
          </div>
          <div className="pagination">
            <button disabled={page === 0} onClick={() => setPage((p) => p - 1)}>
              上一页
            </button>
            <span>
              {page + 1} / {Math.max(1, Math.ceil(filtered.length / 10))}
            </span>
            <button
              disabled={(page + 1) * 10 >= filtered.length}
              onClick={() => setPage((p) => p + 1)}
            >
              下一页
            </button>
          </div>
          <p className="muted">
            修改会创建新版本，原始数据仍保留。已排除 {excluded.length} 个样本。
          </p>
        </details>
      )}
      {error && <p className="form-error">{error}</p>}
      <div className="form-actions">
        <button
          className="danger-button"
          disabled={busy}
          onClick={async () => {
            if (!confirm("从当前研究移除这份数据？历史版本和结果会保留。"))
              return;
            setBusy(true);
            try {
              await onRemove();
            } catch (e) {
              setError((e as Error).message);
            } finally {
              setBusy(false);
            }
          }}
        >
          <Trash2 size={15} />
          移出当前数据
        </button>
        {dataset.data_type !== "table" && (
          <button
            className="primary"
            disabled={busy}
            onClick={async () => {
              setBusy(true);
              try {
                await onConfirm(mapping, excluded);
              } catch (e) {
                setError((e as Error).message);
              } finally {
                setBusy(false);
              }
            }}
          >
            <Check size={16} />
            确认并保存新版本
          </button>
        )}
      </div>
    </>
  );
}
function DatasetType({
  dataset,
  onDone,
}: {
  dataset: DatasetDetail;
  onDone: (datasetId: string) => void;
}) {
  const [kind, setKind] = useState(dataset.data_type),
    [unit, setUnit] = useState("auto"),
    [id, setId] = useState(""),
    [transpose, setTranspose] = useState(false),
    [busy, setBusy] = useState(false),
    [error, setError] = useState("");
  return (
    <details
      className="details"
      open={dataset.data_type === "table" ? true : undefined}
    >
      <summary>数据用途与格式</summary>
      <div className="form-grid">
        <label>
          用途
          <select
            value={kind}
            onChange={(e) => setKind(e.target.value as typeof kind)}
          >
            <option value="table">普通表格</option>
            <option value="metadata">样本与指标</option>
            <option value="taxonomy">物种丰度</option>
            <option value="functional">功能通路</option>
          </select>
        </label>
        {kind === "metadata" && (
          <label>
            样本编号列
            <select value={id} onChange={(e) => setId(e.target.value)}>
              <option value="">自动识别</option>
              {dataset.columns.map((c) => (
                <option key={c}>{c}</option>
              ))}
            </select>
          </label>
        )}
        {["taxonomy", "functional"].includes(kind) && (
          <>
            <label>
              单位
              <select value={unit} onChange={(e) => setUnit(e.target.value)}>
                <option value="auto">自动识别</option>
                <option value="fraction">比例</option>
                <option value="percent">百分比</option>
                <option value="counts">计数</option>
                <option value="other">其他标准化丰度</option>
              </select>
            </label>
            <label className="check-label">
              <input
                type="checkbox"
                checked={transpose}
                onChange={(e) => setTranspose(e.target.checked)}
              />
              每行是样本
            </label>
          </>
        )}
      </div>
      {error && (
        <p role="alert" className="form-error">
          {error}
        </p>
      )}
      <button
        className="secondary"
        disabled={busy}
        onClick={async () => {
          setBusy(true);
          try {
            await post(
              `/projects/${dataset.project_id}/datasets/${dataset.id}/reinterpret`,
              { kind, unit, id_column: id || null, transpose },
            );
            onDone(dataset.id);
          } catch (e) {
            setError((e as Error).message);
          } finally {
            setBusy(false);
          }
        }}
      >
        保存数据用途
      </button>
    </details>
  );
}
