import { useState } from "react";
import type { MouseEvent } from "react";
import AppIcon from "./AppIcon";
import { Button, Dialog } from "./ui";
import { PAGE_HELP } from "../content/pageHelp";
import "../styles/help.css";

export default function WorkspaceHelp({ view, pageLabel, onNavigate }: { view: string; pageLabel: string; onNavigate: (view: string) => void }) {
  const [open, setOpen] = useState(false);
  const help = PAGE_HELP[view] || PAGE_HELP.dashboard;

  function follow(event: MouseEvent<HTMLAnchorElement>, nextView: string) {
    if (event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
    event.preventDefault();
    // Close before changing routes so the new page can receive keyboard focus.
    event.currentTarget.closest("dialog")?.close();
    setOpen(false);
    onNavigate(nextView);
  }

  return <>
    <button type="button" className="workspace-help-trigger" aria-label="Help with this page" aria-haspopup="dialog" onClick={() => setOpen(true)} title="Help with this page">
      <AppIcon name="help" size={21} /><span className="workspace-help-label">Help</span>
    </button>
    <Dialog open={open} onClose={() => setOpen(false)} title={"Help with " + pageLabel}
      description={<p className="workspace-help-description">{help.description}</p>}
      footer={<><a className="ui-button" href="?view=about" onClick={event => follow(event, "about")}>Open full guide<AppIcon name="arrow" size={15} /></a><a className="ui-button ui-button-primary" href={"?view=" + help.action.view} onClick={event => follow(event, help.action.view)}>{help.action.label}<AppIcon name="arrow" size={15} /></a></>}>
      <div className="workspace-help-content">
        <h3>{help.title}</h3>
        <ol className="workspace-help-steps">{help.steps.map(step => <li key={step}>{step}</li>)}</ol>
        <p className="workspace-help-tip"><AppIcon name="help" size={18} /><span>{help.tip}</span></p>
      </div>
    </Dialog>
  </>;
}

export function ProjectIntroHelp() {
  const [open, setOpen] = useState(false);
  return <>
    <button type="button" className="workspace-help-trigger project-intro-trigger" aria-label="What is LLM Guardrail?" aria-haspopup="dialog" onClick={() => setOpen(true)}>
      <AppIcon name="help" size={21} /><span>What is this?</span>
    </button>
    <Dialog open={open} onClose={() => setOpen(false)} title="Meet LLM Guardrail"
      description={<p className="workspace-help-description">A place to try AI requests, check agent instructions, and understand why a safety check allowed or stopped something.</p>}
      footer={<Button variant="primary" onClick={() => setOpen(false)}>Got it</Button>}>
      <div className="workspace-help-content">
        <h3>Think of it as a checkpoint for your AI.</h3>
        <ol className="workspace-help-steps">
          <li>You write a prompt or paste a file of instructions for an AI agent.</li>
          <li>The app checks it for risks, such as leaked credentials or attempts to bypass your rules.</li>
          <li>You review the result. Allowed model requests continue to your configured AI provider.</li>
        </ol>
        <p className="workspace-help-tip"><AppIcon name="sparkles" size={18} /><span>After signing in, open Help &amp; getting started for a simple walkthrough. Use made-up information while exploring the public demo.</span></p>
      </div>
    </Dialog>
  </>;
}
