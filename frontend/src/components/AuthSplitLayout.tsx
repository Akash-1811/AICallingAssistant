import { useEffect, useState, type ReactNode } from "react";
import { Link } from "react-router-dom";
import loginBgVideo from "../Video/LoginBGVideo.mp4";
import { useTheme } from "../theme/ThemeProvider";
import { BrandGlyph, ChevronDownIcon, MiniSuiteIcon, MoonGlyph, SunGlyph } from "../pages/authIcons";
import styles from "../pages/LoginPage.module.css";

type AuthContextMode = "login" | "signup";

interface Props {
  contextMode: AuthContextMode;
  children: ReactNode;
  /** Wider main column for signup form */
  mainWide?: boolean;
}

export function AuthSplitLayout({ contextMode, children, mainWide = false }: Props) {
  const { theme, toggleTheme } = useTheme();
  const [toastOpen, setToastOpen] = useState(true);

  /* Let light mode use global tokens; dark keeps chrome aligned with auth panel */
  useEffect(() => {
    const html = document.documentElement;
    const body = document.body;
    const rootEl = document.getElementById("root");
    if (theme === "dark") {
      html.style.backgroundColor = "#121212";
      body.style.backgroundColor = "#121212";
      if (rootEl) rootEl.style.backgroundColor = "#121212";
    } else {
      html.style.backgroundColor = "";
      body.style.backgroundColor = "";
      if (rootEl) rootEl.style.backgroundColor = "";
    }
    return () => {
      html.style.backgroundColor = "";
      body.style.backgroundColor = "";
      if (rootEl) rootEl.style.backgroundColor = "";
    };
  }, [theme]);

  const contextLead = contextMode === "login" ? "You are signing into" : "You are signing up for";

  return (
    <div className={styles.page}>
      <div className={styles.left}>
        <header className={styles.topBar}>
          <Link to="/" className={styles.brandMark} aria-label="AI Sales Assistant home">
            <BrandGlyph />
            <span>AI Sales Assistant</span>
          </Link>
          <div className={styles.topBarActions}>
            <button
              type="button"
              className={styles.themeIconBtn}
              onClick={toggleTheme}
              aria-label={theme === "dark" ? "Switch to light mode" : "Switch to dark mode"}
            >
              {theme === "dark" ? <SunGlyph /> : <MoonGlyph />}
            </button>
            <button type="button" className={styles.contextPill}>
              {contextLead} <MiniSuiteIcon /> <strong>AI Sales Assistant</strong>
              <span className={styles.chevron} aria-hidden="true">
                <ChevronDownIcon />
              </span>
            </button>
          </div>
        </header>

        <div className={styles.leftBody}>
          <main className={`${styles.main} ${mainWide ? styles.mainWide : ""}`}>{children}</main>
        </div>

        <footer className={styles.footer}>
          By continuing, you agree to AI Sales Assistant&apos;s{" "}
          <a href="/docs">Terms of Service</a> and <a href="/docs">Privacy Policy</a>.
        </footer>
      </div>

      <div className={styles.right}>
        <div className={styles.videoWrap} aria-hidden="true">
          <video
            className={styles.videoBg}
            src={loginBgVideo}
            autoPlay
            muted
            loop
            playsInline
            preload="auto"
          />
          <div className={styles.videoScrim} />
        </div>
        {toastOpen ? (
          <div className={styles.toast} role="status">
            <button type="button" className={styles.toastClose} onClick={() => setToastOpen(false)} aria-label="Dismiss">
              ×
            </button>
            As of April 4, 2026, our Privacy Policy and Cookie Policy have been updated. View them here:
            <div className={styles.toastLinks}>
              <a href="/docs">Privacy Policy</a>
              <a href="/docs">Cookie Policy</a>
            </div>
          </div>
        ) : null}
      </div>
    </div>
  );
}
