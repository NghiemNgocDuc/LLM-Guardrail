import { cloneElement, isValidElement, useCallback, useEffect, useId, useRef, useState } from "react";
import type { ButtonHTMLAttributes, KeyboardEvent, ReactElement, ReactNode } from "react";
import AppIcon from "./AppIcon";
import type { IconName } from "./AppIcon";
import "../styles/ui.css";

export type Tone = "neutral" | "success" | "warning" | "danger" | "info";
export function PageHeader({ eyebrow, title, description, actions }: { eyebrow?: string; title: string; description?: ReactNode; actions?: ReactNode }) {
  return <header className="ui-page-header"><div>{eyebrow && <p className="ui-eyebrow">{eyebrow}</p>}<h1>{title}</h1>{description && <div className="ui-page-description">{description}</div>}</div>{actions && <div className="ui-page-actions">{actions}</div>}</header>;
}
export function Panel({ title, description, actions, children, className = "" }: { title?: string; description?: ReactNode; actions?: ReactNode; children: ReactNode; className?: string }) {
  const id = useId();
  return <section className={"ui-panel " + className} aria-labelledby={title ? id : undefined}>{(title || description || actions) && <div className="ui-panel-header"><div>{title && <h2 id={id}>{title}</h2>}{description && <div className="ui-panel-description">{description}</div>}</div>{actions && <div className="ui-panel-actions">{actions}</div>}</div>}<div className="ui-panel-body">{children}</div></section>;
}
export function Button({ variant = "secondary", loading = false, icon, children, className = "", disabled, type = "button", ...props }: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: "primary" | "secondary" | "ghost" | "danger"; loading?: boolean; icon?: IconName }) {
  return <button {...props} type={type} disabled={disabled || loading} aria-busy={loading || undefined} className={"ui-button ui-button-" + variant + " " + className}>{loading ? <span className="workspace-spinner" aria-hidden="true" /> : icon && <AppIcon name={icon} size={16} />}{children}</button>;
}
export function Badge({ tone = "neutral", children }: { tone?: Tone; children: ReactNode }) { return <span className={"ui-badge ui-tone-" + tone}>{children}</span>; }
export function Field({ label, htmlFor, hint, error, children }: { label: ReactNode; htmlFor?: string; hint?: ReactNode; error?: ReactNode; children: ReactNode }) {
  const generated = useId();
  const child = isValidElement(children) ? children as ReactElement<{ id?: string; "aria-describedby"?: string; "aria-invalid"?: boolean }> : null;
  const canLink = child && typeof child.type === "string" && ["input", "select", "textarea"].includes(child.type);
  const id = htmlFor || (canLink ? child.props.id || generated : undefined);
  const detailId = generated + "-detail";
  const control = canLink ? cloneElement(child, { id, "aria-describedby": [child.props["aria-describedby"], (hint || error) && detailId].filter(Boolean).join(" ") || undefined, "aria-invalid": Boolean(error) || undefined }) : children;
  return <div className="ui-field"><label className="ui-field-label" htmlFor={id}>{label}</label>{control}{(hint || error) && <div id={detailId} className={"ui-field-hint" + (error ? " ui-field-error" : "")}>{error || hint}</div>}</div>;
}
export function EmptyState({ icon = "layers", title, description, action }: { icon?: IconName; title: string; description?: ReactNode; action?: ReactNode }) {
  return <div className="ui-empty"><span className="ui-empty-icon"><AppIcon name={icon} size={23} /></span><h3>{title}</h3>{description && <p>{description}</p>}{action && <div className="ui-empty-action">{action}</div>}</div>;
}
export function Notice({ tone = "info", children }: { tone?: Tone; children: ReactNode }) {
  return <div className={"ui-notice ui-tone-" + tone} role={tone === "danger" ? "alert" : "status"}><AppIcon name={tone === "success" ? "check" : tone === "danger" ? "activity" : "shield"} size={17} /><div>{children}</div></div>;
}
export function LoadingState({ label = "Loading…" }: { label?: string }) {
  return <div className="ui-loading" role="status"><span className="workspace-spinner" aria-hidden="true" /><span>{label}</span></div>;
}
export function TableWrap({ label = "Data table", children }: { label?: string; children: ReactNode }) {
  return <div className="ui-table-wrap" role="region" aria-label={label} tabIndex={0}>{children}</div>;
}
export function trapDialogFocus(event: KeyboardEvent<HTMLDialogElement>) {
  if (event.key !== "Tab") return;
  const controls = Array.from(event.currentTarget.querySelectorAll<HTMLElement>('a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])')).filter(node => node.tabIndex >= 0 && node.getClientRects().length > 0);
  const first = controls[0], last = controls.at(-1);
  if (!first || !last) { event.preventDefault(); return; }
  if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
  else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
}
export function Dialog({ open, onClose, title, description, children, footer, size = "md", dismissible = true }: { open: boolean; onClose: () => void; title: string; description?: ReactNode; children?: ReactNode; footer?: ReactNode; size?: "sm" | "md" | "lg"; dismissible?: boolean }) {
  const ref = useRef<HTMLDialogElement>(null);
  const latestClose = useRef(onClose);
  latestClose.current = onClose;
  const snapshot = useRef({ title, description, children, footer, dismissible });
  if (open) snapshot.current = { title, description, children, footer, dismissible };
  const content = open ? { title, description, children, footer, dismissible } : snapshot.current;
  const id = useId();
  useEffect(() => {
    const dialog = ref.current;
    if (!dialog) return;
    if (open) { dialog.dataset.closing = "false"; if (!dialog.open) dialog.showModal(); return; }
    if (!dialog.open) return;
    dialog.dataset.closing = "true";
    const timer = window.setTimeout(() => dialog.close(), window.matchMedia("(prefers-reduced-motion: reduce)").matches ? 0 : 140);
    return () => window.clearTimeout(timer);
  }, [open]);
  return <dialog ref={ref} className={"ui-dialog ui-dialog-" + size} aria-labelledby={id} aria-describedby={content.description ? id + "-description" : undefined} onKeyDown={trapDialogFocus} onCancel={event => { event.preventDefault(); if (dismissible) latestClose.current(); }} onClick={event => {
    if (event.target !== event.currentTarget || !dismissible) return;
    const bounds = event.currentTarget.getBoundingClientRect();
    if (event.clientX < bounds.left || event.clientX > bounds.right || event.clientY < bounds.top || event.clientY > bounds.bottom) latestClose.current();
  }}>
    <div className="ui-dialog-header"><div><h2 id={id}>{content.title}</h2>{content.description && <div id={id + "-description"} className="ui-panel-description">{content.description}</div>}</div>{content.dismissible && <Button variant="ghost" aria-label="Close dialog" onClick={onClose} className="ui-icon-button" icon="close" />}</div>
    {content.children && <div className="ui-dialog-body">{content.children}</div>}{content.footer && <div className="ui-dialog-footer">{content.footer}</div>}
  </dialog>;
}
type Confirmation = { title: string; description: ReactNode; confirmLabel?: string; danger?: boolean };
export function useConfirmation() {
  const [request, setRequest] = useState<Confirmation | null>(null);
  const resolve = useRef<((value: boolean) => void) | null>(null);
  const finish = useCallback((value: boolean) => { resolve.current?.(value); resolve.current = null; setRequest(null); }, []);
  useEffect(() => () => { resolve.current?.(false); }, []);
  const confirm = useCallback((next: Confirmation) => new Promise<boolean>(done => { resolve.current?.(false); resolve.current = done; setRequest(next); }), []);
  const dialog = <Dialog open={Boolean(request)} onClose={() => finish(false)} title={request?.title || "Confirm action"} description={request?.description} size="sm" footer={<><Button onClick={() => finish(false)}>Cancel</Button><Button variant={request?.danger ? "danger" : "primary"} onClick={() => finish(true)}>{request?.confirmLabel || "Confirm"}</Button></>} />;
  return { confirm, dialog };
}
