import { useEffect, useState } from "react";

import { Activity, LoaderCircle, Sparkles } from "lucide-react";
import { post, request } from "../api";

export function SettingsPanel() {
  const [settings, setSettings] = useState<{
      model: string;
      base_url: string;
      configured: boolean;
    } | null>(null),
    [busy, setBusy] = useState(false),
    [message, setMessage] = useState("");
  useEffect(() => {
    request<typeof settings>("/settings/model").then(setSettings);
  }, []);
  const [literature, setLiterature] = useState<{
    configured: boolean;
    url: string;
    kind: string;
  } | null>(null);
  useEffect(() => {
    request<{ configured: boolean; url: string; kind: string }>(
      "/settings/literature",
    ).then(setLiterature);
  }, []);
  return (
    <>
      <div className="connection-card">
        <span className="task-icon">
          <Sparkles size={22} />
        </span>
        <div>
          <strong>{settings?.model || "正在读取配置…"}</strong>
          <p>{settings?.configured ? "已读取本地密钥" : "尚未配置密钥"}</p>
        </div>
        <span className="badge">文本模型</span>
      </div>
      <label>
        接口地址
        <input readOnly value={settings?.base_url || ""} />
      </label>
      <p className="muted">
        在项目根目录 .env 中设置 api_key、base_url 和
        model。无需将密钥输入浏览器；修改后再次测试即可。
      </p>
      <button
        className="primary"
        disabled={busy}
        onClick={async () => {
          setBusy(true);
          setMessage("");
          try {
            const d = await post<{ ok: boolean; model: string }>(
              "/settings/model/test",
            );
            setMessage(
              d.ok
                ? "连接成功，文本与 JSON 接口可用。"
                : "模型响应未符合预期。",
            );
          } catch (e) {
            setMessage((e as Error).message);
          } finally {
            setBusy(false);
          }
        }}
      >
        {busy ? (
          <LoaderCircle className="spin" size={16} />
        ) : (
          <Activity size={16} />
        )}
        测试连接
      </button>
      {message && <p className="connection-message">{message}</p>}
      <section className="literature-settings">
        <h3>文献服务</h3>
        <p>{literature?.configured ? literature.url : "尚未连接"}</p>
        <details className="details">
          <summary>接入方式</summary>
          <p>
            在 .env 中设置 literature_url。通用接口为 POST /search 和 GET
            /papers/文献编号；如使用 BioFlow 文献库，设置
            literature_kind=localbase 和 literature_kb。凭据使用
            literature_api_key。
          </p>
        </details>
      </section>
      <div className="hint">
        数值计算在本地执行。规划与解释时会向该服务发送研究目标、数据摘要及必要结果，请使用你有权处理的数据。
      </div>
    </>
  );
}
