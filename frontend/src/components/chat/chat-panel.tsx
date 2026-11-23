"use client";

import { FormEvent, useRef, useState } from "react";
import { ApiError, apiClient, type MetadataResponse, type SummaryRequest } from "@/lib/api";
import { ExternalIcon, InfoIcon, SendIcon, SparkIcon } from "@/components/ui/icons";
import { StatusPill } from "@/components/ui/status-pill";
import { ExecutionTraceDisclosure } from "./execution-trace";
import type { A03ChatResponse } from "@/lib/api/a03-contract-proposal";
import { YearComparisonEvidence } from "./year-comparison";

type Message = { id: string; role: "user"; content: string } | { id: string; role: "assistant"; response: A03ChatResponse } | { id: string; role: "error"; content: string };

const suggestions = ["What does fire radiative power mean?", "Can hotspots confirm a wildfire?", "What limitations should I consider?"];

export function ChatPanel({ filters, provinceName, metadata }: { filters: SummaryRequest; provinceName: string; metadata?: Pick<MetadataResponse, "data_status" | "source"> }) {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  async function sendMessage(message: string) {
    const trimmed = message.trim();
    if (!trimmed || loading) return;
    const userMessage: Message = { id: crypto.randomUUID(), role: "user", content: trimmed };
    setMessages((current) => [...current, userMessage]);
    setInput("");
    setLoading(true);
    try {
      const response = await apiClient.chat({ message: trimmed, product_id: filters.product_id, context: { province_code: filters.province_codes[0] ?? null, date_from: filters.date_from, date_to: filters.date_to } }) as A03ChatResponse;
      setMessages((current) => [...current, { id: response.request_id, role: "assistant", response }]);
    } catch (error) {
      const message = error instanceof ApiError
        ? error.code === "RATE_LIMITED" ? `Request limit reached. Try again${error.retryAfterSeconds ? ` in ${error.retryAfterSeconds} seconds` : " later"}.`
          : error.code === "REQUEST_TIMEOUT" ? "The bounded assistant request timed out. No answer was generated; please retry."
          : error.code === "DEPENDENCY_UNAVAILABLE" ? "A required assistant dependency is unavailable. No synthetic answer was substituted."
          : error.message
        : "The assistant is unavailable right now. Please try again.";
      setMessages((current) => [...current, { id: crypto.randomUUID(), role: "error", content: message }]);
    } finally {
      setLoading(false);
      inputRef.current?.focus();
    }
  }

  function onSubmit(event: FormEvent) { event.preventDefault(); void sendMessage(input); }

  return (
    <section id="assistant" className="panel overflow-hidden" aria-labelledby="chat-title">
      <div className="flex flex-wrap items-start justify-between gap-3 border-b border-slate-100 p-4 lg:p-5">
        <div className="flex items-center gap-3"><span className="grid h-10 w-10 place-items-center rounded-xl bg-forest-700 text-white"><SparkIcon /></span><div><p className="eyebrow">Grounded exploration</p><h2 id="chat-title" className="mt-0.5 text-lg font-semibold">Ask the intelligence agent</h2></div></div>
        <StatusPill tone="green"><span className="h-1.5 w-1.5 rounded-full bg-forest-500" /> Ready</StatusPill>
      </div>

      <div className="min-h-[260px] max-h-[500px] space-y-5 overflow-y-auto p-4 lg:p-6" aria-live="polite">
        {messages.length === 0 && <div className="mx-auto max-w-2xl py-5 text-center"><div className="mx-auto grid h-12 w-12 place-items-center rounded-2xl bg-forest-50 text-forest-700"><SparkIcon className="h-6 w-6" /></div><h3 className="mt-4 text-base font-semibold">Explore the evidence, not just the answer</h3><p className="mx-auto mt-2 max-w-lg text-sm leading-6 text-slate-500">Ask about hotspot patterns or satellite terminology. Answers will separate analytical findings, documentation, and limitations.</p><div className="mt-5 flex flex-wrap justify-center gap-2">{suggestions.map((suggestion) => <button key={suggestion} type="button" onClick={() => void sendMessage(suggestion)} className="rounded-full border border-slate-200 bg-white px-3 py-2 text-xs font-medium text-slate-600 transition hover:border-forest-500 hover:text-forest-700">{suggestion}</button>)}</div></div>}
        {messages.map((message) => {
          if (message.role === "user") return <div key={message.id} className="ml-auto max-w-[85%] rounded-2xl rounded-br-md bg-forest-700 px-4 py-3 text-sm leading-6 text-white sm:max-w-[72%]">{message.content}</div>;
          if (message.role === "error") return <div key={message.id} role="alert" className="max-w-[90%] rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800"><strong>Couldn’t complete the request.</strong><p className="mt-1">{message.content}</p></div>;
          return <article key={message.id} className="max-w-3xl"><div className="mb-2 flex items-center gap-2"><span className="grid h-7 w-7 place-items-center rounded-lg bg-forest-100 text-forest-700"><SparkIcon className="h-4 w-4" /></span><span className="text-xs font-semibold">Intelligence agent</span><StatusPill tone={message.response.mode === "unsupported" ? "amber" : "slate"}>{message.response.mode}</StatusPill></div><p className="text-sm leading-7 text-slate-700">{message.response.answer}</p>{message.response.metrics && <dl className="mt-3 flex flex-wrap gap-2">{message.response.metrics.map((metric) => <div key={metric.name} className="rounded-lg border border-slate-200 bg-slate-50 px-3 py-2"><dt className="text-[10px] uppercase tracking-wide text-slate-500">{metric.name.replaceAll("_", " ")}</dt><dd className="mt-1 text-sm font-semibold">{metric.value === null ? "Unavailable" : metric.value.toLocaleString("en-US")} {metric.unit}</dd></div>)}</dl>}{message.response.year_comparison && <YearComparisonEvidence comparison={message.response.year_comparison} />}{message.response.chart && <p className="mt-3 text-xs text-slate-500">Chart evidence: {message.response.chart.series.length} backend-supplied period{message.response.chart.series.length === 1 ? "" : "s"}.</p>}{message.response.map && <p className="mt-1 text-xs text-slate-500">Map evidence: {message.response.map.features.length} bounded backend-supplied point{message.response.map.features.length === 1 ? "" : "s"}.</p>}{message.response.citations.length > 0 && <div className="mt-4"><p className="text-xs font-bold uppercase tracking-wider text-slate-500">Sources</p><div className="mt-2 flex flex-wrap gap-2">{message.response.citations.map((citation) => <a key={citation.chunk_id} href={citation.url} target="_blank" rel="noopener noreferrer" className="inline-flex items-center gap-2 rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 text-xs font-medium text-slate-700 hover:border-forest-500">{citation.title}<ExternalIcon className="h-3.5 w-3.5" /></a>)}</div></div>}{message.response.limitations.length > 0 && <div className="mt-4 rounded-xl border border-amber-200 bg-amber-50/70 p-3"><div className="flex gap-2"><InfoIcon className="mt-0.5 h-4 w-4 shrink-0 text-amber-700"/><div><p className="text-xs font-semibold text-amber-900">Limitations</p><ul className="mt-1 space-y-1 text-xs leading-5 text-amber-800">{message.response.limitations.map((limitation) => <li key={limitation}>• {limitation}</li>)}</ul></div></div></div>}<ExecutionTraceDisclosure trace={message.response.execution_trace} response={message.response} dataContext={metadata ? { dataStatus: metadata.data_status, source: metadata.source } : undefined} /></article>;
        })}
        {loading && <div className="flex items-center gap-3 text-sm text-slate-500"><span className="grid h-7 w-7 place-items-center rounded-lg bg-forest-100 text-forest-700"><SparkIcon className="h-4 w-4" /></span><span className="flex gap-1" aria-label="Assistant is thinking"><i className="h-2 w-2 animate-bounce rounded-full bg-forest-500 [animation-delay:-.3s]"/><i className="h-2 w-2 animate-bounce rounded-full bg-forest-500 [animation-delay:-.15s]"/><i className="h-2 w-2 animate-bounce rounded-full bg-forest-500"/></span></div>}
      </div>

      <form onSubmit={onSubmit} className="border-t border-slate-100 bg-slate-50/60 p-4 lg:p-5"><div className="flex gap-2"><label className="sr-only" htmlFor="chat-input">Ask about wildfire hotspot data</label><input ref={inputRef} id="chat-input" value={input} onChange={(event) => setInput(event.target.value)} maxLength={1000} disabled={loading} placeholder={`Ask about ${provinceName} hotspot detections…`} className="h-12 min-w-0 flex-1 rounded-xl border border-slate-200 bg-white px-4 text-sm shadow-sm focus:border-forest-500 focus:outline-none focus:ring-2 focus:ring-forest-500/15"/><button type="submit" disabled={!input.trim() || loading} aria-label="Send message" className="grid h-12 w-12 shrink-0 place-items-center rounded-xl bg-forest-700 text-white transition hover:bg-forest-900 disabled:cursor-not-allowed disabled:opacity-40"><SendIcon className="h-5 w-5"/></button></div><div className="mt-2 flex justify-between gap-4 text-[10px] text-slate-500"><span>Responses may be incomplete. Inspect sources and limitations.</span><span>{input.length}/1000</span></div></form>
    </section>
  );
}
