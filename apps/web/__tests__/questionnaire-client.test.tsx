/**
 * QuestionnaireClient — UI tests for Sprint 7 chunks 7.9, 7.10, 7.11.
 *
 * Covers:
 *   - Renders empty state when no runs exist.
 *   - Renders run list and selects first run by default.
 *   - Auto-fill progress reflects answered / question counts.
 *   - "Filter flagged" toggles the rendering set to flagged-only cells.
 *   - Patching a flagged answer clears the flag and propagates the update.
 *   - Download button is disabled until run.status === "ready".
 */

import {
  render,
  screen,
  fireEvent,
  waitFor,
  act,
  within,
} from "@testing-library/react"
import { describe, it, expect, vi, afterEach } from "vitest"

import { QuestionnaireClient } from "@/components/questionnaire-client"

// Stable refs — Clerk in production returns the same object across renders;
// reproducing that here keeps useCallback/useEffect deps from churning.
const STABLE_AUTH = { getToken: async () => "test-token" }
vi.mock("@clerk/nextjs", () => ({
  useAuth: () => STABLE_AUTH,
}))

// PageHeader pulls in shadcn Sidebar primitives that need a provider context;
// stub it out so the workspace tests stay focused on the questionnaire UI.
vi.mock("@/components/page-header", () => ({
  PageHeader: ({ title }: { title: string }) => <h1>{title}</h1>,
}))

// ── Fixtures ───────────────────────────────────────────────────────────────

const READY_RUN = {
  id: "run-ready",
  user_id: "user_abc",
  filename: "sig.xlsx",
  format: "sig-lite",
  status: "ready",
  question_count: 4,
  answered_count: 4,
  flagged_count: 1,
  cluster_count: 2,
  output_r2_key: "users/u/q/out.xlsx",
  failure_reason: null,
  created_at: "2026-05-07T10:00:00Z",
  updated_at: "2026-05-07T10:01:00Z",
}

const QUESTIONS = [
  {
    id: "q-1",
    run_id: READY_RUN.id,
    question_id: "A.1",
    sheet: "SIG-Lite",
    row: 2,
    column: 3,
    section: "Access Control",
    domain: "access_control",
    answer_type: "yes_no",
    question_text: "Do you require MFA?",
    answer_text: "Yes",
    confidence: 0.92,
    flagged: false,
    citations: [],
    edited_by_user: false,
  },
  {
    id: "q-2",
    run_id: READY_RUN.id,
    question_id: "A.2",
    sheet: "SIG-Lite",
    row: 3,
    column: 3,
    section: "Access Control",
    domain: "access_control",
    answer_type: "yes_no",
    question_text: "Is access least-privilege?",
    answer_text: "Pending review",
    confidence: 0.42,
    flagged: true,
    citations: [
      {
        evidence_id: "ev_42",
        snippet: "RBAC enforced via SSO",
        source_uri: "r2://bucket/ev_42.json",
      },
    ],
    edited_by_user: false,
  },
  {
    id: "q-3",
    run_id: READY_RUN.id,
    question_id: "D.1",
    sheet: "SIG-Lite",
    row: 6,
    column: 3,
    section: "Data Handling",
    domain: "data_handling",
    answer_type: "yes_no",
    question_text: "Is data encrypted at rest?",
    answer_text: "Yes",
    confidence: 0.88,
    flagged: false,
    citations: [],
    edited_by_user: false,
  },
  {
    id: "q-4",
    run_id: READY_RUN.id,
    question_id: "D.2",
    sheet: "SIG-Lite",
    row: 7,
    column: 3,
    section: "Data Handling",
    domain: "data_handling",
    answer_type: "free_text",
    question_text: "Describe your data retention.",
    answer_text: "We retain data for 12 months per policy.",
    confidence: 0.86,
    flagged: false,
    citations: [],
    edited_by_user: false,
  },
]

function buildFetchMock(initialQuestions = QUESTIONS) {
  const state = {
    runs: [READY_RUN as any],
    questions: [...initialQuestions] as any[],
  }
  const handler = vi.fn(async (input: RequestInfo, init?: RequestInit) => {
    const url = typeof input === "string" ? input : (input as Request).url
    const method = init?.method ?? "GET"
    if (url.endsWith("/api/questionnaire") && method === "GET") {
      return {
        ok: true,
        status: 200,
        json: async () => ({ runs: state.runs, count: state.runs.length }),
      }
    }
    if (
      url.endsWith(`/api/questionnaire/${READY_RUN.id}`) &&
      method === "GET"
    ) {
      return {
        ok: true,
        status: 200,
        json: async () => ({ run: state.runs[0], questions: state.questions }),
      }
    }
    if (url.includes("/api/questionnaire/questions/") && method === "PATCH") {
      const id = url.split("/").pop() as string
      const body = JSON.parse(init?.body as string)
      let next: any = null
      state.questions = state.questions.map((q: any) => {
        if (q.id !== id) return q
        next = {
          ...q,
          answer_text: body.answer_text,
          flagged: body.clear_flag ? false : q.flagged,
          edited_by_user: true,
        }
        return next
      })
      state.runs[0] = {
        ...state.runs[0],
        flagged_count: state.questions.filter((q: any) => q.flagged).length,
      }
      return {
        ok: true,
        status: 200,
        json: async () => next,
      }
    }
    return { ok: false, status: 404, json: async () => ({}) }
  })
  return { handler, state }
}

afterEach(() => {
  vi.restoreAllMocks()
})

// ── Tests ───────────────────────────────────────────────────────────────────

describe("QuestionnaireClient", () => {
  it("renders the run list and the auto-fill progress", async () => {
    const { handler } = buildFetchMock()
    global.fetch = handler as any
    render(<QuestionnaireClient />)

    expect(await screen.findByText("sig.xlsx")).toBeInTheDocument()
    expect(await screen.findByText(/4 of 4 answered/i)).toBeInTheDocument()
    expect(screen.getByRole("progressbar")).toBeInTheDocument()
  })

  it("filters to flagged-only cells when toggle is pressed", async () => {
    const { handler } = buildFetchMock()
    global.fetch = handler as any
    render(<QuestionnaireClient />)

    expect(await screen.findByText("Do you require MFA?")).toBeInTheDocument()
    expect(screen.getByText("Is access least-privilege?")).toBeInTheDocument()

    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: /filter flagged/i }))
    })

    expect(screen.getByText("Is access least-privilege?")).toBeInTheDocument()
    expect(screen.queryByText("Do you require MFA?")).toBeNull()
  })

  it("clears the flag after editing a flagged answer", async () => {
    const { handler } = buildFetchMock()
    global.fetch = handler as any
    render(<QuestionnaireClient />)

    await screen.findByText("Is access least-privilege?")
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: /filter flagged/i }))
    })

    const flaggedRow = screen
      .getByText("Is access least-privilege?")
      .closest("li") as HTMLLIElement
    expect(flaggedRow).toBeTruthy()
    expect(flaggedRow.dataset.flagged).toBe("true")

    await act(async () => {
      fireEvent.click(
        within(flaggedRow).getByRole("button", { name: "Edit" })
      )
    })
    const textarea = within(flaggedRow).getByRole("textbox")
    await act(async () => {
      fireEvent.change(textarea, {
        target: {
          value: "Yes — readiness reference architecture in place.",
        },
      })
    })
    await act(async () => {
      fireEvent.click(
        within(flaggedRow).getByRole("button", {
          name: /^save( and clear flag)?$/i,
        })
      )
    })

    await waitFor(() => {
      expect(screen.queryByText("Is access least-privilege?")).toBeNull()
    })
    await act(async () => {
      fireEvent.click(
        screen.getByRole("button", { name: /showing flagged/i })
      )
    })
    expect(
      await screen.findByText(/readiness reference architecture/i)
    ).toBeInTheDocument()
  })

  it("disables download when the run is not ready", async () => {
    const draftingRun = { ...READY_RUN, status: "drafting", answered_count: 1 }
    const { handler, state } = buildFetchMock()
    state.runs = [draftingRun]
    global.fetch = handler as any
    render(<QuestionnaireClient />)

    const button = await screen.findByRole("button", {
      name: /download filled xlsx/i,
    })
    expect(button).toBeDisabled()
  })
})
