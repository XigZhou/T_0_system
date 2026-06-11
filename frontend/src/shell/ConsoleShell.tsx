import { useEffect, useState, type ReactNode } from "react";
import { useLocation } from "react-router-dom";
import { Sidebar } from "./Sidebar";
import { Topbar } from "./Topbar";
import { findRoute } from "../navigation/menu";

export type CurrentUser = {
  username?: string;
  display_name?: string;
  email?: string;
  role?: string;
  is_admin?: boolean;
};

type ConsoleShellProps = {
  children: ReactNode;
};

export function ConsoleShell({ children }: ConsoleShellProps) {
  const [darkMode, setDarkMode] = useState(false);
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [currentUser, setCurrentUser] = useState<CurrentUser | null>(null);
  const [authLoading, setAuthLoading] = useState(true);
  const location = useLocation();
  const route = findRoute(location.pathname);
  const crumbs = route ? [route.groupLabel, route.label] : ["\u7cfb\u7edf", "\u9875\u9762\u672a\u627e\u5230"];

  useEffect(() => {
    let cancelled = false;
    async function loadCurrentUser() {
      try {
        const response = await fetch("/api/auth/me", { credentials: "include" });
        if (!response.ok) return;
        const data = await response.json() as { authenticated?: boolean; user?: CurrentUser | null };
        if (!cancelled) setCurrentUser(data.authenticated ? data.user || null : null);
      } finally {
        if (!cancelled) setAuthLoading(false);
      }
    }
    void loadCurrentUser().catch(() => {
      if (!cancelled) setAuthLoading(false);
    });
    return () => { cancelled = true; };
  }, []);

  return (
    <div className={darkMode ? "app-root dark" : "app-root"}>
      <div className="console-shell">
        <Sidebar collapsed={sidebarCollapsed} currentUser={currentUser} authLoading={authLoading} />
        <div className="workspace-shell">
          <Topbar
            crumbs={crumbs}
            currentUser={currentUser}
            authLoading={authLoading}
            darkMode={darkMode}
            onToggleDark={() => setDarkMode((value) => !value)}
            sidebarCollapsed={sidebarCollapsed}
            onToggleSidebar={() => setSidebarCollapsed((value) => !value)}
          />
          <main className="workspace-main">{children}</main>
        </div>
      </div>
    </div>
  );
}
