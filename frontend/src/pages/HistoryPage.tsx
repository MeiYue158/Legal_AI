import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { getHistory, ApiError, type HistoryItem } from "@/api/client";
import { useAuthStore } from "@/store/authStore";

export function HistoryPage() {
  const navigate = useNavigate();
  const { user, logout } = useAuthStore();

  const [items, setItems] = useState<HistoryItem[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getHistory()
      .then(setItems)
      .catch((err) => setError(err instanceof ApiError ? err.message : "Failed to load history"));
  }, []);

  function handleLogout() {
    logout();
    navigate("/login");
  }

  return (
    <div className="mx-auto max-w-3xl p-6">
      <div className="mb-6 flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold">📜 Query History</h1>
          <p className="text-sm text-muted-foreground">Welcome, {user?.username}</p>
        </div>
        <div className="flex gap-2">
          <Link to="/case-research">
            <Button variant="secondary">← Case Research</Button>
          </Link>
          <Button variant="secondary" onClick={handleLogout}>
            Logout
          </Button>
        </div>
      </div>

      {error && <p className="text-sm text-destructive">{error}</p>}

      {items === null && !error && (
        <p className="text-sm text-muted-foreground">Loading…</p>
      )}

      {items?.length === 0 && (
        <p className="text-sm text-muted-foreground">
          No queries yet — head to Case Research to ask something.
        </p>
      )}

      <div className="flex flex-col gap-4">
        {items?.map((item) => (
          <Card key={item.query_id}>
            <CardHeader>
              <CardTitle className="text-base font-normal">{item.query}</CardTitle>
            </CardHeader>
            <CardContent className="flex flex-wrap items-center gap-x-4 gap-y-1 text-sm text-muted-foreground">
              <span>{new Date(item.created_at).toLocaleString()}</span>
              <span>model: {item.model}</span>
              <span>{item.latency_ms}ms</span>
              <span>
                {item.rating ? (
                  <>rating: {"⭐".repeat(item.rating)}</>
                ) : (
                  "no feedback yet"
                )}
              </span>
              {item.comment && <span>· "{item.comment}"</span>}
            </CardContent>
          </Card>
        ))}
      </div>
    </div>
  );
}
