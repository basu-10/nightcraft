export default function LoginPage() {
  const urlParams = new URLSearchParams(window.location.search);
  const nextTarget = (urlParams.get("next") || "/").startsWith("/") ? (urlParams.get("next") || "/") : "/";
  const ssoBasePath = window.location.pathname.startsWith("/seeksage") ? "/seeksage" : "";

  return (
    <div className="page-shell">
      <div className="bg-layer" />
      <div className="card auth-card">
        <p className="live-badge"><span className="live-dot"></span> SeekSage</p>
        <h1>SeekSage</h1>
        <p className="subtle">
          Start here and continue with the shared login used across the platform.
        </p>

        <a className="link-btn link-anchor" href={`${ssoBasePath}/auth/sso/login?next=${encodeURIComponent(nextTarget)}`}>
          Continue With Shared SSO
        </a>
      </div>
    </div>
  );
}
