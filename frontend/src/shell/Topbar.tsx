import { useEffect, useRef, useState } from "react";
import { Bell, ChevronDown, LogOut, Moon, PanelLeft, PanelLeftClose, Sun, User } from "lucide-react";
import type { CurrentUser } from "./ConsoleShell";

type TopbarProps = {
  crumbs: string[];
  currentUser: CurrentUser | null;
  authLoading: boolean;
  darkMode: boolean;
  onToggleDark: () => void;
  sidebarCollapsed: boolean;
  onToggleSidebar: () => void;
};

const label = {
  fallbackUser: "\u7814\u7a76\u5458",
  loadingUser: "\u8bfb\u53d6\u4e2d",
  adminRole: "\u7ba1\u7406\u5458",
  userRole: "\u666e\u901a\u7528\u6237",
  guestRole: "\u672a\u767b\u5f55",
  profile: "\u4e2a\u4eba\u8d44\u6599",
  logout: "\u9000\u51fa\u767b\u5f55",
  toggleSidebar: "\u5207\u6362\u4fa7\u8fb9\u680f",
  breadcrumbs: "\u9762\u5305\u5c51",
  notifications: "\u901a\u77e5",
  toggleTheme: "\u5207\u6362\u4e3b\u9898",
  userMenu: "\u7528\u6237\u83dc\u5355",
  openUserMenu: "\u6253\u5f00\u7528\u6237\u83dc\u5355"
};

function roleLabel(user: CurrentUser | null): string {
  if (!user) return label.guestRole;
  return user.role === "admin" || user.is_admin ? label.adminRole : label.userRole;
}

function initialsFor(name: string): string {
  const clean = String(name || "").trim();
  if (!clean) return "--";
  const asciiParts = clean.match(/[A-Za-z0-9]+/g);
  if (asciiParts?.length) {
    const first = asciiParts[0]?.[0] || "";
    const second = asciiParts.length > 1 ? asciiParts[1]?.[0] || "" : asciiParts[0]?.[1] || "";
    return `${first}${second}`.toUpperCase();
  }
  return clean.slice(0, 2);
}

async function logout() {
  await fetch("/api/auth/logout", { method: "POST", credentials: "include" });
  window.location.href = "/login";
}

export function Topbar({ crumbs, currentUser, authLoading, darkMode, onToggleDark, sidebarCollapsed, onToggleSidebar }: TopbarProps) {
  const [menuOpen, setMenuOpen] = useState(false);
  const menuRef = useRef<HTMLDivElement | null>(null);
  const userLabel = authLoading
    ? label.loadingUser
    : currentUser?.display_name || currentUser?.username || label.fallbackUser;
  const username = currentUser?.username || userLabel;
  const userMeta = currentUser?.email || roleLabel(currentUser);
  const initials = initialsFor(currentUser?.display_name || currentUser?.username || userLabel);

  useEffect(() => {
    if (!menuOpen) return;
    function handlePointerDown(event: PointerEvent) {
      if (menuRef.current && !menuRef.current.contains(event.target as Node)) {
        setMenuOpen(false);
      }
    }
    function handleKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") setMenuOpen(false);
    }
    document.addEventListener("pointerdown", handlePointerDown);
    document.addEventListener("keydown", handleKeyDown);
    return () => {
      document.removeEventListener("pointerdown", handlePointerDown);
      document.removeEventListener("keydown", handleKeyDown);
    };
  }, [menuOpen]);

  function handleProfileClick() {
    return undefined;
  }

  function handleLogout() {
    void logout().catch(() => {
      window.location.href = "/login";
    });
  }

  return (
    <header className="topbar">
      <div className="topbar-left">
        <button className="icon-button" type="button" onClick={onToggleSidebar} aria-label={label.toggleSidebar}>
          {sidebarCollapsed ? <PanelLeft size={17} /> : <PanelLeftClose size={17} />}
        </button>
        <nav className="breadcrumbs" aria-label={label.breadcrumbs}>
          {crumbs.map((crumb, index) => (
            <span className="breadcrumb-item" key={`${crumb}-${index}`}>
              {index > 0 && <span className="breadcrumb-separator">/</span>}
              <span className={index === crumbs.length - 1 ? "breadcrumb-current" : "breadcrumb-muted"}>
                {crumb}
              </span>
            </span>
          ))}
        </nav>
      </div>

      <div className="topbar-actions">
        <button className="icon-button icon-button-dot" type="button" aria-label={label.notifications}>
          <Bell size={17} />
          <span aria-hidden="true" />
        </button>
        <button className="icon-button" type="button" onClick={onToggleDark} aria-label={label.toggleTheme}>
          {darkMode ? <Sun size={17} /> : <Moon size={17} />}
        </button>
        <div className="user-menu-wrap" ref={menuRef}>
          <button
            className={menuOpen ? "user-button user-button-open" : "user-button"}
            type="button"
            title={userLabel}
            aria-label={label.openUserMenu}
            aria-expanded={menuOpen}
            aria-haspopup="menu"
            onClick={() => setMenuOpen((value) => !value)}
          >
            <span className="user-avatar user-avatar-initials">{initials}</span>
            <span className="user-button-copy">
              <span className="user-label">{userLabel}</span>
              <span className="user-role-label">{roleLabel(currentUser)}</span>
            </span>
            <ChevronDown className={menuOpen ? "user-chevron open" : "user-chevron"} size={14} />
          </button>
          {menuOpen && (
            <div className="user-dropdown" role="menu" aria-label={label.userMenu}>
              <div className="user-dropdown-head">
                <strong>{username}</strong>
                <span>{userMeta}</span>
              </div>
              <div className="user-dropdown-section">
                <button className="user-dropdown-item" type="button" role="menuitem" onClick={handleProfileClick}>
                  <User size={15} />
                  <span>{label.profile}</span>
                </button>
              </div>
              <div className="user-dropdown-section">
                <button className="user-dropdown-item danger" type="button" role="menuitem" onClick={handleLogout}>
                  <LogOut size={15} />
                  <span>{label.logout}</span>
                </button>
              </div>
            </div>
          )}
        </div>
      </div>
    </header>
  );
}
