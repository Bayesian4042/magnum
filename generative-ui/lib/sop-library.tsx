"use client";

import { defineComponent, createLibrary, tagSchemaId } from "@openuidev/react-lang";
import { z } from "zod/v4";
import {
  BarChart as RechartsBarChart,
  Bar,
  LineChart as RechartsLineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
} from "recharts";

// ---------------------------------------------------------------------------
// Helper schemas
// ---------------------------------------------------------------------------

const StatusSchema = z.enum(["green", "yellow", "red", "neutral"]);
tagSchemaId(StatusSchema, "Status");

// ---------------------------------------------------------------------------
// MetricCard
// ---------------------------------------------------------------------------

const MetricCard = defineComponent({
  name: "MetricCard",
  description:
    "Displays a single KPI metric with a label, value, optional trend delta, and optional status colour (green/yellow/red/neutral).",
  props: z.object({
    label: z.string(),
    value: z.string(),
    delta: z.string().optional(),
    status: StatusSchema.optional(),
  }),
  component: ({ props }) => {
    const border: Record<string, string> = {
      green: "border-emerald-200 bg-emerald-50",
      yellow: "border-amber-200 bg-amber-50",
      red: "border-rose-200 bg-rose-50",
      neutral: "border-slate-200 bg-white",
    };
    const badge: Record<string, string> = {
      green: "text-emerald-700 bg-emerald-100",
      yellow: "text-amber-700 bg-amber-100",
      red: "text-rose-700 bg-rose-100",
      neutral: "text-slate-500 bg-slate-100",
    };
    const s = props.status ?? "neutral";
    return (
      <div className={`rounded-xl border p-5 flex flex-col gap-1.5 shadow-sm ${border[s]}`}>
        <span className="text-xs font-medium uppercase tracking-wider text-slate-400">
          {props.label}
        </span>
        <span className="text-2xl font-bold text-slate-800 leading-tight">
          {props.value}
        </span>
        {props.delta && (
          <span className={`text-xs font-semibold rounded-full px-2 py-0.5 self-start ${badge[s]}`}>
            {props.delta}
          </span>
        )}
      </div>
    );
  },
});

// ---------------------------------------------------------------------------
// MetricGrid
// ---------------------------------------------------------------------------

const MetricGrid = defineComponent({
  name: "MetricGrid",
  description:
    "Renders a responsive grid of MetricCard items (2–4 across). Use to show related KPIs side by side.",
  props: z.object({ items: z.array(MetricCard.ref) }),
  component: ({ props, renderNode }) => (
    <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
      {renderNode(props.items)}
    </div>
  ),
});

// ---------------------------------------------------------------------------
// TrafficLight
// ---------------------------------------------------------------------------

const TrafficLight = defineComponent({
  name: "TrafficLight",
  description:
    "Displays one technology's season readiness as a card with a colour-coded status pill and bandwidth percentage.",
  props: z.object({
    tech: z.string(),
    bandwidth: z.string().describe("Formatted percentage e.g. '12.4%'"),
    status: z.enum(["Green", "Yellow", "Red"]),
  }),
  component: ({ props }) => {
    const pill: Record<string, string> = {
      Green: "bg-emerald-100 text-emerald-700 border border-emerald-200",
      Yellow: "bg-amber-100 text-amber-700 border border-amber-200",
      Red: "bg-rose-100 text-rose-700 border border-rose-200",
    };
    const card: Record<string, string> = {
      Green: "border-emerald-200 bg-emerald-50/60",
      Yellow: "border-amber-200 bg-amber-50/60",
      Red: "border-rose-200 bg-rose-50/60",
    };
    return (
      <div className={`rounded-xl border p-4 flex flex-col items-center gap-2 text-center shadow-sm ${card[props.status]}`}>
        <span className="text-xs font-medium text-slate-600">{props.tech}</span>
        <span className="text-xl font-bold text-slate-800">{props.bandwidth}</span>
        <span className={`text-xs font-semibold rounded-full px-3 py-1 ${pill[props.status]}`}>
          {props.status}
        </span>
      </div>
    );
  },
});

// ---------------------------------------------------------------------------
// ReadinessGrid
// ---------------------------------------------------------------------------

const ReadinessGrid = defineComponent({
  name: "ReadinessGrid",
  description:
    "Renders a full season-readiness overview as a responsive grid of TrafficLight cards. Use when the user asks for season readiness or an overview of all technologies.",
  props: z.object({
    title: z.string().optional(),
    summary: z.object({ green: z.number(), yellow: z.number(), red: z.number() }).optional(),
    items: z.array(TrafficLight.ref),
  }),
  component: ({ props, renderNode }) => (
    <div className="flex flex-col gap-4">
      {props.title && (
        <h2 className="text-base font-semibold text-slate-800">{props.title}</h2>
      )}
      {props.summary && (
        <div className="flex gap-2 text-xs flex-wrap">
          <span className="px-3 py-1 rounded-full bg-emerald-100 text-emerald-700 font-semibold border border-emerald-200">
            ✓ {props.summary.green} Green
          </span>
          <span className="px-3 py-1 rounded-full bg-amber-100 text-amber-700 font-semibold border border-amber-200">
            ~ {props.summary.yellow} Yellow
          </span>
          <span className="px-3 py-1 rounded-full bg-rose-100 text-rose-700 font-semibold border border-rose-200">
            ✗ {props.summary.red} Red
          </span>
        </div>
      )}
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        {renderNode(props.items)}
      </div>
    </div>
  ),
});

// ---------------------------------------------------------------------------
// BarChart
// ---------------------------------------------------------------------------

const BarSeriesSchema = z.object({ key: z.string(), label: z.string(), color: z.string() });
tagSchemaId(BarSeriesSchema, "BarSeries");

const BarChartDataRowSchema = z.record(z.string(), z.union([z.string(), z.number()]));
tagSchemaId(BarChartDataRowSchema, "BarChartDataRow");

const BarChart = defineComponent({
  name: "BarChart",
  description:
    "Renders a grouped bar chart. Ideal for comparing supply vs demand, or tonnage by site across months.",
  props: z.object({
    title: z.string(),
    xKey: z.string().describe("The key in each data row to use as the X-axis (e.g. 'month')"),
    series: z.array(BarSeriesSchema),
    data: z.array(BarChartDataRowSchema),
    stacked: z.boolean().optional(),
  }),
  component: ({ props }) => (
    <div className="flex flex-col gap-3">
      <h3 className="text-sm font-semibold text-slate-700">{props.title}</h3>
      <ResponsiveContainer width="100%" height={280}>
        <RechartsBarChart data={props.data} margin={{ top: 4, right: 16, left: 0, bottom: 4 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
          <XAxis dataKey={props.xKey} tick={{ fill: "#94a3b8", fontSize: 11 }} />
          <YAxis
            tick={{ fill: "#94a3b8", fontSize: 11 }}
            tickFormatter={(v) =>
              v >= 1e6 ? `${(v / 1e6).toFixed(1)}M` : v >= 1000 ? `${(v / 1000).toFixed(0)}K` : v
            }
          />
          <Tooltip
            contentStyle={{ backgroundColor: "#fff", border: "1px solid #e2e8f0", borderRadius: 8, boxShadow: "0 4px 6px -1px rgb(0 0 0 / 0.07)" }}
            labelStyle={{ color: "#1e293b", fontWeight: 600, fontSize: 12 }}
          />
          <Legend wrapperStyle={{ color: "#64748b", fontSize: 12 }} />
          {props.series.map((s) => (
            <Bar
              key={s.key}
              dataKey={s.key}
              name={s.label}
              fill={s.color}
              stackId={props.stacked ? "stack" : undefined}
              radius={props.stacked ? undefined : [3, 3, 0, 0]}
            />
          ))}
        </RechartsBarChart>
      </ResponsiveContainer>
    </div>
  ),
});

// ---------------------------------------------------------------------------
// LineChart
// ---------------------------------------------------------------------------

const LineSeriesSchema = z.object({
  key: z.string(),
  label: z.string(),
  color: z.string(),
  dashed: z.boolean().optional(),
});
tagSchemaId(LineSeriesSchema, "LineSeries");

const LineChart = defineComponent({
  name: "LineChart",
  description:
    "Renders a line chart for trends over time. Use for inventory projections, DOH trends, MATDI, or bandwidth over months.",
  props: z.object({
    title: z.string(),
    xKey: z.string(),
    series: z.array(LineSeriesSchema),
    data: z.array(BarChartDataRowSchema),
  }),
  component: ({ props }) => (
    <div className="flex flex-col gap-3">
      <h3 className="text-sm font-semibold text-slate-700">{props.title}</h3>
      <ResponsiveContainer width="100%" height={260}>
        <RechartsLineChart data={props.data} margin={{ top: 4, right: 16, left: 0, bottom: 4 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
          <XAxis dataKey={props.xKey} tick={{ fill: "#94a3b8", fontSize: 11 }} />
          <YAxis
            tick={{ fill: "#94a3b8", fontSize: 11 }}
            tickFormatter={(v) =>
              v >= 1e6 ? `${(v / 1e6).toFixed(1)}M` : v >= 1000 ? `${(v / 1000).toFixed(0)}K` : String(v)
            }
          />
          <Tooltip
            contentStyle={{ backgroundColor: "#fff", border: "1px solid #e2e8f0", borderRadius: 8, boxShadow: "0 4px 6px -1px rgb(0 0 0 / 0.07)" }}
            labelStyle={{ color: "#1e293b", fontWeight: 600, fontSize: 12 }}
          />
          <Legend wrapperStyle={{ color: "#64748b", fontSize: 12 }} />
          {props.series.map((s) => (
            <Line
              key={s.key}
              type="monotone"
              dataKey={s.key}
              name={s.label}
              stroke={s.color}
              strokeWidth={2}
              strokeDasharray={s.dashed ? "6 3" : undefined}
              dot={{ r: 3 }}
            />
          ))}
        </RechartsLineChart>
      </ResponsiveContainer>
    </div>
  ),
});

// ---------------------------------------------------------------------------
// DataTable
// ---------------------------------------------------------------------------

const DataTableColumnSchema = z.object({
  key: z.string(),
  label: z.string(),
  align: z.enum(["left", "right", "center"]).optional(),
});
tagSchemaId(DataTableColumnSchema, "DataTableColumn");

const DataTable = defineComponent({
  name: "DataTable",
  description:
    "Renders a clean data table with custom columns and rows. Use for MATDI comparisons, monthly breakdowns, or structured data.",
  props: z.object({
    title: z.string().optional(),
    columns: z.array(DataTableColumnSchema),
    rows: z.array(z.record(z.string(), z.union([z.string(), z.number(), z.null()]))),
    caption: z.string().optional(),
  }),
  component: ({ props }) => (
    <div className="flex flex-col gap-2">
      {props.title && (
        <h3 className="text-sm font-semibold text-slate-700">{props.title}</h3>
      )}
      <div className="overflow-x-auto rounded-xl border border-slate-200 shadow-sm">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-slate-200 bg-slate-50">
              {props.columns.map((col) => (
                <th
                  key={col.key}
                  className={`px-4 py-2.5 font-semibold text-slate-500 text-${col.align ?? "left"} text-xs uppercase tracking-wide`}
                >
                  {col.label}
                </th>
              ))}
            </tr>
          </thead>
          <tbody className="bg-white">
            {props.rows.map((row, i) => (
              <tr
                key={i}
                className="border-b border-slate-100 last:border-0 hover:bg-slate-50 transition-colors"
              >
                {props.columns.map((col) => {
                  const val = row[col.key];
                  const isStatus = col.key === "status";
                  const cellClass = `px-4 py-2.5 text-slate-700 text-${col.align ?? "left"} text-sm`;
                  let display: React.ReactNode = val == null ? "—" : String(val);

                  if (isStatus && typeof val === "string") {
                    const statusStyle: Record<string, string> = {
                      "On Track": "px-2 py-0.5 rounded-full bg-emerald-100 text-emerald-700 text-xs font-semibold border border-emerald-200",
                      "At Risk":  "px-2 py-0.5 rounded-full bg-rose-100 text-rose-700 text-xs font-semibold border border-rose-200",
                      "Green":    "px-2 py-0.5 rounded-full bg-emerald-100 text-emerald-700 text-xs font-semibold border border-emerald-200",
                      "Yellow":   "px-2 py-0.5 rounded-full bg-amber-100 text-amber-700 text-xs font-semibold border border-amber-200",
                      "Red":      "px-2 py-0.5 rounded-full bg-rose-100 text-rose-700 text-xs font-semibold border border-rose-200",
                    };
                    display = <span className={statusStyle[val] ?? ""}>{val}</span>;
                  }
                  return <td key={col.key} className={cellClass}>{display}</td>;
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {props.caption && <p className="text-xs text-slate-400">{props.caption}</p>}
    </div>
  ),
});

// ---------------------------------------------------------------------------
// SectionHeader
// ---------------------------------------------------------------------------

const SectionHeader = defineComponent({
  name: "SectionHeader",
  description: "Renders a section title with an optional subtitle. Use to visually separate sections of a multi-part response.",
  props: z.object({ title: z.string(), subtitle: z.string().optional() }),
  component: ({ props }) => (
    <div className="flex flex-col gap-0.5">
      <h2 className="text-base font-semibold text-slate-800">{props.title}</h2>
      {props.subtitle && <p className="text-sm text-slate-500">{props.subtitle}</p>}
    </div>
  ),
});

// ---------------------------------------------------------------------------
// TextBlock
// ---------------------------------------------------------------------------

const TextBlock = defineComponent({
  name: "TextBlock",
  description: "Renders a plain-text paragraph or narrative summary. Use for explanations, caveats, or contextual notes alongside charts and tables.",
  props: z.object({ content: z.string() }),
  component: ({ props }) => (
    <p className="text-sm leading-relaxed text-slate-500">{props.content}</p>
  ),
});

// ---------------------------------------------------------------------------
// Stack — root layout container
// ---------------------------------------------------------------------------

const Stack = defineComponent({
  name: "Stack",
  description:
    "Vertical layout container. Every response MUST start with Stack as the root. Place all content as children of Stack.",
  props: z.object({
    children: z.array(
      z.union([
        MetricGrid.ref,
        MetricCard.ref,
        ReadinessGrid.ref,
        TrafficLight.ref,
        BarChart.ref,
        LineChart.ref,
        DataTable.ref,
        SectionHeader.ref,
        TextBlock.ref,
      ])
    ),
  }),
  component: ({ props, renderNode }) => (
    <div className="flex flex-col gap-8 w-full">
      {renderNode(props.children)}
    </div>
  ),
});

// ---------------------------------------------------------------------------
// Library assembly
// ---------------------------------------------------------------------------

export const sopLibrary = createLibrary({
  root: "Stack",
  components: [
    Stack,
    MetricCard,
    MetricGrid,
    TrafficLight,
    ReadinessGrid,
    BarChart,
    LineChart,
    DataTable,
    SectionHeader,
    TextBlock,
  ],
  componentGroups: [
    {
      name: "Layout",
      components: ["Stack", "SectionHeader", "TextBlock"],
      notes: [
        "- Every response MUST start with: root = Stack([...])",
        "- Use SectionHeader before major sections.",
        "- Use TextBlock for narrative paragraphs and caveats.",
      ],
    },
    {
      name: "KPI Metrics",
      components: ["MetricCard", "MetricGrid"],
      notes: [
        "- Use MetricGrid to show 2–4 related KPIs side by side.",
        "- status must be 'green', 'yellow', 'red', or 'neutral'.",
        "- Format values as human-readable strings: '1.2M cases', '45.0 days', '12.4%'.",
      ],
    },
    {
      name: "Season Readiness",
      components: ["TrafficLight", "ReadinessGrid"],
      notes: [
        "- Use ReadinessGrid when showing all technologies' readiness at once.",
        "- TrafficLight status is 'Green', 'Yellow', or 'Red' (capitalised).",
        "- Include summary counts in ReadinessGrid when available.",
      ],
    },
    {
      name: "Charts",
      components: ["BarChart", "LineChart"],
      notes: [
        "- BarChart: use for supply vs demand comparisons and tonnage by site.",
        "- LineChart: use for inventory trends, DOH over time, MATDI trends.",
        "- Colors: supply='#6366f1', demand='#f59e0b', inventory='#10b981', doh='#8b5cf6', target='#ef4444'.",
        "- Format month as 'YYYY-MM' for xKey.",
        "- Inline data directly in the chart — do NOT reference external variables.",
      ],
    },
    {
      name: "Tables",
      components: ["DataTable"],
      notes: [
        "- Use for MATDI vs target, monthly breakdowns, and validation tables.",
        "- Set align 'right' for numeric columns.",
        "- Use null for missing values (rendered as '—').",
        "- The 'status' column gets automatic colour-coded pills.",
      ],
    },
  ],
});
