import { useMemo, useState } from "react";
import { ChevronDown, ChevronRight } from "lucide-react";
import { NavLink, useLocation } from "react-router-dom";
import { LogoMark, navGroups } from "../navigation/menu";
import type { CurrentUser } from "./ConsoleShell";

type SidebarProps = {
  collapsed: boolean;
  currentUser: CurrentUser | null;
  authLoading: boolean;
};

const sidebarText = {
  brandTitle: "T_0 \u91cf\u5316\u63a7\u5236\u53f0",
  brandSubtitle: "\u6446\u52a8\u56de\u6d4b\u7cfb\u7edf",
  mainNav: "\u4e3b\u5bfc\u822a"
};

function isAdminUser(user: CurrentUser | null): boolean {
  return user?.role === "admin" || user?.is_admin === true;
}

export function Sidebar({ collapsed, currentUser }: SidebarProps) {
  const [openGroups, setOpenGroups] = useState<Record<string, boolean>>(
    Object.fromEntries(navGroups.map((group) => [group.id, true]))
  );
  const location = useLocation();
  const isAdmin = isAdminUser(currentUser);
  const visibleGroups = useMemo(
    () => navGroups
      .map((group) => ({ ...group, items: group.items.filter((item) => !item.adminOnly || isAdmin) }))
      .filter((group) => group.items.length > 0),
    [isAdmin]
  );

  return (
    <aside className={collapsed ? "sidebar sidebar-collapsed" : "sidebar"}>
      <div className="sidebar-brand">
        <div className="brand-mark">
          <LogoMark />
        </div>
        {!collapsed && (
          <div className="brand-copy">
            <span className="brand-title">{sidebarText.brandTitle}</span>
            <span className="brand-subtitle">{sidebarText.brandSubtitle}</span>
          </div>
        )}
      </div>

      <nav className="sidebar-nav" aria-label={sidebarText.mainNav}>
        {visibleGroups.map((group) => {
          const isOpen = openGroups[group.id];
          return (
            <section className="nav-group" key={group.id}>
              {!collapsed && (
                <button
                  className="nav-group-toggle"
                  type="button"
                  onClick={() =>
                    setOpenGroups((current) => ({
                      ...current,
                      [group.id]: !current[group.id]
                    }))
                  }
                >
                  <span>{group.label}</span>
                  {isOpen ? <ChevronDown size={13} /> : <ChevronRight size={13} />}
                </button>
              )}

              {(isOpen || collapsed) && (
                <div className="nav-items">
                  {group.items.map((item) => (
                    <NavLink
                      className={({ isActive }) =>
                        (isActive || item.aliases?.includes(location.pathname) ? "nav-item nav-item-active" : "nav-item")
                      }
                      key={item.path}
                      title={collapsed ? item.label : undefined}
                      to={item.path}
                    >
                      <span className="nav-item-icon">{item.icon}</span>
                      {!collapsed && <span className="nav-item-label">{item.label}</span>}
                    </NavLink>
                  ))}
                </div>
              )}
            </section>
          );
        })}
      </nav>
    </aside>
  );
}
