import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Checkbox } from "@/components/ui/checkbox";
import { Slider } from "@/components/ui/slider";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { legalAnalysis, submitFeedback, ApiError, type LegalAnalysisResponse } from "@/api/client";
import { useAuthStore } from "@/store/authStore";

export function CaseResearchPage() {
  const navigate = useNavigate();
  const { user, logout } = useAuthStore();

  const [query, setQuery] = useState("");
  const [k, setK] = useState(5);
  const [useLlm, setUseLlm] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<LegalAnalysisResponse | null>(null);
  const [feedbackSent, setFeedbackSent] = useState<Record<number, number>>({});

  async function handleSearch() {
    if (!query.trim()) {
      setError("Please enter a query.");
      return;
    }
    setError(null);
    setLoading(true);
    setResult(null);
    try {
      const res = await legalAnalysis({ query, k, useLlm });
      setResult(res);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Search failed");
    } finally {
      setLoading(false);
    }
  }

  async function handleRate(queryId: number, rating: number) {
    setFeedbackSent((prev) => ({ ...prev, [queryId]: rating }));
    try {
      await submitFeedback({ queryId, rating });
    } catch {
      // non-critical — leave the optimistic UI state as-is
    }
  }

  function handleLogout() {
    logout();
    navigate("/login");
  }

  return (
    <div className="mx-auto max-w-3xl p-6">
      <div className="mb-6 flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold">🔍 Case Research</h1>
          <p className="text-sm text-muted-foreground">Welcome, {user?.username}</p>
        </div>
        <div className="flex gap-2">
          <Link to="/history">
            <Button variant="secondary">📜 History</Button>
          </Link>
          <Button variant="secondary" onClick={handleLogout}>
            Logout
          </Button>
        </div>
      </div>

      <Card className="mb-6">
        <CardContent className="flex flex-col gap-4 pt-6">
          <p className="text-sm text-muted-foreground">
            Enter a legal question or claim. The system retrieves the most similar cases from the
            corpus and highlights the sentence(s) in each case that most likely support it.
          </p>
          <Textarea
            placeholder="e.g. Can a landlord terminate a lease without notice for late rent?"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            rows={4}
          />
          <div>
            <label className="mb-2 block text-sm font-medium">Number of cases to retrieve: {k}</label>
            <Slider value={[k]} onValueChange={([v]) => setK(v)} min={1} max={10} step={1} />
          </div>
          <label className="flex items-center gap-2 text-sm">
            <Checkbox checked={useLlm} onCheckedChange={(v) => setUseLlm(Boolean(v))} />
            🤖 Generate an LLM answer with verified citations (calls OpenAI API — costs credits)
          </label>
          {error && <p className="text-sm text-destructive">{error}</p>}
          <Button onClick={handleSearch} disabled={loading}>
            {loading ? "Searching…" : "Search"}
          </Button>
        </CardContent>
      </Card>

      {result && (
        <div className="flex flex-col gap-4">
          <p className="text-sm text-muted-foreground">
            Found {result.cases.length} case(s) · {result.latency_ms}ms · model: {result.model}
          </p>

          {result.answer && (
            <Card>
              <CardHeader>
                <CardTitle className="text-base">🤖 Generated answer</CardTitle>
              </CardHeader>
              <CardContent className="flex flex-col gap-3">
                <p>{result.answer}</p>
                <p className="text-xs text-muted-foreground">
                  🟢 green = exact quote verified against the source · 🟠 orange = model
                  paraphrased; showing the closest matching sentence instead
                </p>
                <FeedbackWidget
                  queryId={result.queryId}
                  currentRating={feedbackSent[result.queryId]}
                  onRate={(rating) => handleRate(result.queryId, rating)}
                />
              </CardContent>
            </Card>
          )}

          {result.cases.map((c) => (
            <Card key={c.case_id}>
              <CardHeader>
                <CardTitle className="text-base">
                  {c.case_name} — {c.citation}{" "}
                  <span className="font-normal text-muted-foreground">
                    (similarity: {c.score.toFixed(2)})
                  </span>
                </CardTitle>
              </CardHeader>
              <CardContent>
                <div
                  className="max-h-[400px] overflow-y-auto rounded border p-3 text-sm leading-relaxed"
                  dangerouslySetInnerHTML={{ __html: c.highlighted_html }}
                />
              </CardContent>
            </Card>
          ))}

          {!result.answer && (
            <FeedbackWidget
              queryId={result.queryId}
              currentRating={feedbackSent[result.queryId]}
              onRate={(rating) => handleRate(result.queryId, rating)}
            />
          )}
        </div>
      )}
    </div>
  );
}

function FeedbackWidget({
  queryId,
  currentRating,
  onRate,
}: {
  queryId: number;
  currentRating?: number;
  onRate: (rating: number) => void;
}) {
  if (currentRating) {
    return <p className="text-sm text-muted-foreground">Thanks for your feedback! ({currentRating}/5)</p>;
  }
  return (
    <div className="flex items-center gap-2 text-sm">
      <span className="text-muted-foreground">Was this helpful?</span>
      {[1, 2, 3, 4, 5].map((n) => (
        <button
          key={n}
          onClick={() => onRate(n)}
          className="rounded px-2 py-1 hover:bg-accent"
          aria-label={`Rate ${n} out of 5`}
        >
          {n}⭐
        </button>
      ))}
      <span className="sr-only">query {queryId}</span>
    </div>
  );
}
