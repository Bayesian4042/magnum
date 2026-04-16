/**
 * Run once (or as part of `pnpm dev` / `pnpm build`) to write the OpenUI
 * system prompt to a plain text file that the API route can readFileSync.
 *
 *   pnpm tsx scripts/generate-prompt.ts
 */

import fs from "fs";
import path from "path";

// Dynamic import so we can run this outside the Next.js context.
// We import from the client library because we need the real defineComponent.
import { defineComponent, createLibrary, tagSchemaId } from "@openuidev/react-lang";
import { z } from "zod/v4";

// ---------------------------------------------------------------------------
// Schema-only stubs (no React renderers needed for prompt generation)
// ---------------------------------------------------------------------------

const stub = () => null as never;

const StatusSchema = z.enum(["green", "yellow", "red", "neutral"]);
tagSchemaId(StatusSchema, "Status");

const BarSeriesSchema = z.object({ key: z.string(), label: z.string(), color: z.string() });
tagSchemaId(BarSeriesSchema, "BarSeries");

const LineSeriesSchema = z.object({ key: z.string(), label: z.string(), color: z.string(), dashed: z.boolean().optional() });
tagSchemaId(LineSeriesSchema, "LineSeries");

const DataRowSchema = z.record(z.string(), z.union([z.string(), z.number()]));
tagSchemaId(DataRowSchema, "DataRow");

const DataTableColumnSchema = z.object({ key: z.string(), label: z.string(), align: z.enum(["left", "right", "center"]).optional() });
tagSchemaId(DataTableColumnSchema, "DataTableColumn");

const MetricCard = defineComponent({ name: "MetricCard", description: "Displays a single KPI metric with a label, value, optional trend delta, and optional status colour (green/yellow/red/neutral).", props: z.object({ label: z.string(), value: z.string(), delta: z.string().optional(), status: StatusSchema.optional() }), component: stub });
const MetricGrid = defineComponent({ name: "MetricGrid", description: "Renders a responsive grid of MetricCard items (2–4 across). Use to show related KPIs side by side.", props: z.object({ items: z.array(MetricCard.ref) }), component: stub });
const TrafficLight = defineComponent({ name: "TrafficLight", description: "Displays one technology's season readiness as a card with a colour-coded status pill and bandwidth percentage.", props: z.object({ tech: z.string(), bandwidth: z.string().describe("Formatted percentage e.g. '12.4%'"), status: z.enum(["Green", "Yellow", "Red"]) }), component: stub });
const ReadinessGrid = defineComponent({ name: "ReadinessGrid", description: "Renders a full season-readiness overview as a responsive grid of TrafficLight cards. Use when the user asks for season readiness or an overview of all technologies.", props: z.object({ title: z.string().optional(), summary: z.object({ green: z.number(), yellow: z.number(), red: z.number() }).optional(), items: z.array(TrafficLight.ref) }), component: stub });
const BarChart = defineComponent({ name: "BarChart", description: "Renders a grouped bar chart. Ideal for comparing supply vs demand, or tonnage by site across months.", props: z.object({ title: z.string(), xKey: z.string().describe("Key for X-axis (e.g. 'month')"), series: z.array(BarSeriesSchema), data: z.array(DataRowSchema), stacked: z.boolean().optional() }), component: stub });
const LineChart = defineComponent({ name: "LineChart", description: "Renders a line chart for trends over time. Use for inventory projections, DOH trends, MATDI, or bandwidth over months.", props: z.object({ title: z.string(), xKey: z.string(), series: z.array(LineSeriesSchema), data: z.array(DataRowSchema) }), component: stub });
const DataTable = defineComponent({ name: "DataTable", description: "Renders a clean data table. Use for MATDI comparisons, monthly breakdowns, or structured data.", props: z.object({ title: z.string().optional(), columns: z.array(DataTableColumnSchema), rows: z.array(z.record(z.string(), z.union([z.string(), z.number(), z.null()]))), caption: z.string().optional() }), component: stub });
const SectionHeader = defineComponent({ name: "SectionHeader", description: "Renders a section title with an optional subtitle. Use to visually separate sections.", props: z.object({ title: z.string(), subtitle: z.string().optional() }), component: stub });
const TextBlock = defineComponent({ name: "TextBlock", description: "Renders a plain-text paragraph or narrative summary. Use for explanations, caveats, or contextual notes.", props: z.object({ content: z.string() }), component: stub });
const Stack = defineComponent({
  name: "Stack",
  description: "Vertical layout container. Every response MUST start with Stack as the root. Place all content as children of Stack.",
  props: z.object({ children: z.array(z.union([MetricGrid.ref, MetricCard.ref, ReadinessGrid.ref, TrafficLight.ref, BarChart.ref, LineChart.ref, DataTable.ref, SectionHeader.ref, TextBlock.ref])) }),
  component: stub,
});

const library = createLibrary({
  root: "Stack",
  components: [Stack, MetricCard, MetricGrid, TrafficLight, ReadinessGrid, BarChart, LineChart, DataTable, SectionHeader, TextBlock],
  componentGroups: [
    { name: "Layout", components: ["Stack", "SectionHeader", "TextBlock"], notes: ["- Every response MUST start with: root = Stack([...])", "- Use SectionHeader before major sections.", "- Use TextBlock for narrative paragraphs and caveats."] },
    { name: "KPI Metrics", components: ["MetricCard", "MetricGrid"], notes: ["- Use MetricGrid to show 2–4 related KPIs side by side.", "- status must be 'green', 'yellow', 'red', or 'neutral'.", "- Format values as human-readable strings: '1.2M cases', '45.0 days', '12.4%'."] },
    { name: "Season Readiness", components: ["TrafficLight", "ReadinessGrid"], notes: ["- Use ReadinessGrid when showing all technologies' readiness at once.", "- TrafficLight status is 'Green', 'Yellow', or 'Red' (capitalised).", "- Include summary counts in ReadinessGrid when available."] },
    { name: "Charts", components: ["BarChart", "LineChart"], notes: ["- BarChart: use for supply vs demand comparisons and tonnage by site.", "- LineChart: use for inventory trends, DOH over time, MATDI trends.", "- Colors: supply='#6366f1', demand='#f59e0b', inventory='#10b981', doh='#8b5cf6', target='#ef4444'.", "- Format month as 'YYYY-MM' for xKey.", "- Inline data directly in the component — do NOT reference external variables."] },
    { name: "Tables", components: ["DataTable"], notes: ["- Use for MATDI vs target, monthly breakdowns, and validation tables.", "- Set align 'right' for numeric columns.", "- Use null for missing values (rendered as '—').", "- The 'status' column gets automatic colour-coded pills."] },
  ],
});

const systemPrompt = library.prompt({
  preamble: `You are a smart S&OP (Sales & Operations Planning) assistant for the Magnum ice cream brand's MRF3 2026 planning cycle.

You help operations planners quickly understand supply, demand, inventory, and season readiness data by generating interactive dashboard views in response to natural language questions.

ALWAYS call the appropriate data tool(s) before generating UI — never make up numbers.
ALWAYS output valid OpenUI Lang — start every response with: root = Stack([...])
Use the data returned by tools to populate chart data, table rows, and metric values inline.

Key concepts:
- Technologies: product size buckets (48oz, Talenti, BJ PTS, MG Sticks, etc.)
- Bandwidth: (excess inventory above DOH target) / season demand — higher is better
- MATDI: Moving Annual Total Days of Inventory — checkpoint targets at Apr, Aug, Dec
- DOH: Days on Hand — target is 45 days
- Season: May–September is peak demand season`,

  additionalRules: [
    "Always call at least one tool to fetch real data before responding.",
    "Format large numbers as human-readable strings: 1,234,567 → '1.2M cases'.",
    "For bandwidth, format as percentage: 0.124 → '12.4%'.",
    "When showing RCCP data, always include both a BarChart (supply vs demand) and a LineChart (inventory + DOH).",
    "Use status 'green'/'yellow'/'red' for MetricCard, and 'Green'/'Yellow'/'Red' (capitalised) for TrafficLight.",
    "If the user asks about a specific tech, call get_rccp_data. If about all techs, call get_season_readiness.",
    "Include a TextBlock with a 1–2 sentence narrative summary at the end of multi-section responses.",
  ],

  examples: [
    `# Season readiness overview
root = Stack([header, summary, grid, note])
header = SectionHeader("Season Readiness Overview", "MRF3 2026 — all technologies")
summary = MetricGrid([g, y, r])
g = MetricCard("On Track", "14 technologies", null, "green")
y = MetricCard("Watch", "3 technologies", null, "yellow")
r = MetricCard("At Risk", "2 technologies", null, "red")
grid = ReadinessGrid(null, {green: 14, yellow: 3, red: 2}, [t1, t2])
t1 = TrafficLight("48oz", "12.4%", "Green")
t2 = TrafficLight("Talenti", "8.1%", "Yellow")
note = TextBlock("Most technologies are on track for the 2026 season. Talenti and MG Sticks require monitoring.")`,
  ],
});

// ---------------------------------------------------------------------------
// Write to generated/system-prompt.txt
// ---------------------------------------------------------------------------

const outDir = path.join(process.cwd(), "generated");
fs.mkdirSync(outDir, { recursive: true });
const outFile = path.join(outDir, "system-prompt.txt");
fs.writeFileSync(outFile, systemPrompt, "utf-8");

console.log(`✓ System prompt written to ${outFile} (${systemPrompt.length} chars)`);
