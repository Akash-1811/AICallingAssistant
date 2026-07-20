import { useEffect, useState } from "react";
import { createPortal } from "react-dom";
import { Link, NavLink, useMatch, useNavigate } from "react-router-dom";
import { useAuth } from "../auth/AuthContext";
import { useTheme } from "../theme/ThemeProvider";
import styles from "./Sidebar.module.css";

interface Props {
  isLive?: boolean;
}

// The nav itself is identical on desktop and mobile — only where it renders
// differs: inline in the layout flow on desktop, or as an overlay drawer
// (portaled to <body> so it can't be clipped by the shell's overflow:hidden)
// on mobile. Desktop's DOM/CSS path is untouched either way.
export function Sidebar({ isLive = false }: Props) {
  const [mobileOpen, setMobileOpen] = useState(false);

  useEffect(() => {
    if (!mobileOpen) return;
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    function onKeyDown(e: KeyboardEvent) {
      if (e.key === "Escape") setMobileOpen(false);
    }
    window.addEventListener("keydown", onKeyDown);
    return () => {
      document.body.style.overflow = previousOverflow;
      window.removeEventListener("keydown", onKeyDown);
    };
  }, [mobileOpen]);

  return (
    <>
      {/* In normal document flow (not fixed) so it pushes page content down
          instead of floating over it — only shown below 768px. */}
      <div className={styles.mobileTopbar}>
        <button
          type="button"
          className={styles.mobileMenuBtn}
          onClick={() => setMobileOpen(true)}
          aria-label="Open menu"
        >
          <MenuIcon />
        </button>
        <span className={styles.mobileTopbarBrand}>AI Sales Assistant</span>
      </div>
      <SidebarPanel isLive={isLive} variant="inline" />
      {mobileOpen
        ? createPortal(
            <>
              <div className={styles.backdrop} onClick={() => setMobileOpen(false)} />
              <SidebarPanel isLive={isLive} variant="drawer" onNavigate={() => setMobileOpen(false)} />
            </>,
            document.body
          )
        : null}
    </>
  );
}

function SidebarPanel({
  isLive = false,
  variant,
  onNavigate,
}: {
  isLive?: boolean;
  variant: "inline" | "drawer";
  onNavigate?: () => void;
}) {
  const { theme, toggleTheme } = useTheme();
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const onLiveRoute = useMatch({ path: "/live", end: true });

  function handleLogout() {
    logout();
    navigate("/login", { replace: true });
  }

  return (
    <aside
      className={`${styles.sidebar} ${variant === "drawer" ? styles.sidebarDrawer : styles.sidebarInline}`}
      onClick={(e) => {
        if (onNavigate && (e.target as HTMLElement).closest("a,button")) onNavigate();
      }}
    >
      <div className={styles.brand}>
        <div className={styles.logo} aria-hidden="true">
          <svg width="22" height="22" viewBox="0 0 24 24" fill="none">
            <path
              d="M12 2L3 7v10l9 5 9-5V7l-9-5z"
              stroke="currentColor"
              strokeWidth="1.35"
              strokeLinejoin="round"
            />
            <path d="M12 22V12" stroke="currentColor" strokeWidth="1.35" strokeLinecap="round" />
          </svg>
        </div>
        <div className={styles.brandText}>
          <span className={styles.brandName}>AI Sales&nbsp;<wbr />Assistant</span>
          <span className={styles.brandSub}>Powered by HubCode</span>
        </div>
        {variant === "drawer" ? (
          <button type="button" className={styles.drawerCloseBtn} onClick={onNavigate} aria-label="Close menu">
            <CloseIcon />
          </button>
        ) : null}
      </div>

      <nav className={styles.nav} aria-label="Main navigation">
        <NavLink
          to="/"
          end
          className={({ isActive }) =>
            `${styles.navItem} ${isActive ? styles.navActive : ""}`
          }
        >
          <span className={styles.navIcon} aria-hidden="true">
            <GridIcon />
          </span>
          <span className={styles.navLabel}>Dashboard</span>
        </NavLink>
        <NavLink
          to="/live"
          className={({ isActive }) =>
            `${styles.navItem} ${isActive ? styles.navActive : ""}`
          }
        >
          <span className={styles.navIcon} aria-hidden="true">
            <PhoneIcon />
          </span>
          <span className={styles.navLabel}>Live Calls</span>
          {isLive && onLiveRoute != null ? <span className={styles.liveDot} aria-label="live" /> : null}
        </NavLink>
        <NavLink
          to="/knowledge"
          className={({ isActive }) =>
            `${styles.navItem} ${isActive ? styles.navActive : ""}`
          }
        >
          <span className={styles.navIcon} aria-hidden="true">
            <BookIcon />
          </span>
          <span className={styles.navLabel}>Knowledge Base</span>
        </NavLink>
        <NavLink
          to="/analytics"
          className={({ isActive }) =>
            `${styles.navItem} ${isActive ? styles.navActive : ""}`
          }
        >
          <span className={styles.navIcon} aria-hidden="true">
            <ChartIcon />
          </span>
          <span className={styles.navLabel}>Call insights</span>
        </NavLink>
      </nav>

      <Link to="/live" className={styles.newSession}>
        <PlusIcon />
        New Session
      </Link>

      <div className={styles.navFooter}>
        <button
          type="button"
          className={`${styles.navItem} ${styles.navCompact} ${styles.themeToggle}`}
          onClick={toggleTheme}
          aria-label={theme === "dark" ? "Switch to light mode" : "Switch to dark mode"}
        >
          <span className={styles.navIcon} aria-hidden="true">
            {theme === "dark" ? <SunIcon /> : <MoonIcon />}
          </span>
          <span className={styles.navLabel}>{theme === "dark" ? "Light mode" : "Dark mode"}</span>
        </button>
        {user ? (
          <>
            <div className={`${styles.navItem} ${styles.navCompact}`} title={user.email}>
              <span className={styles.navIcon} aria-hidden="true">
                <UserPlusIcon />
              </span>
              <span className={styles.navLabel}>{user.display_name || user.email}</span>
            </div>
            <button
              type="button"
              className={`${styles.navItem} ${styles.navCompact}`}
              onClick={handleLogout}
            >
              <span className={styles.navIcon} aria-hidden="true">
                <LogInIcon />
              </span>
              <span className={styles.navLabel}>Log out</span>
            </button>
          </>
        ) : (
          <>
            <NavLink
              to="/signup"
              className={({ isActive }) =>
                `${styles.navItem} ${styles.navCompact} ${isActive ? styles.navActive : ""}`
              }
            >
              <span className={styles.navIcon} aria-hidden="true">
                <UserPlusIcon />
              </span>
              <span className={styles.navLabel}>Sign up</span>
            </NavLink>
            <NavLink
              to="/login"
              className={({ isActive }) =>
                `${styles.navItem} ${styles.navCompact} ${isActive ? styles.navActive : ""}`
              }
            >
              <span className={styles.navIcon} aria-hidden="true">
                <LogInIcon />
              </span>
              <span className={styles.navLabel}>Log in</span>
            </NavLink>
          </>
        )}
        <NavPlaceholder icon={<GearIcon />} label="Settings" compact />
        <NavPlaceholder icon={<LifeRingIcon />} label="Support" compact />
      </div>
    </aside>
  );
}

function NavPlaceholder({
  icon,
  label,
  compact = false,
}: {
  icon: React.ReactNode;
  label: string;
  compact?: boolean;
}) {
  return (
    <button
      type="button"
      className={`${styles.navItem} ${styles.navPlaceholder} ${compact ? styles.navCompact : ""}`}
      disabled
      title="Coming soon"
    >
      <span className={styles.navIcon} aria-hidden="true">
        {icon}
      </span>
      <span className={styles.navLabel}>{label}</span>
    </button>
  );
}

function MenuIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <line x1="3" y1="6" x2="21" y2="6" />
      <line x1="3" y1="12" x2="21" y2="12" />
      <line x1="3" y1="18" x2="21" y2="18" />
    </svg>
  );
}

function CloseIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <line x1="18" y1="6" x2="6" y2="18" />
      <line x1="6" y1="6" x2="18" y2="18" />
    </svg>
  );
}

function MoonIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z" />
    </svg>
  );
}

function SunIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <circle cx="12" cy="12" r="4" />
      <path d="M12 2v2M12 20v2M4.93 4.93l1.41 1.41M17.66 17.66l1.41 1.41M2 12h2M20 12h2M6.34 17.66l-1.41 1.41M19.07 4.93l-1.41 1.41" />
    </svg>
  );
}

function UserPlusIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M16 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2" />
      <circle cx="8.5" cy="7" r="4" />
      <line x1="20" y1="8" x2="20" y2="14" />
      <line x1="23" y1="11" x2="17" y2="11" />
    </svg>
  );
}

function LogInIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M15 3h4a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2h-4" />
      <polyline points="10 17 15 12 10 7" />
      <line x1="15" y1="12" x2="3" y2="12" />
    </svg>
  );
}

function PlusIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" aria-hidden="true">
      <line x1="12" y1="5" x2="12" y2="19" />
      <line x1="5" y1="12" x2="19" y2="12" />
    </svg>
  );
}

function GridIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <rect x="3" y="3" width="7" height="7" />
      <rect x="14" y="3" width="7" height="7" />
      <rect x="14" y="14" width="7" height="7" />
      <rect x="3" y="14" width="7" height="7" />
    </svg>
  );
}

function PhoneIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M22 16.92v3a2 2 0 0 1-2.18 2 19.79 19.79 0 0 1-8.63-3.07A19.5 19.5 0 0 1 4.69 12 19.79 19.79 0 0 1 1.61 3.5 2 2 0 0 1 3.6 1.3h3a2 2 0 0 1 2 1.72 12.84 12.84 0 0 0 .7 2.81 2 2 0 0 1-.45 2.11L7.91 9a16 16 0 0 0 6 6l.92-.92a2 2 0 0 1 2.11-.45 12.84 12.84 0 0 0 2.81.7A2 2 0 0 1 22 16.92z" />
    </svg>
  );
}

function BookIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20" />
      <path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z" />
    </svg>
  );
}

function ChartIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <line x1="18" y1="20" x2="18" y2="10" />
      <line x1="12" y1="20" x2="12" y2="4" />
      <line x1="6" y1="20" x2="6" y2="14" />
    </svg>
  );
}

function GearIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="12" cy="12" r="3" />
      <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z" />
    </svg>
  );
}

function LifeRingIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="12" cy="12" r="10" />
      <circle cx="12" cy="12" r="4" />
      <line x1="4.93" y1="4.93" x2="9.17" y2="9.17" />
      <line x1="14.83" y1="14.83" x2="19.07" y2="19.07" />
      <line x1="14.83" y1="9.17" x2="19.07" y2="4.93" />
      <line x1="14.83" y1="9.17" x2="18.36" y2="5.64" />
      <line x1="4.93" y1="19.07" x2="9.17" y2="14.83" />
    </svg>
  );
}
