import type { SyntheticEvent } from "react";
import { ExternalLink, RefreshCw } from "lucide-react";

type LegacyFrameProps = {
  title: string;
  eyebrow: string;
  description: string;
  legacyPath: string;
};

export function LegacyFrame({ title, eyebrow, description, legacyPath }: LegacyFrameProps) {
  const frameName = `legacy-frame-${legacyPath.replace(/[^a-zA-Z0-9]+/g, "-") || "page"}`;
  const isViteDevServer = /^517\d$/.test(window.location.port);
  const frameSrc = isViteDevServer && legacyPath === "/" ? "/__legacy/index" : legacyPath;

  function handleFrameLoad(event: SyntheticEvent<HTMLIFrameElement>) {
    const frameDocument = event.currentTarget.contentDocument;
    const frameWindow = event.currentTarget.contentWindow;
    if (!frameDocument || !frameWindow) return;

    try {
      if (isViteDevServer && legacyPath === "/" && frameWindow.location.pathname === "/") {
        frameWindow.location.replace(frameSrc);
        return;
      }

      frameDocument.body.classList.add("embedded-console-page");
      if (!frameDocument.getElementById("embedded-console-style")) {
        const style = frameDocument.createElement("style");
        style.id = "embedded-console-style";
        style.textContent = `
          body.embedded-console-page { background: #fff; }
          body.embedded-console-page .brand-actions { display: none !important; }
          body.embedded-console-page .brand-block { margin-bottom: 12px !important; }
          body.embedded-console-page .brand-block .eyebrow { display: none !important; }
          body.embedded-console-page .brand-block h1 { font-size: 22px !important; line-height: 1.25 !important; }
          body.embedded-console-page .shell { min-height: 100vh !important; padding: 14px !important; }
          body.embedded-console-page .controls { border-radius: 8px !important; }
          body.embedded-console-page .workspace { min-width: 0 !important; }
          body.embedded-console-page a[href="/sector"],
          body.embedded-console-page a[href="/stock-pools"],
          body.embedded-console-page a[href="/daily"],
          body.embedded-console-page a[href="/paper"],
          body.embedded-console-page a[href="/single"],
          body.embedded-console-page a[href="/admin"],
          body.embedded-console-page a[href="/users"],
          body.embedded-console-page a[data-logout] { display: none !important; }
        `;
        frameDocument.head.appendChild(style);
      }
    } catch {
      // Same-origin in this app; ignore if a browser blocks iframe document access.
    }
  }

  return (
    <section className="legacy-page" aria-label={title}>
      <div className="legacy-header">
        <div className="legacy-copy">
          <p className="page-eyebrow">{eyebrow}</p>
          <h1>{title}</h1>
          <p>{description}</p>
        </div>
        <div className="legacy-actions">
          <a className="secondary-link" href={frameSrc} target="_blank" rel="noreferrer">
            <ExternalLink size={14} />
            {"\u6253\u5f00\u65e7\u9875"}
          </a>
          <a className="secondary-link" href={frameSrc} target={frameName}>
            <RefreshCw size={14} />
            {"\u5237\u65b0"}
          </a>
        </div>
      </div>

      <div className="legacy-frame-wrap">
        <iframe className="legacy-frame" name={frameName} src={frameSrc} title={`${title} legacy page`} onLoad={handleFrameLoad} />
      </div>
    </section>
  );
}
