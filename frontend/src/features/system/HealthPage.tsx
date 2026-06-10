import { useEffect, useState } from "react";

type HealthState = {
  loading: boolean;
  status: "checking" | "ok" | "error";
  detail: string;
  checkedAt?: string;
};

const healthText = {
  checkingDetail: "\u6b63\u5728\u68c0\u67e5 FastAPI /health\u3002",
  failed: "\u5065\u5eb7\u68c0\u67e5\u5931\u8d25",
  system: "\u7cfb\u7edf",
  title: "\u5065\u5eb7\u68c0\u67e5",
  retry: "\u91cd\u65b0\u68c0\u67e5",
  fastapiStatus: "FastAPI \u72b6\u6001",
  ok: "\u670d\u52a1\u6b63\u5e38",
  checking: "\u68c0\u67e5\u4e2d",
  error: "\u68c0\u67e5\u5931\u8d25",
  checkedAt: "\u68c0\u67e5\u65f6\u95f4\uff1a"
};

const initialHealthState: HealthState = {
  loading: true,
  status: "checking",
  detail: healthText.checkingDetail
};

export function HealthPage() {
  const [health, setHealth] = useState<HealthState>(initialHealthState);

  async function checkHealth() {
    setHealth((current) => ({ ...current, loading: true, status: "checking", detail: healthText.checkingDetail }));
    try {
      const response = await fetch("/health", { credentials: "include" });
      const payload = await response.json().catch(() => null);
      if (!response.ok) {
        throw new Error(payload?.detail || `HTTP ${response.status}`);
      }
      setHealth({
        loading: false,
        status: payload?.status === "ok" ? "ok" : "error",
        detail: JSON.stringify(payload ?? {}, null, 2),
        checkedAt: new Date().toLocaleString("zh-CN")
      });
    } catch (error) {
      setHealth({
        loading: false,
        status: "error",
        detail: error instanceof Error ? error.message : healthText.failed,
        checkedAt: new Date().toLocaleString("zh-CN")
      });
    }
  }

  useEffect(() => {
    void checkHealth();
  }, []);

  return (
    <section className="placeholder-page health-page">
      <div className="page-header">
        <div>
          <p className="page-eyebrow">{healthText.system}</p>
          <h1>{healthText.title}</h1>
        </div>
        <button className="secondary-link" type="button" onClick={() => void checkHealth()} disabled={health.loading}>
          {healthText.retry}
        </button>
      </div>

      <section className="run-surface">
        <div className="run-copy">
          <p className="surface-label">{healthText.fastapiStatus}</p>
          <p className={`health-status health-status-${health.status}`}>
            {health.status === "ok" ? healthText.ok : health.loading ? healthText.checking : healthText.error}
          </p>
          {health.checkedAt && <p className="health-time">{healthText.checkedAt}{health.checkedAt}</p>}
        </div>
      </section>

      <pre className="health-payload">{health.detail}</pre>
    </section>
  );
}
