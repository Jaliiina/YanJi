import { useEffect, useState } from "react";
import { ArrowRight } from "lucide-react";
import type { Clarification, Dataset } from "../types";

type Draft = {
  dataset_id: string;
  field: string;
  unit: string;
  unknown_unit: boolean;
  order: string[];
  picked: string;
  text: string;
  values: string[];
  mapping: Record<string, string>;
};

export type ClarifyAnswer = {
  id: string;
  dataset_id: string | null;
  field: string | null;
  unit: string;
  encoding: string;
  unknown_unit: boolean;
  text: string;
  picked: string[];
  mapping: Record<string, string>;
};

const titles: Record<Clarification["kind"], string> = {
  bind_field: "对应哪一列",
  unit: "单位",
  encoding: "等级顺序",
  choice: "请选择",
  text: "请说明",
  select: "请选择",
  samples: "样本对应",
};

function token(dataset_id: string, field: string) {
  return `${dataset_id}::${field}`;
}

export function ClarifyForm({
  datasets,
  cards,
  busy,
  onSubmit,
  onOpenFiles,
}: {
  datasets: Dataset[];
  cards: Clarification[];
  busy: boolean;
  onSubmit: (answers: ClarifyAnswer[]) => void;
  onOpenFiles: () => void;
}) {
  const [drafts, setDrafts] = useState<Record<string, Draft>>({});
  useEffect(() => {
    setDrafts(
      Object.fromEntries(
        cards.map((card) => [
          card.id,
          {
            dataset_id: card.dataset_id || "",
            field: card.field || "",
            unit: "",
            unknown_unit: false,
            order: [],
            picked: "",
            text: "",
            values: [],
            // A sample starts on the record suggested for it, if there is one.
            mapping: Object.fromEntries(
              (card.kind === "samples" ? card.items || [] : [])
                .filter((item) => item.hint)
                .map((item) => [item.value, item.hint]),
            ),
          },
        ]),
      ),
    );
  }, [cards]);
  function update(id: string, patch: Partial<Draft>) {
    setDrafts((current) => ({
      ...current,
      [id]: { ...current[id], ...patch },
    }));
  }
  const severalFiles =
    new Set(
      cards.flatMap((card) =>
        (card.options || []).map((option) => option.dataset_id),
      ),
    ).size > 1;
  function optionLabel(dataset_id: string, field: string) {
    const name = datasets.find((dataset) => dataset.id === dataset_id)?.filename;
    return severalFiles && name ? `${name} · ${field}` : field;
  }
  // A unit or order question that belongs to a research phrase follows the column chosen for it.
  function bound(card: Clarification) {
    if (card.kind === "bind_field" || !card.concept) return undefined;
    const source = cards.find(
      (item) => item.kind === "bind_field" && item.concept === card.concept,
    );
    return source ? { source, draft: drafts[source.id] } : undefined;
  }
  function target(card: Clarification) {
    const draft = drafts[card.id];
    const follow = bound(card);
    return card.kind === "bind_field"
      ? { dataset_id: draft.dataset_id, field: draft.field }
      : {
          dataset_id:
            follow?.draft?.dataset_id || card.dataset_id || draft.dataset_id,
          field: follow?.draft?.field || card.field || draft.field,
        };
  }
  function levels(card: Clarification) {
    const follow = bound(card);
    const at = target(card);
    const option = (follow?.source.options || card.options || []).find(
      (item) => item.dataset_id === at.dataset_id && item.field === at.field,
    );
    return option?.values?.length ? option.values : card.values || [];
  }
  const incomplete = cards.some((card) => {
    const draft = drafts[card.id];
    if (!draft) return true;
    if (card.kind === "bind_field") return !draft.field;
    if (card.kind === "unit") return !draft.unit.trim() && !draft.unknown_unit;
    if (card.kind === "select")
      return (
        draft.values.length < (card.min_pick || 1) ||
        draft.values.length > (card.max_pick || 1)
      );
    if (card.kind === "text" && card.required) return !draft.text.trim();
    return false;
  });
  function toggle(card: Clarification, value: string) {
    const current = drafts[card.id].values;
    const most = card.max_pick || 1;
    update(card.id, {
      values: current.includes(value)
        ? current.filter((item) => item !== value)
        : most === 1
          ? [value]
          : current.length < most
            ? [...current, value]
            : current,
    });
  }
  return (
    <div className="plan-questions">
      <h3>还有几项需要补充</h3>
      <p>在这里回答，方案会按你的回答更新。</p>
      {cards.map((card) => {
        const draft = drafts[card.id];
        if (!draft) return null;
        return (
          <article className="clarify-card" key={card.id}>
            <h4>{titles[card.kind]}</h4>
            <p>{card.prompt}</p>
            {card.kind === "bind_field" && (
              <label>
                使用的列
                <select
                  aria-label={`${card.concept || "这一项"}使用的列`}
                  value={
                    draft.field ? token(draft.dataset_id, draft.field) : ""
                  }
                  onChange={(event) => {
                    const [dataset_id = "", field = ""] =
                      event.target.value.split("::");
                    update(card.id, { dataset_id, field });
                    cards
                      .filter(
                        (item) =>
                          item.kind === "encoding" &&
                          !!item.concept &&
                          item.concept === card.concept,
                      )
                      .forEach((item) => update(item.id, { order: [] }));
                  }}
                >
                  <option value="">请选择</option>
                  {(card.options || []).map((option) => (
                    <option
                      key={token(option.dataset_id, option.field)}
                      value={token(option.dataset_id, option.field)}
                    >
                      {optionLabel(option.dataset_id, option.field)}
                    </option>
                  ))}
                </select>
              </label>
            )}
            {card.kind === "unit" && (
              <div className="clarify-unit">
                <label>
                  单位
                  <input
                    aria-label={`${card.field || card.concept}的单位`}
                    value={draft.unit}
                    disabled={draft.unknown_unit}
                    placeholder="例如：岁、mg/L"
                    onChange={(event) =>
                      update(card.id, { unit: event.target.value })
                    }
                  />
                </label>
                <label className="check-line">
                  <input
                    type="checkbox"
                    checked={draft.unknown_unit}
                    onChange={(event) =>
                      update(card.id, {
                        unknown_unit: event.target.checked,
                        unit: event.target.checked ? "" : draft.unit,
                      })
                    }
                  />
                  单位未知，按原始数值描述
                </label>
              </div>
            )}
            {card.kind === "encoding" && (
              <div>
                <div className="choice-chips">
                  {levels(card).map((value) => {
                    const index = draft.order.indexOf(value);
                    return (
                      <button
                        type="button"
                        key={value}
                        className={index >= 0 ? "selected" : ""}
                        onClick={() =>
                          update(card.id, {
                            order:
                              index >= 0
                                ? draft.order.filter((item) => item !== value)
                                : [...draft.order, value],
                          })
                        }
                      >
                        {index >= 0 ? `${index + 1}. ${value}` : value}
                      </button>
                    );
                  })}
                </div>
                <p className="clarify-order">
                  {draft.order.length
                    ? `当前顺序：${draft.order.join(" > ")}`
                    : "依次点选来排顺序。不点选表示没有固定顺序。"}
                </p>
              </div>
            )}
            {card.kind === "choice" && (
              <div className="choice-chips">
                {(card.choices || []).map((value) => (
                  <button
                    type="button"
                    key={value}
                    aria-pressed={draft.picked === value}
                    className={draft.picked === value ? "selected" : ""}
                    onClick={() =>
                      update(card.id, {
                        picked: draft.picked === value ? "" : value,
                      })
                    }
                  >
                    {value}
                  </button>
                ))}
              </div>
            )}
            {card.kind === "select" &&
              ((card.items || []).length > 8 && (card.max_pick || 1) === 1 ? (
                <label>
                  选择一项
                  <select
                    aria-label={card.prompt}
                    value={draft.values[0] || ""}
                    onChange={(event) =>
                      update(card.id, {
                        values: event.target.value ? [event.target.value] : [],
                      })
                    }
                  >
                    <option value="">请选择</option>
                    {(card.items || []).map((item) => (
                      <option key={item.value} value={item.value}>
                        {item.label || item.value}
                      </option>
                    ))}
                  </select>
                </label>
              ) : (
                <div
                  className="choice-chips"
                  role="group"
                  aria-label={card.prompt}
                >
                  {(card.items || []).map((item) => (
                    <button
                      type="button"
                      key={item.value}
                      aria-pressed={draft.values.includes(item.value)}
                      className={
                        draft.values.includes(item.value) ? "selected" : ""
                      }
                      onClick={() => toggle(card, item.value)}
                    >
                      {item.label || item.value}
                    </button>
                  ))}
                </div>
              ))}
            {card.kind === "samples" &&
              (card.items || []).map((item) => {
                const taken = Object.entries(draft.mapping)
                  .filter(([sample, to]) => sample !== item.value && to)
                  .map(([, to]) => to);
                return (
                  <label className="sample-match" key={item.value}>
                    <span>{item.value}</span>
                    <select
                      aria-label={`${item.value} 对应的记录`}
                      value={draft.mapping[item.value] || ""}
                      onChange={(event) =>
                        update(card.id, {
                          mapping: {
                            ...draft.mapping,
                            [item.value]: event.target.value,
                          },
                        })
                      }
                    >
                      <option value="">本次不纳入</option>
                      {(card.choices || [])
                        .filter((name) => !taken.includes(name))
                        .map((name) => (
                          <option key={name} value={name}>
                            对应 {name}
                          </option>
                        ))}
                    </select>
                  </label>
                );
              })}
            {card.action === "data" && (
              <button
                type="button"
                className="text-button"
                onClick={onOpenFiles}
              >
                去项目文件查看或添加
              </button>
            )}
            {(card.kind === "choice" || card.kind === "text") && (
              <label>
                {card.kind === "choice"
                  ? "补充说明（选填）"
                  : card.required
                    ? "你的说明"
                    : "你的回答"}
                <textarea
                  rows={2}
                  aria-label={`回答：${card.prompt}`}
                  value={draft.text}
                  placeholder={
                    card.kind === "choice"
                      ? "选项都不合适时，在这里写明"
                      : card.required
                        ? "例如：改成描述性分析"
                        : "不确定可以留空，方案会采用保守做法并说明"
                  }
                  onChange={(event) =>
                    update(card.id, { text: event.target.value })
                  }
                />
              </label>
            )}
          </article>
        );
      })}
      <button
        className="primary"
        disabled={busy || incomplete}
        onClick={() =>
          onSubmit(
            cards.map((card) => {
              const draft = drafts[card.id];
              const at = target(card);
              return {
                id: card.id,
                dataset_id: at.dataset_id || null,
                field: at.field || null,
                unit: draft.unit.trim(),
                encoding:
                  card.kind === "encoding" ? draft.order.join(" > ") : "",
                unknown_unit: draft.unknown_unit,
                text: [draft.picked, draft.text.trim()]
                  .filter(Boolean)
                  .join("；"),
                picked: draft.values,
                mapping: Object.fromEntries(
                  Object.entries(draft.mapping).filter(([, to]) => to),
                ),
              };
            }),
          )
        }
      >
        <ArrowRight size={16} />
        按这些回答更新方案
      </button>
    </div>
  );
}
