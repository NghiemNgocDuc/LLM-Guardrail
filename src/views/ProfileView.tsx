import type { components } from "../api-types";
import { Badge, Button, LoadingState, Notice, PageHeader, Panel } from "../components/ui";
import { OrganizationForm, ProfileForm, SecurityForm, useWorkspaceSettings } from "./SettingsView";
import "../styles/accounts.css";

type User = components["schemas"]["UserOut"];
export default function ProfileView({ user, onUserUpdate }: { user: User | null; onUserUpdate?: (user: User) => void }) {
  const workspace = useWorkspaceSettings(user);
  const initials = (user?.full_name || user?.email || "U").trim().split(/\s+/).slice(0, 2).map((part) => part[0]).join("").toUpperCase();
  return <div className="accounts-page">
    <PageHeader eyebrow="Your account" title="A little more about you." description="Keep your identity and your workspace details up to date." actions={<a className="accounts-link" href="?view=settings">All settings →</a>} />
    <div className="accounts-profile-layout"><Panel className="accounts-profile-card"><div className="accounts-profile-avatar" aria-hidden="true">{initials}</div><h2>{user?.full_name || "Your profile"}</h2><p className="accounts-profile-email">{user?.email}</p><div className="accounts-profile-badges"><Badge tone={user?.is_admin ? "info" : "neutral"}>{user?.is_admin ? "Administrator" : "Member"}</Badge><Badge tone={user?.email_verified ? "success" : "warning"}>{user?.email_verified ? "Email verified" : "Email unverified"}</Badge></div>{user?.created_at && <p className="accounts-copy">Joined <time dateTime={user.created_at}>{new Date(user.created_at).toLocaleDateString(undefined, { month: "long", year: "numeric" })}</time></p>}</Panel>
      <div className="accounts-stack"><ProfileForm user={user} onUserUpdate={onUserUpdate} />{user?.is_admin && user.org_id && <>{workspace.loading && !workspace.policy && <LoadingState label="Loading workspace settings" />}{workspace.error && <Notice tone="danger">{workspace.error}<Button variant="ghost" onClick={() => void workspace.reload()}>Try again</Button></Notice>}{workspace.org && <OrganizationForm org={workspace.org} onSaved={workspace.setOrg} />}{workspace.policy && <SecurityForm policy={workspace.policy} onSaved={workspace.setPolicy} />}</>}</div>
    </div>
  </div>;
}
