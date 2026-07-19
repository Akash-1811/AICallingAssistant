import { Outlet } from "react-router-dom";
import { useAssistantWs } from "./hooks/useAssistantWs";
import { Sidebar } from "./components/Sidebar";
import styles from "./App.module.css";

export function AppLayout() {
  const assistant = useAssistantWs();
  const isLive = assistant.status === "live";

  return (
    <div className={styles.shell}>
      <div className={styles.shellMain}>
        <Sidebar isLive={isLive} />
        <div className={styles.workspace}>
          <Outlet context={assistant} />
        </div>
      </div>

      <footer className={styles.siteFooter}>
        <span className={styles.footerCopy}>
          © {new Date().getFullYear()} AI Sales Assistant · Powered by HubCode
        </span>
        <nav className={styles.footerNav} aria-label="Footer">
          <a href="/docs" className={styles.footerLink}>
            Privacy
          </a>
          <a href="/docs" className={styles.footerLink}>
            Security
          </a>
          <a href="/health" className={styles.footerLink}>
            Status
          </a>
        </nav>
      </footer>
    </div>
  );
}
