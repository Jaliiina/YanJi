import { useEffect, useState } from "react";
import { ArrowRight, FileText, Plus, Settings2, Upload } from "lucide-react";
import { request } from "../api";
import { DataTable } from "../components/DataWorkspace";
import { UnderstandingPanel } from "../components/UnderstandingPanel";
import type { DatasetDetail } from "../types";
import type { WorkspacePageProps } from "./types";
const types = {
  taxonomy: "物种丰度表",
  functional: "功能通路表",
  metadata: "样本与指标表",
  table: "数据表",
};
export function DataPage({
  detail,
  setModal,
  setTab,
  refresh,
  openDataset,
  fileId,
  setFileId,
}: WorkspacePageProps) {
  const [file, setFile] = useState<DatasetDetail | null>(null),
    [error, setError] = useState("");
  const current =
    detail.datasets.find((d) => d.id === fileId) || detail.datasets[0];
  useEffect(() => {
    let live = true;
    setFile(null);
    setError("");
    if (current)
      request<DatasetDetail>(`/projects/${detail.id}/datasets/${current.id}`)
        .then((d) => live && setFile(d))
        .catch((e) => live && setError(e.message));
    return () => {
      live = false;
    };
  }, [detail.id, current?.id]);
  return (
    <>
      <div className="page-heading">
        <div>
          <h1>项目文件</h1>
        </div>
        <button className="primary" onClick={() => setModal("upload")}>
          <Plus size={16} />
          添加文件
        </button>
      </div>
      {!current ? (
        <section className="files-empty">
          <Upload size={35} />
          <h2>把这次研究要用的文件放进来</h2>
          <p>先查看内容，接下来再选择分析什么。</p>
          <button className="primary" onClick={() => setModal("upload")}>
            选择文件
          </button>
          <span>Excel、CSV、TSV、JSON 记录表</span>
        </section>
      ) : (
        <>
          <div className="file-browser">
            <nav aria-label="项目文件">
              {detail.datasets.map((d) => (
                <button
                  className={current.id === d.id ? "selected" : ""}
                  key={d.id}
                  onClick={() => setFileId(d.id)}
                >
                  <FileText size={18} />
                  <div>
                    <strong>{d.filename}</strong>
                    <span>
                      {d.transformations?.find((t) => t.sheet)?.sheet ||
                        types[d.data_type]}
                    </span>
                  </div>
                </button>
              ))}
            </nav>
            <section className="file-content" key={current.id}>
              <div className="file-content-head">
                <div>
                  <h2>{current.filename}</h2>
                  <span>
                    {types[current.data_type]} · {current.summary.rows || 0} 行
                    · {current.summary.columns || current.features} 列
                    {current.transformations?.find((t) => t.sheet)?.sheet &&
                      ` · ${current.transformations.find((t) => t.sheet)?.sheet}`}
                  </span>
                </div>
                <button
                  className="text-button"
                  onClick={() => openDataset(current.id)}
                >
                  <Settings2 size={16} />
                  读取设置
                </button>
              </div>
              {error ? (
                <p role="alert" className="form-error">
                  {error}
                </p>
              ) : file ? (
                <DataTable preview={file.preview} />
              ) : (
                <div className="loading-panel">正在读取表格…</div>
              )}
              <details className="file-notes">
                <summary>
                  补充背景或解释某一列 <span>选填</span>
                </summary>
                <UnderstandingPanel
                  pid={detail.id}
                  datasetId={current.id}
                  onSave={refresh}
                />
              </details>
            </section>
          </div>
          <div className="files-next">
            <span>文件放好后，告诉研迹你想研究什么。</span>
            <button className="primary" onClick={() => setTab("overview")}>
              下一步：开始分析 <ArrowRight size={16} />
            </button>
          </div>
        </>
      )}
    </>
  );
}
