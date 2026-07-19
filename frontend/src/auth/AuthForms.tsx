import { FormEvent, useState, type ReactNode } from "react";
import { Link, useNavigate } from "react-router-dom";
import { AuthSplitLayout } from "../components/AuthSplitLayout";
import { useAuth } from "./AuthContext";
import styles from "../pages/LoginPage.module.css";

const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

type Mode = "login" | "signup";

const COPY = {
  login: {
    title: "Log into your account",
    emailLabel: "Email",
    submit: "Log in",
    busy: "Logging in…",
    footer: "Don't have an account?",
    footerLink: "/signup",
    footerText: "Sign up",
    formClass: `${styles.authForm} ${styles.authFormLogin}`,
  },
  signup: {
    title: "Create your account",
    emailLabel: "Work email",
    submit: "Create account",
    busy: "Creating account…",
    footer: "Already have an account?",
    footerLink: "/login",
    footerText: "Log in",
    formClass: styles.authForm,
  },
} as const;

function AuthField({
  id,
  label,
  labelExtra,
  type = "text",
  autoComplete,
  placeholder,
  value,
  onChange,
  error,
}: {
  id: string;
  label: string;
  labelExtra?: ReactNode;
  type?: string;
  autoComplete?: string;
  placeholder?: string;
  value: string;
  onChange: (value: string) => void;
  error?: string;
}) {
  return (
    <div className={`${styles.field} ${error ? styles.fieldError : ""}`}>
      <label className={styles.label} htmlFor={id}>
        {label}
        {labelExtra}
      </label>
      <input
        id={id}
        name={id}
        type={type}
        autoComplete={autoComplete}
        className={styles.textInput}
        placeholder={placeholder}
        value={value}
        onChange={(e) => onChange(e.target.value)}
      />
      {error ? <p className={styles.fieldHint}>{error}</p> : null}
    </div>
  );
}

export function AuthForms({ mode }: { mode: Mode }) {
  const navigate = useNavigate();
  const { login, signup } = useAuth();
  const copy = COPY[mode];
  const prefix = mode;

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [confirm, setConfirm] = useState("");
  const [touched, setTouched] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const emailErr = touched && email && !EMAIL_RE.test(email) ? "Enter a valid email address." : undefined;
  const passwordErr =
    touched && mode === "login" && !password ? "Password is required." : undefined;
  const passwordShort =
    touched && mode === "signup" && password && password.length < 8 ? "Use at least 8 characters." : undefined;
  const confirmErr =
    touched && mode === "signup" && confirm && password !== confirm ? "Passwords do not match." : undefined;

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setTouched(true);
    setError(null);
    const trimmed = email.trim();
    if (!trimmed || !password || !EMAIL_RE.test(trimmed)) return;
    if (mode === "signup" && (password.length < 8 || password !== confirm)) return;

    setSubmitting(true);
    try {
      if (mode === "login") await login(trimmed, password);
      else await signup(trimmed, password, displayName);
      navigate("/", { replace: true });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Something went wrong");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <AuthSplitLayout contextMode={mode} mainWide>
      <h1 className={styles.title}>{copy.title}</h1>

      <form className={copy.formClass} onSubmit={handleSubmit} noValidate>
        <AuthField
          id={`${prefix}-email`}
          label={copy.emailLabel}
          type="email"
          autoComplete="email"
          placeholder="you@company.com"
          value={email}
          onChange={setEmail}
          error={emailErr}
        />

        {mode === "signup" ? (
          <AuthField
            id={`${prefix}-name`}
            label="Display name"
            labelExtra={<span className={styles.labelMuted}> (optional)</span>}
            autoComplete="name"
            placeholder="Alex Rivera"
            value={displayName}
            onChange={setDisplayName}
          />
        ) : null}

        <AuthField
          id={`${prefix}-password`}
          label="Password"
          type="password"
          autoComplete={mode === "login" ? "current-password" : "new-password"}
          placeholder={mode === "login" ? "Enter your password" : "At least 8 characters"}
          value={password}
          onChange={setPassword}
          error={passwordErr || passwordShort}
        />

        {mode === "signup" ? (
          <AuthField
            id={`${prefix}-confirm`}
            label="Confirm password"
            type="password"
            autoComplete="new-password"
            placeholder="Repeat password"
            value={confirm}
            onChange={setConfirm}
            error={confirmErr}
          />
        ) : null}

        {error ? <p className={styles.fieldHint}>{error}</p> : null}

        <button type="submit" className={`${styles.btn} ${styles.btnPrimary}`} disabled={submitting}>
          {submitting ? copy.busy : copy.submit}
        </button>
      </form>

      <p className={styles.loginRow}>
        {copy.footer}
        <Link to={copy.footerLink} className={styles.loginLink}>
          {copy.footerText}
        </Link>
      </p>
    </AuthSplitLayout>
  );
}
