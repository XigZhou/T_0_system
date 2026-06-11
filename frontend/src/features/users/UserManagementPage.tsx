import { useEffect, useMemo, useState } from "react";
import { KeyRound, RefreshCw, ShieldAlert, UserCheck, UserX } from "lucide-react";
import "./userManagement.css";

type CurrentUser = { username?: string; display_name?: string; role?: string; is_admin?: boolean };
type ManagedUser = {
  username?: string;
  display_name?: string;
  role?: string;
  is_active?: boolean | number;
  created_at?: string;
  last_login_at?: string;
  password_updated_at?: string;
};
type StatusState = { text: string; error?: boolean };

const txt = {
  title: "\u7528\u6237\u7ba1\u7406",
  eyebrow: "\u7cfb\u7edf\u6743\u9650",
  note: "\u7ba1\u7406\u666e\u901a\u7528\u6237\u72b6\u6001\u548c\u5bc6\u7801\u91cd\u7f6e\uff1b\u8be5\u9875\u9762\u4ec5 admin \u53ef\u89c1\u3002",
  refresh: "\u5237\u65b0\u7528\u6237",
  checking: "\u6b63\u5728\u6821\u9a8c\u767b\u5f55\u7528\u6237\u3002",
  denied: "\u53ea\u6709 admin \u7528\u6237\u53ef\u4ee5\u67e5\u770b\u7528\u6237\u7ba1\u7406\u3002",
  loading: "\u6b63\u5728\u8bfb\u53d6\u7528\u6237\u5217\u8868\uff1b\u672c\u6b21\u4e0d\u4f1a\u5199\u5165\u6570\u636e\u3002",
  loaded: "\u7528\u6237\u5217\u8868\u5df2\u5237\u65b0\uff1b\u672c\u6b21\u53ea\u8bfb\u53d6\u6570\u636e\u3002",
  noUsers: "\u6682\u65e0\u7528\u6237\u8bb0\u5f55\u3002",
  loadFail: "\u8bfb\u53d6\u7528\u6237\u5217\u8868\u5931\u8d25",
  usersTitle: "\u6ce8\u518c\u7528\u6237\u4e0e\u72b6\u6001",
  usersEyebrow: "\u7528\u6237\u5217\u8868",
  usersNote: "\u7981\u7528\u6216\u91cd\u7f6e\u5bc6\u7801\u4f1a\u7acb\u5373\u5199\u5165\u7528\u6237\u8868\uff1badmin \u8d26\u53f7\u4e0d\u5728\u9875\u9762\u4e0a\u64cd\u4f5c\u3002",
  totalUsers: "\u7528\u6237\u603b\u6570",
  activeUsers: "\u542f\u7528\u7528\u6237",
  inactiveUsers: "\u505c\u7528\u7528\u6237",
  adminUsers: "\u7ba1\u7406\u5458",
  username: "\u7528\u6237\u540d",
  displayName: "\u663e\u793a\u540d\u79f0",
  role: "\u89d2\u8272",
  status: "\u72b6\u6001",
  createdAt: "\u521b\u5efa\u65f6\u95f4",
  lastLogin: "\u6700\u8fd1\u767b\u5f55",
  passwordUpdated: "\u5bc6\u7801\u66f4\u65b0",
  actions: "\u64cd\u4f5c",
  adminRole: "\u7ba1\u7406\u5458",
  userRole: "\u666e\u901a\u7528\u6237",
  active: "\u542f\u7528",
  inactive: "\u505c\u7528",
  enable: "\u542f\u7528",
  disable: "\u7981\u7528",
  resetPassword: "\u91cd\u7f6e\u5bc6\u7801",
  adminLocked: "admin \u8d26\u53f7\u9700\u8981\u5728\u670d\u52a1\u5668\u4fa7\u7ef4\u62a4",
  promptPassword: "\u8bf7\u8f93\u5165\u65b0\u5bc6\u7801\uff08\u81f3\u5c118\u4f4d\uff09",
  passwordTooShort: "\u65b0\u5bc6\u7801\u81f3\u5c11\u9700\u8981 8 \u4f4d\uff1b\u672c\u6b21\u6ca1\u6709\u5199\u5165\u6570\u636e\u3002",
  writingStatus: "\u6b63\u5728\u5199\u5165\u7528\u6237\u72b6\u6001...",
  writingPassword: "\u6b63\u5728\u91cd\u7f6e\u7528\u6237\u5bc6\u7801...",
  confirmEnable: "\u786e\u8ba4\u542f\u7528\u8be5\u7528\u6237\uff1f",
  confirmDisable: "\u786e\u8ba4\u7981\u7528\u8be5\u7528\u6237\uff1f",
  noRows: "\u6682\u65e0\u7528\u6237\u3002"
};

function isAdminUser(user: CurrentUser | null): boolean {
  return user?.role === "admin" || user?.is_admin === true;
}

function detailText(error: unknown): string {
  return error instanceof Error ? error.message : String(error || "");
}

async function fetchJson<T>(url: string, options: RequestInit = {}): Promise<T> {
  const response = await fetch(url, { credentials: "include", ...options });
  if (!response.ok) {
    const data = await response.json().catch(() => ({}));
    throw new Error(data.detail || `HTTP ${response.status}`);
  }
  return response.json() as Promise<T>;
}

function formatDate(value: unknown): string {
  return value ? String(value) : "-";
}

function isUserActive(user: ManagedUser): boolean {
  return user.is_active === true || Number(user.is_active) === 1;
}

function formatRole(user: ManagedUser): string {
  return user.role === "admin" ? txt.adminRole : txt.userRole;
}

export function UserManagementPage() {
  const [currentUser, setCurrentUser] = useState<CurrentUser | null>(null);
  const [authLoading, setAuthLoading] = useState(true);
  const [users, setUsers] = useState<ManagedUser[]>([]);
  const [busy, setBusy] = useState(false);
  const [status, setStatus] = useState<StatusState>({ text: txt.checking });
  const isAdmin = isAdminUser(currentUser);

  async function loadUsers(showStatus = true) {
    if (showStatus) setStatus({ text: txt.loading });
    const data = await fetchJson<{ users?: ManagedUser[] }>("/api/users");
    const nextUsers = data.users || [];
    setUsers(nextUsers);
    if (showStatus) {
      setStatus({ text: nextUsers.length ? `${txt.loaded}\u5171 ${nextUsers.length} \u4e2a\u7528\u6237\u3002` : txt.noUsers, error: !nextUsers.length });
    }
  }

  async function boot() {
    setAuthLoading(true);
    try {
      const auth = await fetchJson<{ authenticated?: boolean; user?: CurrentUser | null }>("/api/auth/me");
      const user = auth.authenticated ? auth.user || null : null;
      setCurrentUser(user);
      if (!isAdminUser(user)) {
        setStatus({ text: txt.denied, error: true });
        return;
      }
      await loadUsers(false);
      setStatus({ text: txt.loaded });
    } catch (error) {
      setStatus({ text: `${txt.loadFail}\uff1a${detailText(error)}`, error: true });
    } finally {
      setAuthLoading(false);
    }
  }

  useEffect(() => {
    void boot();
  }, []);

  const summary = useMemo(() => {
    const active = users.filter(isUserActive).length;
    const admin = users.filter((user) => user.role === "admin").length;
    return [
      { key: "total", label: txt.totalUsers, value: users.length },
      { key: "active", label: txt.activeUsers, value: active },
      { key: "inactive", label: txt.inactiveUsers, value: users.length - active },
      { key: "admin", label: txt.adminUsers, value: admin }
    ];
  }, [users]);

  async function toggleStatus(user: ManagedUser) {
    const username = user.username || "";
    if (!username || username === "admin") return;
    const nextActive = !isUserActive(user);
    const confirmed = typeof window.confirm !== "function" ? true : window.confirm(nextActive ? txt.confirmEnable : txt.confirmDisable);
    if (!confirmed) return;
    setBusy(true);
    setStatus({ text: txt.writingStatus });
    try {
      await fetchJson(`/api/users/${encodeURIComponent(username)}/status`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ is_active: nextActive })
      });
      setStatus({ text: `${username} ${nextActive ? txt.active : txt.inactive}\uff0c\u5df2\u5199\u5165\u7528\u6237\u72b6\u6001\u3002` });
      await loadUsers(false);
    } catch (error) {
      setStatus({ text: detailText(error), error: true });
    } finally {
      setBusy(false);
    }
  }

  async function resetPassword(user: ManagedUser) {
    const username = user.username || "";
    if (!username || username === "admin") return;
    const newPassword = typeof window.prompt === "function" ? window.prompt(`${txt.promptPassword}\uff1a${username}`) : "";
    if (!newPassword) return;
    if (newPassword.length < 8) {
      setStatus({ text: txt.passwordTooShort, error: true });
      return;
    }
    setBusy(true);
    setStatus({ text: txt.writingPassword });
    try {
      await fetchJson(`/api/users/${encodeURIComponent(username)}/password`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ new_password: newPassword })
      });
      setStatus({ text: `${username} \u5bc6\u7801\u5df2\u91cd\u7f6e\uff0c\u5df2\u5199\u5165\u7528\u6237\u8868\u3002` });
      await loadUsers(false);
    } catch (error) {
      setStatus({ text: detailText(error), error: true });
    } finally {
      setBusy(false);
    }
  }

  if (authLoading) return <StatusOnly text={txt.checking} />;
  if (!isAdmin) return <StatusOnly text={txt.denied} error />;

  return (
    <section className="user-management-page">
      <div className="user-management-header">
        <div>
          <p className="page-eyebrow">{txt.eyebrow}</p>
          <h1>{txt.title}</h1>
          <p className="user-management-note">{txt.note}</p>
        </div>
        <div className="user-management-actions">
          <button className="secondary-link" type="button" disabled={busy} onClick={() => void loadUsers(true)}><RefreshCw size={14} />{txt.refresh}</button>
        </div>
      </div>

      <div className="metric-strip user-management-metrics">
        {summary.map((item) => <div className="metric-tile" key={item.key}><span>{item.label}</span><strong>{item.value}</strong></div>)}
      </div>
      <StatusLine state={status} />

      <section className="user-management-panel">
        <div className="panel-header user-management-panel-head">
          <div><p className="page-eyebrow">{txt.usersEyebrow}</p><h2>{txt.usersTitle}</h2></div>
          <p>{txt.usersNote}</p>
        </div>
        <div className="table-wrap user-management-table-wrap">
          <table>
            <thead>
              <tr>
                <th>{txt.username}</th>
                <th>{txt.displayName}</th>
                <th>{txt.role}</th>
                <th>{txt.status}</th>
                <th>{txt.createdAt}</th>
                <th>{txt.lastLogin}</th>
                <th>{txt.passwordUpdated}</th>
                <th>{txt.actions}</th>
              </tr>
            </thead>
            <tbody>
              {users.length ? users.map((user, index) => {
                const active = isUserActive(user);
                const username = user.username || "";
                const isBuiltInAdmin = username === "admin";
                return (
                  <tr key={username || index}>
                    <td>{username || "-"}</td>
                    <td>{user.display_name || "-"}</td>
                    <td>{formatRole(user)}</td>
                    <td><span className={active ? "user-status-pill active" : "user-status-pill inactive"}>{active ? txt.active : txt.inactive}</span></td>
                    <td>{formatDate(user.created_at)}</td>
                    <td>{formatDate(user.last_login_at)}</td>
                    <td>{formatDate(user.password_updated_at)}</td>
                    <td>
                      <div className="user-row-actions">
                        <button className="secondary-link small-action" type="button" disabled={busy || isBuiltInAdmin} title={isBuiltInAdmin ? txt.adminLocked : undefined} onClick={() => void toggleStatus(user)}>
                          {active ? <UserX size={13} /> : <UserCheck size={13} />}{active ? txt.disable : txt.enable}
                        </button>
                        <button className="secondary-link small-action" type="button" disabled={busy || isBuiltInAdmin} title={isBuiltInAdmin ? txt.adminLocked : undefined} onClick={() => void resetPassword(user)}>
                          <KeyRound size={13} />{txt.resetPassword}
                        </button>
                      </div>
                    </td>
                  </tr>
                );
              }) : <tr><td colSpan={8}>{txt.noRows}</td></tr>}
            </tbody>
          </table>
        </div>
      </section>
    </section>
  );
}

function StatusOnly({ text, error = false }: { text: string; error?: boolean }) {
  return <section className="user-management-page"><div className={error ? "user-management-denied error" : "user-management-denied"}><ShieldAlert size={18} /><span>{text}</span></div></section>;
}

function StatusLine({ state }: { state: StatusState }) {
  return <p className={state.error ? "user-management-status error" : "user-management-status"}>{state.text}</p>;
}
