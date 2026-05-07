"use client";

import { useEffect, useState, useCallback, useRef } from "react";
import { useAuth } from "@clerk/nextjs";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { IslandErrorBoundary } from "@/components/error-boundary";
import { z } from "zod";

const PolicyDraftSchema = z.object({
  id: z.string(),
  policy_type: z.string(),
  title: z.string(),
  content: z.string(),
  version: z.number(),
  finalized: z.boolean(),
  thread_id: z.string().nullable().optional(),
  created_at: z.string(),
  updated_at: z.string(),
});

type PolicyDraft = z.infer<typeof PolicyDraftSchema>;

type PolicyType = "irp" | "access_control" | "change_management" | "vendor_management";

const POLICY_TYPE_LABELS: Record<PolicyType, string> = {
  irp: "Incident Response Plan",
  access_control: "Access Control Policy",
  change_management: "Change Management Policy",
  vendor_management: "Vendor Management Policy",
};

function PolicyEditorContent({
  policy,
  onSave,
  onDownload,
  saving,
}: {
  policy: PolicyDraft;
  onSave: (content: string) => void;
  onDownload: (format: "md" | "docx") => void;
  saving: boolean;
}) {
  const [content, setContent] = useState(policy.content);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    setContent(policy.content);
  }, [policy.content]);

  return (
    <div className="flex flex-col gap-4 h-full">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <h2 className="text-lg font-semibold">{policy.title}</h2>
          <Badge variant={policy.finalized ? "default" : "secondary"}>
            {policy.finalized ? "Finalized" : `Draft v${policy.version}`}
          </Badge>
        </div>
        <div className="flex gap-2">
          <Button
            variant="outline"
            size="sm"
            onClick={() => onSave(content)}
            disabled={saving || content === policy.content}
          >
            {saving ? "Saving..." : "Save"}
          </Button>
          <Button
            variant="outline"
            size="sm"
            onClick={() => onDownload("md")}
          >
            Download .md
          </Button>
          <Button
            variant="outline"
            size="sm"
            onClick={() => onDownload("docx")}
          >
            Download .docx
          </Button>
        </div>
      </div>
      <textarea
        ref={textareaRef}
        className="flex-1 w-full min-h-[500px] p-4 border rounded-md font-mono text-sm resize-none focus:outline-none focus:ring-2 focus:ring-ring"
        value={content}
        onChange={(e) => setContent(e.target.value)}
        aria-label={`Edit ${policy.title}`}
      />
    </div>
  );
}

function PolicyListItem({
  policy,
  selected,
  onClick,
}: {
  policy: PolicyDraft;
  selected: boolean;
  onClick: () => void;
}) {
  return (
    <button
      onClick={onClick}
      className={`w-full text-left p-3 rounded-md border transition-colors ${
        selected
          ? "border-primary bg-primary/5"
          : "border-transparent hover:bg-muted"
      }`}
    >
      <div className="flex items-center justify-between">
        <span className="font-medium text-sm">{policy.title}</span>
        <Badge variant={policy.finalized ? "default" : "outline"} className="text-xs">
          {policy.finalized ? "Final" : `v${policy.version}`}
        </Badge>
      </div>
      <span className="text-xs text-muted-foreground">
        {POLICY_TYPE_LABELS[policy.policy_type as PolicyType] ?? policy.policy_type}
      </span>
    </button>
  );
}

function DraftPolicyButton({
  policyType,
  onDraft,
  active,
}: {
  policyType: PolicyType;
  onDraft: (type: PolicyType) => void;
  active: boolean;
}) {
  return (
    <Button
      variant="outline"
      size="sm"
      className="w-full justify-start"
      onClick={() => onDraft(policyType)}
      disabled={active}
    >
      {active ? "Drafting..." : `Draft ${POLICY_TYPE_LABELS[policyType]}`}
    </Button>
  );
}

export default function PoliciesPage() {
  const { getToken } = useAuth();
  const [policies, setPolicies] = useState<PolicyDraft[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [selectedPolicy, setSelectedPolicy] = useState<PolicyDraft | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadingPolicy, setLoadingPolicy] = useState(false);
  const [saving, setSaving] = useState(false);
  const [draftingType, setDraftingType] = useState<PolicyType | null>(null);
  const [error, setError] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  const policyAbortRef = useRef<AbortController | null>(null);
  const mountedRef = useRef(true);

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
      abortRef.current?.abort();
      policyAbortRef.current?.abort();
    };
  }, []);

  const fetchPolicies = useCallback(async () => {
    try {
      const token = await getToken();
      abortRef.current?.abort();
      abortRef.current = new AbortController();
      const res = await fetch("/api/policies", {
        headers: { Authorization: `Bearer ${token}` },
        signal: abortRef.current.signal,
      });
      if (!res.ok) throw new Error(`Failed to fetch policies: ${res.status}`);
      const data = await res.json();
      const parsed = z.object({ policies: z.array(PolicyDraftSchema) }).safeParse(data);
      if (!parsed.success) throw new Error("Invalid response shape");
      if (mountedRef.current) {
        setPolicies(parsed.data.policies);
      }
    } catch (err) {
      if (err instanceof DOMException && err.name === "AbortError") return;
      if (mountedRef.current) {
        setError(err instanceof Error ? err.message : "Failed to load policies");
      }
    } finally {
      if (mountedRef.current) setLoading(false);
    }
  }, [getToken]);

  useEffect(() => {
    fetchPolicies();
  }, [fetchPolicies]);

  // Auto-select first policy once loaded
  useEffect(() => {
    if (!selectedId && policies.length > 0) {
      setSelectedId(policies[0].id);
    }
  }, [policies, selectedId]);

  // Fetch full policy content when selection changes
  useEffect(() => {
    if (!selectedId) {
      setSelectedPolicy(null);
      return;
    }
    let cancelled = false;
    (async () => {
      setLoadingPolicy(true);
      try {
        const token = await getToken();
        policyAbortRef.current?.abort();
        policyAbortRef.current = new AbortController();
        const res = await fetch(`/api/policies/${selectedId}`, {
          headers: { Authorization: `Bearer ${token}` },
          signal: policyAbortRef.current.signal,
        });
        if (!res.ok) throw new Error(`Failed to fetch policy: ${res.status}`);
        const raw = await res.json();
        const parsed = PolicyDraftSchema.safeParse(raw);
        if (!cancelled && parsed.success && mountedRef.current) {
          setSelectedPolicy(parsed.data);
        }
      } catch (err) {
        if (err instanceof DOMException && err.name === "AbortError") return;
        if (!cancelled && mountedRef.current) {
          setError(err instanceof Error ? err.message : "Failed to load policy");
        }
      } finally {
        if (!cancelled && mountedRef.current) setLoadingPolicy(false);
      }
    })();
    return () => { cancelled = true; };
  }, [selectedId, getToken]);

  const handleSave = useCallback(
    async (content: string) => {
      if (!selectedId) return;
      setSaving(true);
      try {
        const token = await getToken();
        const controller = new AbortController();
        const res = await fetch(`/api/policies/${selectedId}`, {
          method: "PATCH",
          headers: {
            Authorization: `Bearer ${token}`,
            "Content-Type": "application/json",
          },
          body: JSON.stringify({ content }),
          signal: controller.signal,
        });
        if (!res.ok) throw new Error(`Save failed: ${res.status}`);
        const raw = await res.json();
        const parsed = PolicyDraftSchema.safeParse(raw);
        if (parsed.success && mountedRef.current) {
          setSelectedPolicy(parsed.data);
          setPolicies((prev) =>
            prev.map((p) => (p.id === parsed.data.id ? { ...parsed.data, content: "" } : p))
          );
        }
      } catch (err) {
        if (mountedRef.current) {
          setError(err instanceof Error ? err.message : "Save failed");
        }
      } finally {
        if (mountedRef.current) setSaving(false);
      }
    },
    [getToken, selectedId]
  );

  const handleDownload = useCallback(
    async (format: "md" | "docx") => {
      if (!selectedId) return;
      try {
        const token = await getToken();
        const controller = new AbortController();
        const res = await fetch(
          `/api/policies/${selectedId}/download?format=${format}`,
          {
            headers: { Authorization: `Bearer ${token}` },
            signal: controller.signal,
          }
        );
        if (!res.ok) throw new Error(`Download failed: ${res.status}`);
        const blob = await res.blob();
        const url = URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url;
        a.download =
          selectedPolicy?.title?.replace(/\s+/g, "_") + `_v${selectedPolicy?.version}.${format}`;
        a.click();
        URL.revokeObjectURL(url);
      } catch (err) {
        if (mountedRef.current) {
          setError(err instanceof Error ? err.message : "Download failed");
        }
      }
    },
    [getToken, selectedId, selectedPolicy]
  );

  const handleDraft = useCallback(
    async (policyType: PolicyType) => {
      setDraftingType(policyType);
      setError(null);
      const controller = new AbortController();
      try {
        const token = await getToken();
        const res = await fetch("/api/chat", {
          method: "POST",
          headers: {
            Authorization: `Bearer ${token}`,
            "Content-Type": "application/json",
          },
          body: JSON.stringify({
            messages: [
              {
                role: "user",
                content: `Draft a ${POLICY_TYPE_LABELS[policyType]} for my organization.`,
              },
            ],
            intent: "draft_policy",
            policy_type: policyType,
          }),
          signal: controller.signal,
        });
        if (!res.ok) throw new Error(`Draft request failed: ${res.status}`);
        // Drain the SSE stream body so the upstream connection closes cleanly
        if (res.body) {
          const reader = res.body.getReader();
          while (true) {
            const { done } = await reader.read();
            if (done) break;
          }
        }
        // Refresh the policies list after the stream completes
        if (mountedRef.current) await fetchPolicies();
      } catch (err) {
        if (err instanceof DOMException && err.name === "AbortError") return;
        if (mountedRef.current) {
          setError(err instanceof Error ? err.message : "Draft failed");
        }
      } finally {
        if (mountedRef.current) setDraftingType(null);
      }
    },
    [getToken, fetchPolicies]
  );

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64" role="status">
        <p className="text-muted-foreground">Loading policies...</p>
      </div>
    );
  }

  return (
    <IslandErrorBoundary name="PoliciesPage">
      <div className="flex gap-6 h-[calc(100vh-120px)]">
        {/* Left sidebar — policy list + draft buttons */}
        <div className="w-72 flex-shrink-0 flex flex-col gap-4">
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-sm">Your Policies</CardTitle>
            </CardHeader>
            <CardContent className="flex flex-col gap-1">
              {policies.length === 0 ? (
                <p className="text-sm text-muted-foreground">
                  No policies yet. Draft one below.
                </p>
              ) : (
                policies.map((p) => (
                  <PolicyListItem
                    key={p.id}
                    policy={p}
                    selected={p.id === selectedId}
                    onClick={() => setSelectedId(p.id)}
                  />
                ))
              )}
            </CardContent>
          </Card>

          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-sm">Draft New Policy</CardTitle>
            </CardHeader>
            <CardContent className="flex flex-col gap-2">
              {(
                ["irp", "access_control", "change_management", "vendor_management"] as PolicyType[]
              ).map((pt) => (
                <DraftPolicyButton
                  key={pt}
                  policyType={pt}
                  onDraft={handleDraft}
                  active={draftingType === pt}
                />
              ))}
            </CardContent>
          </Card>
        </div>

        {/* Right pane — editor */}
        <div className="flex-1 min-w-0">
          {error && (
            <div
              className="mb-4 p-3 bg-destructive/10 text-destructive rounded-md text-sm"
              role="alert"
              aria-live="assertive"
            >
              {error}
              <button
                className="ml-2 underline"
                onClick={() => setError(null)}
              >
                Dismiss
              </button>
            </div>
          )}

          {loadingPolicy ? (
            <div className="flex items-center justify-center h-full text-muted-foreground">
              <p>Loading policy...</p>
            </div>
          ) : selectedPolicy ? (
            <PolicyEditorContent
              policy={selectedPolicy}
              onSave={handleSave}
              onDownload={handleDownload}
              saving={saving}
            />
          ) : (
            <div className="flex items-center justify-center h-full text-muted-foreground">
              <p>Select a policy from the sidebar or draft a new one.</p>
            </div>
          )}
        </div>
      </div>
    </IslandErrorBoundary>
  );
}
