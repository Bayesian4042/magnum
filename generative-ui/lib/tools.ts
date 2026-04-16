import { tool, jsonSchema } from "ai";
import { z } from "zod/v4";

const API_URL = process.env.PYTHON_API_URL ?? "http://localhost:8000";

// z.object({}) in Zod v4 serialises to type:"None" — use jsonSchema() for empty schemas.
const emptyParams = jsonSchema<Record<string, never>>({
  type: "object",
  properties: {},
});

export const tools = {
  get_technologies: tool({
    description:
      "Get the list of all technology names available in the S&OP pipeline. Call this first if you need to know valid tech names before calling other tools.",
    inputSchema: emptyParams,
    execute: async () => {
      const res = await fetch(`${API_URL}/api/data/technologies`);
      if (!res.ok) throw new Error(`API error ${res.status}`);
      return res.json();
    },
  }),

  get_season_readiness: tool({
    description:
      "Get the season readiness traffic-light status and bandwidth percentage for every technology. Returns green/yellow/red counts plus a row per tech. Use this when the user asks about season readiness, bandwidth, or which technologies are on track / at risk.",
    inputSchema: emptyParams,
    execute: async () => {
      const res = await fetch(`${API_URL}/api/data/season-readiness`);
      if (!res.ok) throw new Error(`API error ${res.status}`);
      return res.json();
    },
  }),

  get_rccp_data: tool({
    description:
      "Get the Rough Cut Capacity Plan — monthly supply, demand, projected inventory, Days on Hand (DOH), and MATDI for a specific technology. Use when the user asks about supply vs demand, inventory projection, or DOH for a particular tech.",
    inputSchema: z.object({
      tech: z
        .string()
        .describe(
          "The technology name exactly as returned by get_technologies, e.g. '48oz', 'Talenti', 'BJ PTS'."
        ),
    }),
    execute: async ({ tech }) => {
      const res = await fetch(
        `${API_URL}/api/data/rccp/${encodeURIComponent(tech)}`
      );
      if (!res.ok) throw new Error(`API error ${res.status}`);
      return res.json();
    },
  }),

  get_tonnage_by_site: tool({
    description:
      "Get monthly liton tonnage grouped by manufacturing site. Use when the user asks about production by plant, site tonnage, or manufacturing contributions.",
    inputSchema: emptyParams,
    execute: async () => {
      const res = await fetch(`${API_URL}/api/data/tonnage-by-site`);
      if (!res.ok) throw new Error(`API error ${res.status}`);
      return res.json();
    },
  }),

  get_pallet_position: tool({
    description:
      "Get the total pallet position across all technologies by month, including peak month and peak pallet count. Use when the user asks about pallets, storage capacity, or pallet planning.",
    inputSchema: emptyParams,
    execute: async () => {
      const res = await fetch(`${API_URL}/api/data/pallet-position`);
      if (!res.ok) throw new Error(`API error ${res.status}`);
      return res.json();
    },
  }),

  get_matdi_comparison: tool({
    description:
      "Get MATDI (Moving Annual Total Days of Inventory) projections compared to targets at the Apr, Aug, and Dec checkpoints for every technology. Use when the user asks about MATDI, inventory day targets, or checkpoint comparisons.",
    inputSchema: emptyParams,
    execute: async () => {
      const res = await fetch(`${API_URL}/api/data/matdi-comparison`);
      if (!res.ok) throw new Error(`API error ${res.status}`);
      return res.json();
    },
  }),

  get_summary_metrics: tool({
    description:
      "Get high-level KPIs for the full 2026 planning horizon: total demand, total supply, supply/demand ratio, peak inventory, number of technologies, and overall season readiness counts. Use for a quick overview or dashboard summary.",
    inputSchema: emptyParams,
    execute: async () => {
      const res = await fetch(`${API_URL}/api/data/summary-metrics`);
      if (!res.ok) throw new Error(`API error ${res.status}`);
      return res.json();
    },
  }),
};
