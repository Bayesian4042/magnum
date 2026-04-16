"use client";

import { useChat } from "@ai-sdk/react";
import { DefaultChatTransport } from "ai";
import { Renderer } from "@openuidev/react-lang";
import { sopLibrary } from "@/lib/sop-library";
import { useRef, useEffect, useState, useCallback } from "react";

const SUGGESTED_QUERIES = [
  "Show me the season readiness overview",
  "Supply vs demand for 48oz this year",
  "Which technologies are at risk?",
  "MATDI projections vs targets",
  "Tonnage by manufacturing site",
  "Give me a full dashboard summary",
];

const PYTHON_API = process.env.NEXT_PUBLIC_PYTHON_API_URL ?? "http://localhost:8000";

function buildSlideSpec(messages: Array<{ role: string; parts: Array<{ type: string; toolInvocation?: { toolName: string; args?: Record<string, unknown> } }> }>): string[] {
  const slides: string[] = [];
  const seen = new Set<string>();

  for (const msg of messages) {
    if (msg.role !== "assistant") continue;
    for (const part of msg.parts) {
      if (part.type !== "tool-invocation" || !part.toolInvocation) continue;
      const { toolName, args } = part.toolInvocation;

      if ((toolName === "get_season_readiness" || toolName === "get_summary_metrics") && !seen.has("season_readiness")) {
        slides.push("season_readiness", "tech_summary");
        seen.add("season_readiness");
        seen.add("tech_summary");
      }
      if (toolName === "get_rccp_data" && args?.tech) {
        const key = `rccp:${args.tech}`;
        if (!seen.has(key)) {
          slides.push(key);
          seen.add(key);
        }
      }
      if (toolName === "get_matdi_comparison" && !seen.has("matdi")) {
        slides.push("matdi");
        seen.add("matdi");
      }
      if (toolName === "get_tonnage_by_site" && !seen.has("site_tonnage")) {
        slides.push("site_tonnage");
        seen.add("site_tonnage");
      }
    }
  }
  return slides;
}

// The most recent assistant message's rendered content goes to the dashboard panel.
// Older messages stay in the chat history on the right.

export default function Home() {
  const { messages, sendMessage, status } = useChat({
    transport: new DefaultChatTransport({ api: "/api/chat" }),
  });
  const [input, setInput] = useState("");
  const [exporting, setExporting] = useState(false);

  const chatBottomRef = useRef<HTMLDivElement>(null);
  const isStreaming = status === "streaming" || status === "submitted";

  const hasAssistantMessage = messages.some((m) => m.role === "assistant");

  const handleExport = useCallback(async () => {
    setExporting(true);
    try {
      const slideSpec = buildSlideSpec(messages as Parameters<typeof buildSlideSpec>[0]);
      const body = slideSpec.length > 0 ? { slides: slideSpec } : {};
      const res = await fetch(`${PYTHON_API}/api/export/ppt`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      if (!res.ok) throw new Error(`Export failed: ${res.statusText}`);
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = "Magnum_SOP_2026.pptx";
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
    } catch (err) {
      console.error("PPT export error:", err);
    } finally {
      setExporting(false);
    }
  }, [messages]);

  useEffect(() => {
    chatBottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const assistantMessages = messages.filter((m) => m.role === "assistant");
  const lastAssistant = assistantMessages[assistantMessages.length - 1];
  const lastAssistantText = lastAssistant?.parts
    .filter((p) => p.type === "text")
    .map((p) => (p.type === "text" ? p.text : ""))
    .join("") ?? "";

  const isLastStreaming =
    isStreaming && lastAssistant?.id === messages[messages.length - 1]?.id;

  return (
    <div className="flex flex-col h-screen bg-slate-50 text-slate-900 overflow-hidden">
      {/* ── Top header bar ── */}
      <header className="flex items-center gap-3 px-6 py-3 border-b border-slate-200 bg-white shrink-0 z-10">
        <span className="text-lg">🍦</span>
        <div>
          <h1 className="text-sm font-semibold text-slate-900 leading-tight">
            Magnum S&amp;OP
          </h1>
          <p className="text-xs text-slate-400 leading-tight">
            Generative Dashboard · MRF3 2026
          </p>
        </div>
        <div className="ml-auto flex items-center gap-3">
          {isStreaming && (
            <div className="flex items-center gap-1.5 text-xs text-indigo-500 font-medium">
              <span className="w-1.5 h-1.5 rounded-full bg-indigo-500 animate-pulse inline-block" />
              Generating…
            </div>
          )}
          <button
            onClick={handleExport}
            disabled={!hasAssistantMessage || isStreaming || exporting}
            className="flex items-center gap-1.5 rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-xs font-medium text-slate-700 hover:bg-indigo-50 hover:border-indigo-300 hover:text-indigo-700 disabled:opacity-40 disabled:cursor-not-allowed transition-colors shadow-sm"
          >
            {exporting ? (
              <>
                <span className="w-3 h-3 border-2 border-indigo-400 border-t-transparent rounded-full animate-spin inline-block" />
                Exporting…
              </>
            ) : (
              <>
                <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 10v6m0 0l-3-3m3 3l3-3m2 8H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                </svg>
                Export to PPT
              </>
            )}
          </button>
        </div>
      </header>

      {/* ── Main two-column body ── */}
      <div className="flex flex-1 overflow-hidden">

        {/* ── LEFT: Dashboard panel (70%) ── */}
        <main className="flex-7 overflow-y-auto border-r border-slate-200 bg-slate-50">
          {!lastAssistantText ? (
            /* Empty state */
            <div className="flex flex-col items-center justify-center h-full gap-6 px-10 text-center">
              <div className="w-14 h-14 rounded-2xl bg-indigo-50 border border-indigo-100 flex items-center justify-center text-2xl">
                🍦
              </div>
              <div className="flex flex-col gap-2 max-w-sm">
                <h2 className="text-xl font-semibold text-slate-800">
                  Your generative dashboard
                </h2>
                <p className="text-sm text-slate-500">
                  Ask a question in the chat panel on the right and your S&amp;OP
                  dashboard will appear here — charts, tables, and KPIs
                  generated live from your pipeline data.
                </p>
              </div>
              <div className="grid grid-cols-2 gap-2 w-full max-w-md mt-2">
                {SUGGESTED_QUERIES.map((q) => (
                  <button
                    key={q}
                    onClick={() => sendMessage({ text: q })}
                    className="rounded-lg border border-slate-200 bg-white px-3 py-2.5 text-xs text-slate-600 text-left hover:border-indigo-300 hover:bg-indigo-50 hover:text-indigo-700 transition-colors shadow-sm"
                  >
                    {q}
                  </button>
                ))}
              </div>
            </div>
          ) : (
            /* Dashboard content */
            <div className="p-8">
              <Renderer
                response={lastAssistantText}
                library={sopLibrary}
                isStreaming={isLastStreaming}
              />
            </div>
          )}
        </main>

        {/* ── RIGHT: Chat panel (30%) ── */}
        <aside className="flex-3 flex flex-col bg-white min-w-0">
          {/* Chat header */}
          <div className="px-4 py-3 border-b border-slate-100 shrink-0">
            <p className="text-xs font-semibold text-slate-500 uppercase tracking-wider">
              Chat
            </p>
          </div>

          {/* Message history */}
          <div className="flex-1 overflow-y-auto px-4 py-4 flex flex-col gap-3">
            {messages.length === 0 && (
              <p className="text-xs text-slate-400 text-center mt-8">
                Ask anything about your S&amp;OP plan…
              </p>
            )}

            {messages.map((message) => {
              if (message.role === "user") {
                const text = message.parts
                  .filter((p) => p.type === "text")
                  .map((p) => (p.type === "text" ? p.text : ""))
                  .join("");
                return (
                  <div key={message.id} className="flex justify-end">
                    <div className="max-w-[85%] rounded-2xl rounded-tr-sm bg-indigo-600 px-3 py-2 text-xs text-white leading-relaxed">
                      {text}
                    </div>
                  </div>
                );
              }

              if (message.role === "assistant") {
                const text = message.parts
                  .filter((p) => p.type === "text")
                  .map((p) => (p.type === "text" ? p.text : ""))
                  .join("");
                const isThis =
                  isStreaming &&
                  message.id === messages[messages.length - 1]?.id;

                return (
                  <div key={message.id} className="flex gap-2 items-start">
                    <div className="w-5 h-5 rounded-full bg-indigo-100 flex items-center justify-center text-xs shrink-0 mt-0.5">
                      🍦
                    </div>
                    <div className="max-w-[85%] rounded-2xl rounded-tl-sm bg-slate-100 px-3 py-2 text-xs text-slate-700 leading-relaxed">
                      {text ? (
                        <span>
                          {isThis
                            ? "Generating dashboard…"
                            : "Dashboard updated ↖"}
                        </span>
                      ) : (
                        <span className="flex items-center gap-1.5 text-slate-400">
                          <span className="w-1 h-1 rounded-full bg-slate-400 animate-pulse inline-block" />
                          Fetching data…
                        </span>
                      )}
                    </div>
                  </div>
                );
              }

              return null;
            })}

            <div ref={chatBottomRef} />
          </div>

          {/* Input */}
          <div className="shrink-0 px-4 py-3 border-t border-slate-100">
            <form
              onSubmit={(e) => {
                e.preventDefault();
                if (!input.trim() || isStreaming) return;
                sendMessage({ text: input.trim() });
                setInput("");
              }}
              className="flex gap-2"
            >
              <input
                value={input}
                onChange={(e) => setInput(e.target.value)}
                placeholder="Ask about your S&OP data…"
                disabled={isStreaming}
                className="flex-1 rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 text-xs text-slate-900 placeholder:text-slate-400 focus:outline-none focus:ring-2 focus:ring-indigo-400 focus:border-transparent disabled:opacity-50 transition-colors"
              />
              <button
                type="submit"
                disabled={!input.trim() || isStreaming}
                className="shrink-0 rounded-lg bg-indigo-600 hover:bg-indigo-500 disabled:opacity-40 disabled:cursor-not-allowed px-3 py-2 text-xs font-medium text-white transition-colors"
              >
                Send
              </button>
            </form>
            <p className="text-[10px] text-slate-400 mt-1.5 text-center">
              Dashboard renders live on the left
            </p>
          </div>
        </aside>
      </div>
    </div>
  );
}
