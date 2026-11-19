import { ArrowRight } from "lucide-react";
import { Workflow } from "../components/Workflow";
import type { WorkspacePageProps } from "./types";
export function OverviewPage(props: WorkspacePageProps) {
  return (
    <>
      <div className="page-heading">
        <h1>开始分析</h1>
        <button className="text-button" onClick={() => props.setTab("data")}>
          查看项目文件 <ArrowRight size={16} />
        </button>
      </div>
      <div className="workspace-switch">
        <button className="selected">描述研究问题</button>
        <button onClick={() => props.setTab("skills")}>选择分析工具</button>
      </div>
      {props.detail.datasets.length ? (
        <Workflow {...props} />
      ) : (
        <div className="files-empty">
          <h2>先添加这次研究的文件</h2>
          <p>看到文件内容后，研迹才能根据实际数据设计分析。</p>
          <button className="primary" onClick={() => props.setModal("upload")}>
            添加文件
          </button>
        </div>
      )}
    </>
  );
}
