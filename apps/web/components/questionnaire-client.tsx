"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useAuth } from "@clerk/nextjs";
import { z } from "zod";
import {
  ClipboardList,
  Download,
  Filter,
  Loader2,
  Upload,
  X,
} from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { EmptyState } from "@/components/empty-state";
import { Input } from "@/components/ui/input";
import { Progress } from "@/components/ui/progress";
import { IslandErrorBoundary } from "@/components/error-boundary";
import { PageHeader } from "@/components/page-header";

// ── Zod schemas ─────────────────────────────────────────────────────────────

const CitationSchema = z.object({
  evidence_id: z.string().default(""),
  snippet: z.string().default(""),
  source_uri: z.string().default(""),
});

const QuestionSchema = z.object({
  id: z.string(),
  run_id: z.string(),
  question_id: z.string(),
  sheet: z.string(),
  row: z.number(),
  column: z.number(),
  section: z.string().default(""),
  domain: z.string().default("uncategorized"),
  answer_type: z.string().default("unknown"),
  question_text: z.string().default(""),
  answer_text: z.string().default(""),
  confidence: z.number().min(0).max(1),
  flagged: z.boolean(),
  citations: z.array(CitationSchema).default([]),
  edited_by_user: z.boolean().default(false),
});

const RunSummarySchema = z.object({
  id: z.string(),
  user_id: z.string(),
  filename: z.string().default(""),
  format: z.string().default("sig-lite"),
  status: z.enum(["queued", "parsing", "drafting", "ready", "failed"]),
  question_count: z.number(),
  answered_count: z.number(),
  flagged_count: z.number(),
  cluster_count: z.number(),
  output_r2_key: z.string().nullable().optional(),
  failure_reason: z.string().nullable().optional(),
  created_at: z.string(),
  updated_at: z.string(),
});

const RunListSchema = z.object({
  runs: z.array(RunSummarySchema),
  count: z.number(),
});

const RunDetailSchema = z.object({
  run: RunSummarySchema,
  questions: z.array(QuestionSchema),
});

const UploadResponseSchema = z.object({
  run_id: z.string(),
  task_id: z.string(),
  status: z.string(),
  deduplicated: z.boolean(),
  filename: z.string(),
  size_bytes: z.number(),
});

type Question = z.infer<typeof QuestionSchema>;
type RunSummary = z.infer<typeof RunSummarySchema>;

// ── Helpers ─────────────────────────────────────────────────────────────────

const STATUS_LABELS: Record<RunSummary["status"], string> = {
  queued: "Queued",
  parsing: "Parsing",
  drafting: "Drafting",
  ready: "Ready",
  failed: "Failed",
};

const STATUS_BADGE: Record<RunSummary["status"], string> = {
  queued:
    "bg-slate-100 text-slate-700 border-slate-200 dark:bg-slate-900/40 dark:text-slate-200 dark:border-slate-700",
  parsing:
    "bg-blue-50 text-blue-700 border-blue-200 dark:bg-blue-950/40 dark:text-blue-200 dark:border-blue-800",
  drafting:
    "bg-amber-50 text-amber-700 border-amber-200 dark:bg-amber-950/40 dark:text-amber-200 dark:border-amber-800",
  ready:
    "bg-emerald-50 text-emerald-700 border-emerald-200 dark:bg-emerald-950/40 dark:text-emerald-200 dark:border-emerald-800",
  failed:
    "bg-rose-50 text-rose-700 border-rose-200 dark:bg-rose-950/40 dark:text-rose-200 dark:border-rose-800",
};

function fmtPercent(numerator: number, denominator: number): string {
  if (!denominator) return "0%";
  return `${Math.round((numerator / denominator) * 100)}%`;
}

function cellTone(question: Question): string {
  if (question.flagged) {
    return "bg-amber-50 border-amber-200 dark:bg-amber-950/30 dark:border-amber-900";
  }
  if (question.answer_text) {
    return "bg-emerald-50/60 border-emerald-100 dark:bg-emerald-950/20 dark:border-emerald-900";
  }
  return "bg-slate-50 border-slate-200 dark:bg-slate-900/40 dark:border-slate-800";
}

// ── Upload card ─────────────────────────────────────────────────────────────

function UploadCard({
  onUploaded,
}: {
  onUploaded: (runId: string) => void;
}) {
  const { getToken } = useAuth();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const uploadAbortRef = useRef<AbortController | null>(null);

  useEffect(() => {
    return () => {
      uploadAbortRef.current?.abort();
    };
  }, []);

  const handleSubmit = useCallback(
    async (event: React.FormEvent<HTMLFormElement>) => {
      event.preventDefault();
      const file = inputRef.current?.files?.[0];
      if (!file) {
        setError("Choose a SIG-Lite XLSX first.");
        return;
      }
      if (file.size > 10 * 1024 * 1024) {
        setError("File exceeds 10 MB.");
        return;
      }
      setBusy(true);
      setError(null);
      uploadAbortRef.current?.abort();
      uploadAbortRef.current = new AbortController();
      try {
        const token = await getToken();
        const form = new FormData();
        form.append("file", file);
        form.append("format", "sig-lite");
        const res = await fetch("/api/questionnaire/upload", {
          method: "POST",
          headers: { Authorization: `Bearer ${token}` },
          body: form,
          signal: uploadAbortRef.current.signal,
        });
        if (!res.ok) {
          throw new Error(`Upload failed: ${res.status}`);
        }
        const raw = await res.json();
        const parsed = UploadResponseSchema.safeParse(raw);
        if (!parsed.success) {
          throw new Error("Invalid upload response shape.");
        }
        onUploaded(parsed.data.run_id);
        if (inputRef.current) inputRef.current.value = "";
      } catch (err) {
        if (err instanceof DOMException && err.name === "AbortError") return;
        setError(err instanceof Error ? err.message : "Upload failed");
      } finally {
        setBusy(false);
      }
    },
    [getToken, onUploaded]
  );

  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="text-sm flex items-center gap-2">
          <Upload className="h-4 w-4 text-muted-foreground" />
          Upload questionnaire
        </CardTitle>
      </CardHeader>
      <CardContent>
        <form onSubmit={handleSubmit} className="flex flex-col gap-3">
          <Input
            ref={inputRef}
            type="file"
            accept=".xlsx,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            disabled={busy}
            aria-label="SIG-Lite XLSX file"
          />
          <Button type="submit" disabled={busy}>
            {busy ? (
              <>
                <Loader2 className="h-4 w-4 animate-spin" />
                Uploading...
              </>
            ) : (
              <>Upload + auto-fill</>
            )}
          </Button>
          {error && (
            <p className="text-xs text-destructive" role="alert">
              {error}
            </p>
          )}
          <p className="text-[11px] text-muted-foreground">
            SIG-Lite v2026 XLSX, max 10 MB. The fill runs in the background; you
            can leave this page and come back.
          </p>
        </form>
      </CardContent>
    </Card>
  );
}

// ── Run list ────────────────────────────────────────────────────────────────

function RunList({
  runs,
  selectedId,
  onSelect,
}: {
  runs: RunSummary[];
  selectedId: string | null;
  onSelect: (id: string) => void;
}) {
  if (runs.length === 0) {
    return (
      <p className="text-xs text-muted-foreground">
        No runs yet — upload a questionnaire to begin.
      </p>
    );
  }
  return (
    <ul className="flex flex-col gap-1">
      {runs.map((run) => (
        <li key={run.id}>
          <button
            type="button"
            onClick={() => onSelect(run.id)}
            className={`w-full rounded-md border p-2.5 text-left transition-colors ${
              run.id === selectedId
                ? "border-primary bg-primary/5"
                : "border-transparent hover:bg-muted"
            }`}
          >
            <div className="flex items-center justify-between gap-2">
              <span className="truncate text-sm font-medium">
                {run.filename || "questionnaire.xlsx"}
              </span>
              <span
                className={`rounded-full border px-1.5 py-0.5 text-[10px] font-medium ${STATUS_BADGE[run.status]}`}
              >
                {STATUS_LABELS[run.status]}
              </span>
            </div>
            <div className="mt-1 text-[11px] text-muted-foreground">
              {run.answered_count}/{run.question_count} answered ·{" "}
              {run.flagged_count} flagged
            </div>
          </button>
        </li>
      ))}
    </ul>
  );
}

// ── Citation picker ─────────────────────────────────────────────────────────

function CitationPicker({
  citations,
}: {
  citations: Question["citations"];
}) {
  if (!citations.length) {
    return (
      <p className="text-[11px] text-muted-foreground">
        No citations attached.
      </p>
    );
  }
  return (
    <ul className="flex flex-col gap-1">
      {citations.map((cit, idx) => (
        <li
          key={`${cit.evidence_id}-${idx}`}
          className="rounded-md border bg-muted/30 px-2 py-1 text-[11px]"
        >
          <div className="font-mono text-[10px] text-muted-foreground">
            {cit.evidence_id || `ev_${idx + 1}`}
          </div>
          {cit.snippet && (
            <div className="text-foreground">{cit.snippet}</div>
          )}
          {cit.source_uri && (
            <div className="truncate text-[10px] text-muted-foreground">
              {cit.source_uri}
            </div>
          )}
        </li>
      ))}
    </ul>
  );
}

// ── Question editor row ─────────────────────────────────────────────────────

function QuestionRow({
  question,
  onSave,
}: {
  question: Question;
  onSave: (id: string, answer: string) => Promise<void>;
}) {
  const [draft, setDraft] = useState(question.answer_text);
  const [editing, setEditing] = useState(false);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    setDraft(question.answer_text);
  }, [question.answer_text]);

  const dirty = draft !== question.answer_text;
  const tone = cellTone(question);

  const handleSave = async () => {
    setSaving(true);
    try {
      await onSave(question.id, draft);
      setEditing(false);
    } finally {
      setSaving(false);
    }
  };

  return (
    <li
      className={`rounded-md border p-3 ${tone}`}
      data-flagged={question.flagged}
    >
      <div className="flex flex-wrap items-start gap-2">
        <span className="rounded-full bg-foreground/5 px-2 py-0.5 text-[10px] font-mono">
          {question.question_id}
        </span>
        <span className="rounded-full bg-foreground/5 px-2 py-0.5 text-[10px] capitalize">
          {question.domain.replace(/_/g, " ")}
        </span>
        {question.flagged && (
          <Badge
            variant="outline"
            className="border-amber-300 bg-amber-100 text-amber-800 dark:border-amber-800 dark:bg-amber-950/40 dark:text-amber-200"
          >
            Flagged · {(question.confidence * 100).toFixed(0)}%
          </Badge>
        )}
        {!question.flagged && question.answer_text && (
          <Badge
            variant="outline"
            className="border-emerald-300 bg-emerald-50 text-emerald-700 dark:border-emerald-800 dark:bg-emerald-950/40 dark:text-emerald-200"
          >
            Auto · {(question.confidence * 100).toFixed(0)}%
          </Badge>
        )}
        {question.edited_by_user && (
          <Badge variant="outline">Edited</Badge>
        )}
      </div>
      <p className="mt-2 text-sm font-medium">{question.question_text}</p>
      <div className="mt-2 flex flex-col gap-2">
        {editing ? (
          <textarea
            className="min-h-[80px] w-full rounded-md border bg-background p-2 text-sm focus:outline-none focus:ring-2 focus:ring-ring"
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            aria-label={`Edit answer for ${question.question_id}`}
          />
        ) : (
          <p className="whitespace-pre-wrap text-sm text-foreground">
            {question.answer_text || (
              <span className="italic text-muted-foreground">
                No answer yet.
              </span>
            )}
          </p>
        )}
        <div className="flex flex-wrap items-center gap-2">
          {editing ? (
            <>
              <Button
                size="sm"
                onClick={handleSave}
                disabled={saving || !dirty}
              >
                {saving
                  ? "Saving..."
                  : question.flagged
                  ? "Save and clear flag"
                  : "Save"}
              </Button>
              <Button
                size="sm"
                variant="outline"
                onClick={() => {
                  setEditing(false);
                  setDraft(question.answer_text);
                }}
              >
                Cancel
              </Button>
            </>
          ) : (
            <Button
              size="sm"
              variant="outline"
              onClick={() => setEditing(true)}
            >
              Edit
            </Button>
          )}
          <details className="text-[11px]">
            <summary className="cursor-pointer text-muted-foreground hover:text-foreground">
              Citations ({question.citations.length})
            </summary>
            <div className="mt-1">
              <CitationPicker citations={question.citations} />
            </div>
          </details>
        </div>
      </div>
    </li>
  );
}

// ── Run detail panel ────────────────────────────────────────────────────────

function RunDetail({
  runId,
  run,
  questions,
  filterFlagged,
  setFilterFlagged,
  onPatch,
  onDownload,
  downloading,
}: {
  runId: string;
  run: RunSummary;
  questions: Question[];
  filterFlagged: boolean;
  setFilterFlagged: (next: boolean) => void;
  onPatch: (id: string, answer: string) => Promise<void>;
  onDownload: () => Promise<void>;
  downloading: boolean;
}) {
  const filtered = useMemo(
    () => (filterFlagged ? questions.filter((q) => q.flagged) : questions),
    [filterFlagged, questions]
  );
  const groupedBySheet = useMemo(() => {
    const groups: Record<string, Question[]> = {};
    for (const q of filtered) {
      groups[q.sheet] = groups[q.sheet] ?? [];
      groups[q.sheet].push(q);
    }
    return groups;
  }, [filtered]);
  const denom = run.question_count || 1;
  const progressValue = Math.round((run.answered_count / denom) * 100);

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-lg font-semibold">{run.filename}</h2>
          <p className="text-xs text-muted-foreground">
            {run.cluster_count} clusters · {run.format} ·{" "}
            <span
              className={`rounded-full border px-1.5 py-0.5 text-[10px] font-medium ${STATUS_BADGE[run.status]}`}
            >
              {STATUS_LABELS[run.status]}
            </span>
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <Button
            size="sm"
            variant="outline"
            onClick={() => setFilterFlagged(!filterFlagged)}
            aria-pressed={filterFlagged}
          >
            <Filter className="h-3.5 w-3.5" />
            {filterFlagged
              ? `Showing flagged (${run.flagged_count})`
              : "Filter flagged"}
            {filterFlagged && <X className="ml-1 h-3 w-3" />}
          </Button>
          <Button
            size="sm"
            onClick={onDownload}
            disabled={run.status !== "ready" || downloading}
          >
            <Download className="h-3.5 w-3.5" />
            {downloading ? "Preparing..." : "Download filled XLSX"}
          </Button>
        </div>
      </div>

      <Card>
        <CardContent className="flex flex-col gap-2 py-4">
          <div className="flex items-center justify-between text-xs text-muted-foreground">
            <span>
              {run.answered_count} of {run.question_count} answered (
              {fmtPercent(run.answered_count, denom)})
            </span>
            <span>
              {run.flagged_count} flagged · {questions.length} cells loaded
            </span>
          </div>
          <Progress value={progressValue} aria-label="Auto-fill progress" />
        </CardContent>
      </Card>

      {run.status === "failed" && run.failure_reason && (
        <div
          role="alert"
          className="rounded-md border border-rose-200 bg-rose-50 p-3 text-sm text-rose-800 dark:border-rose-900 dark:bg-rose-950/40 dark:text-rose-200"
        >
          Run failed: {run.failure_reason}
        </div>
      )}

      {filtered.length === 0 ? (
        <EmptyState
          icon={ClipboardList}
          title={
            filterFlagged
              ? "No flagged cells"
              : run.status === "ready"
              ? "No questions found"
              : "Auto-fill in progress"
          }
          description={
            filterFlagged
              ? "Clear the flag filter to see every drafted cell."
              : run.status === "ready"
              ? "The parser did not detect any questions in this XLSX."
              : "Cells will appear here as the orchestrator drafts answers."
          }
        />
      ) : (
        <div className="flex flex-col gap-4">
          {Object.entries(groupedBySheet).map(([sheet, group]) => (
            <section key={`${runId}-${sheet}`} className="flex flex-col gap-2">
              <h3 className="text-sm font-semibold">{sheet}</h3>
              <ul className="grid gap-2">
                {group.map((q) => (
                  <QuestionRow
                    key={q.id}
                    question={q}
                    onSave={onPatch}
                  />
                ))}
              </ul>
            </section>
          ))}
        </div>
      )}
    </div>
  );
}

// ── Page-level component ────────────────────────────────────────────────────

const POLL_INTERVAL_MS = 3000;

export function QuestionnaireClient() {
  return (
    <IslandErrorBoundary name="QuestionnaireClient">
      <QuestionnaireWorkspace />
    </IslandErrorBoundary>
  );
}

function QuestionnaireWorkspace() {
  const { getToken } = useAuth();
  const [runs, setRuns] = useState<RunSummary[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [run, setRun] = useState<RunSummary | null>(null);
  const [questions, setQuestions] = useState<Question[]>([]);
  const [filterFlagged, setFilterFlagged] = useState(false);
  const [downloading, setDownloading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const mountedRef = useRef(true);
  const listAbortRef = useRef<AbortController | null>(null);
  const detailAbortRef = useRef<AbortController | null>(null);

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
      listAbortRef.current?.abort();
      detailAbortRef.current?.abort();
    };
  }, []);

  const fetchRuns = useCallback(async () => {
    try {
      const token = await getToken();
      listAbortRef.current?.abort();
      listAbortRef.current = new AbortController();
      const res = await fetch("/api/questionnaire", {
        headers: { Authorization: `Bearer ${token}` },
        signal: listAbortRef.current.signal,
      });
      if (!res.ok) throw new Error(`List failed: ${res.status}`);
      const raw = await res.json();
      const parsed = RunListSchema.safeParse(raw);
      if (!parsed.success) throw new Error("Bad list response");
      if (mountedRef.current) {
        setRuns(parsed.data.runs);
        if (!selectedId && parsed.data.runs.length > 0) {
          setSelectedId(parsed.data.runs[0].id);
        }
      }
    } catch (err) {
      if (err instanceof DOMException && err.name === "AbortError") return;
      if (mountedRef.current) {
        setError(err instanceof Error ? err.message : "Failed to load runs");
      }
    } finally {
      if (mountedRef.current) setLoading(false);
    }
  }, [getToken, selectedId]);

  const fetchRun = useCallback(
    async (runId: string) => {
      try {
        const token = await getToken();
        detailAbortRef.current?.abort();
        detailAbortRef.current = new AbortController();
        const res = await fetch(`/api/questionnaire/${runId}`, {
          headers: { Authorization: `Bearer ${token}` },
          signal: detailAbortRef.current.signal,
        });
        if (!res.ok) throw new Error(`Detail failed: ${res.status}`);
        const raw = await res.json();
        const parsed = RunDetailSchema.safeParse(raw);
        if (!parsed.success) throw new Error("Bad detail response");
        if (mountedRef.current) {
          setRun(parsed.data.run);
          setQuestions(parsed.data.questions);
        }
      } catch (err) {
        if (err instanceof DOMException && err.name === "AbortError") return;
        if (mountedRef.current) {
          setError(err instanceof Error ? err.message : "Failed to load run");
        }
      }
    },
    [getToken]
  );

  // Initial list load.
  useEffect(() => {
    fetchRuns();
  }, [fetchRuns]);

  // Detail + polling loop while not in terminal state. The /poll endpoint
  // is the SWR-style fallback the spec requires alongside SSE (chunk 7.8).
  // Status is read out of a ref so the effect does not re-fire on every
  // status change (which would create a render loop in tests with fake timers).
  const runStatusRef = useRef<RunSummary["status"] | null>(null);
  useEffect(() => {
    runStatusRef.current = run?.status ?? null;
  }, [run?.status]);

  useEffect(() => {
    if (!selectedId) return;
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout> | null = null;

    const tick = async () => {
      if (cancelled) return;
      await fetchRun(selectedId);
      if (cancelled) return;
      const status = runStatusRef.current;
      const isTerminal = status === "ready" || status === "failed";
      if (!isTerminal) {
        timer = setTimeout(tick, POLL_INTERVAL_MS);
      }
    };
    tick();
    return () => {
      cancelled = true;
      if (timer) clearTimeout(timer);
    };
  }, [selectedId, fetchRun]);

  // Reload list when run terminal status changes so the sidebar reflects
  // updated answered/flagged counts.
  useEffect(() => {
    if (run?.status === "ready" || run?.status === "failed") {
      fetchRuns();
    }
  }, [run?.status, fetchRuns]);

  const handleUploaded = useCallback(
    async (runId: string) => {
      await fetchRuns();
      setSelectedId(runId);
    },
    [fetchRuns]
  );

  const handlePatch = useCallback(
    async (questionPk: string, answerText: string) => {
      try {
        const token = await getToken();
        const res = await fetch(
          `/api/questionnaire/questions/${questionPk}`,
          {
            method: "PATCH",
            headers: {
              Authorization: `Bearer ${token}`,
              "Content-Type": "application/json",
            },
            body: JSON.stringify({
              answer_text: answerText,
              clear_flag: true,
            }),
          }
        );
        if (!res.ok) throw new Error(`Patch failed: ${res.status}`);
        const raw = await res.json();
        const parsed = QuestionSchema.safeParse(raw);
        if (parsed.success && mountedRef.current) {
          setQuestions((prev) =>
            prev.map((q) => (q.id === parsed.data.id ? parsed.data : q))
          );
          if (selectedId) await fetchRun(selectedId);
        }
      } catch (err) {
        if (mountedRef.current) {
          setError(err instanceof Error ? err.message : "Patch failed");
        }
      }
    },
    [getToken, selectedId, fetchRun]
  );

  const handleDownload = useCallback(async () => {
    if (!selectedId) return;
    setDownloading(true);
    try {
      const token = await getToken();
      const res = await fetch(
        `/api/questionnaire/${selectedId}/download`,
        {
          headers: { Authorization: `Bearer ${token}` },
          redirect: "follow",
        }
      );
      if (!res.ok) {
        throw new Error(`Download failed: ${res.status}`);
      }
      // The route 302s to a pre-signed URL; ``fetch`` with ``redirect:
      // "follow"`` returns the body of the final URL. Stream it into a Blob
      // and trigger a download.
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = (run?.filename || "questionnaire").replace(
        /\.xlsx$/,
        ""
      ) + "_filled.xlsx";
      a.click();
      URL.revokeObjectURL(url);
    } catch (err) {
      if (mountedRef.current) {
        setError(err instanceof Error ? err.message : "Download failed");
      }
    } finally {
      if (mountedRef.current) setDownloading(false);
    }
  }, [getToken, run?.filename, selectedId]);

  if (loading) {
    return (
      <div
        className="flex items-center justify-center h-64"
        role="status"
        aria-live="polite"
      >
        <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <PageHeader
        title="Questionnaire"
        description="Upload SIG-Lite XLSX, watch the auto-fill progress, edit flagged cells, then download with citations as cell comments."
      />

      {error && (
        <div
          className="flex items-start justify-between rounded-md border border-destructive/30 bg-destructive/10 p-3 text-sm text-destructive"
          role="alert"
        >
          <span>{error}</span>
          <button
            type="button"
            className="ml-2 underline"
            onClick={() => setError(null)}
            aria-label="Dismiss error"
          >
            Dismiss
          </button>
        </div>
      )}

      <div className="flex flex-col gap-6 lg:flex-row lg:items-start">
        <aside className="flex w-full flex-col gap-4 lg:w-80 lg:flex-shrink-0">
          <UploadCard onUploaded={handleUploaded} />
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-sm">Recent runs</CardTitle>
            </CardHeader>
            <CardContent>
              <RunList
                runs={runs}
                selectedId={selectedId}
                onSelect={setSelectedId}
              />
            </CardContent>
          </Card>
        </aside>
        <div className="min-w-0 flex-1">
          {run && selectedId ? (
            <RunDetail
              runId={selectedId}
              run={run}
              questions={questions}
              filterFlagged={filterFlagged}
              setFilterFlagged={setFilterFlagged}
              onPatch={handlePatch}
              onDownload={handleDownload}
              downloading={downloading}
            />
          ) : (
            <EmptyState
              icon={ClipboardList}
              title="No questionnaire selected"
              description="Upload a SIG-Lite XLSX to start the auto-fill, or pick an existing run from the sidebar."
            />
          )}
        </div>
      </div>
    </div>
  );
}
