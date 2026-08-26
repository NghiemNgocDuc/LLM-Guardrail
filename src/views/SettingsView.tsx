import React, { useState, useEffect } from "react";
import { api } from "../utils/api";
import { s } from "../styles/theme";
import type { components } from "../api-types";
import type { CSSProperties } from "react";

type UserOut = components["schemas"]["UserOut"];
type PolicyOut = components["schemas"]["PolicyOut"];
type OrgOut = components["schemas"]["OrgOut"];

interface AuthMessageResponse { message: string }

const field: CSSProperties = {
  display: "block",
  marginBottom: 18,
};
const label: CSSProperties = {
  display: "block",
  fontSize: 12,
  fontWeight: 700,
  color: "#607086",
  marginBottom: 6,
  letterSpacing: "0.02em",
};
const hint: CSSProperties = {
  display: "block",
  fontSize: 11,
  color: "#9aabba",
  marginTop: 4,
};
const input: CSSProperties = {
  width: "100%",
  maxWidth: 440,
  background: "#fff",
  border: "1px solid #ccd9e6",
  borderRadius: 8,
  padding: "11px 13px",
  fontSize: 14,
  color: "#102033",
  fontFamily: "inherit",
  outline: "none",
  boxSizing: "border-box",
  display: "block",
};

function Card({ title, subtitle, children }: {
  title: string;
  subtitle?: string;
  children: React.ReactNode;
}) {
  return (
    <div style={{
      background: "rgba(255,255,255,0.92)",
      border: "1px solid rgba(15,118,110,0.13)",
      borderRadius: 14,
      padding: "24px 28px",
      marginBottom: 18,
      boxShadow: "0 4px 24px rgba(15,118,110,0.06)",
    }}>
      <div style={{ marginBottom: 20, paddingBottom: 14, borderBottom: "1px solid #edf2f7" }}>
        <div style={{ fontSize: 14, fontWeight: 800, color: "#102033" }}>{title}</div>
        {subtitle && <div style={{ fontSize: 12, color: "#8a9bb0", marginTop: 3 }}>{subtitle}</div>}
      </div>
      {children}
    </div>
  );
}

function SaveBtn({ saving, label: lbl }: { saving: boolean; label?: string }) {
  return (
    <button style={s.btn("primary")} type="submit" disabled={saving}>
      {saving ? "Saving…" : lbl || "Save"}
    </button>
  );
}

export default function SettingsView({ user, onUserUpdate, darkMode, setDarkMode, onLogout }: {
  user: UserOut | null;
  onUserUpdate?: (u: UserOut) => void;
  darkMode: boolean;
  setDarkMode: React.Dispatch<React.SetStateAction<boolean>>;
  onLogout: () => void;
}) {
  const [fullName, setFullName] = useState(user?.full_name || "");
  const [savingProfile, setSavingProfile] = useState(false);

  const [currentPw, setCurrentPw] = useState("");
  const [newPw, setNewPw]         = useState("");
  const [confirmPw, setConfirmPw] = useState("");
  const [savingPw, setSavingPw]   = useState(false);

  const [orgName, setOrgName]     = useState("");
  const [savingOrg, setSavingOrg] = useState(false);

  const [webhookUrl, setWebhookUrl]         = useState("");
  const [blockedIpsText, setBlockedIpsText] = useState("");
  const [savingSec, setSavingSec]           = useState(false);

  const [error, setError]     = useState("");
  const [success, setSuccess] = useState("");

  useEffect(() => {
    const loads: Promise<unknown>[] = [api<PolicyOut>("/policy")];
    if (user?.org_id) loads.push(api<OrgOut>("/org"));
    Promise.all(loads).then(([policy, org]) => {
      const cr = (policy as PolicyOut)?.compliance_rules || {};
      const crMap = cr as Record<string, unknown>;
      setWebhookUrl(typeof crMap.webhook_url === "string" ? crMap.webhook_url : "");
      setBlockedIpsText(Array.isArray(crMap.blocked_ips) ? (crMap.blocked_ips as string[]).join("\n") : "");
      if (org) setOrgName((org as OrgOut).name);
    }).catch(() => {});
  }, [user]);

  function flash(msg: string, isErr = false) {
    if (isErr) { setError(msg); setSuccess(""); }
    else        { setSuccess(msg); setError(""); }
    setTimeout(() => { setError(""); setSuccess(""); }, 4000);
  }

  async function saveProfile(e: React.FormEvent) {
    e.preventDefault(); setSavingProfile(true);
    try {
      const updated = await api<UserOut>("/auth/profile", { method: "PATCH", body: { full_name: fullName } });
      onUserUpdate?.(updated);
      flash("Profile updated.");
    } catch (err) { flash(err instanceof Error ? err.message : String(err), true); }
    finally { setSavingProfile(false); }
  }

  async function savePassword(e: React.FormEvent) {
    e.preventDefault();
    if (newPw !== confirmPw) { flash("New passwords do not match.", true); return; }
    setSavingPw(true);
    try {
      const res = await api<AuthMessageResponse>("/auth/change-password", {
        method: "POST",
        body: { current_password: currentPw, new_password: newPw },
      });
      flash(res.message || "Password changed.");
      setCurrentPw(""); setNewPw(""); setConfirmPw("");
    } catch (err) { flash(err instanceof Error ? err.message : String(err), true); }
    finally { setSavingPw(false); }
  }

  async function saveOrg(e: React.FormEvent) {
    e.preventDefault(); setSavingOrg(true);
    try {
      await api<OrgOut>("/org", { method: "PATCH", body: { name: orgName } });
      flash("Organisation renamed.");
    } catch (err) { flash(err instanceof Error ? err.message : String(err), true); }
    finally { setSavingOrg(false); }
  }

  async function saveSecurity(e: React.FormEvent) {
    e.preventDefault(); setSavingSec(true);
    try {
      const blocked_ips = blockedIpsText.split("\n").map(l => l.trim()).filter(Boolean);
      await api<PolicyOut>("/policy", {
        method: "PATCH",
        body: { compliance_rules: { webhook_url: webhookUrl.trim() || undefined, blocked_ips } },
      });
      flash("Security settings saved.");
    } catch (err) { flash(err instanceof Error ? err.message : String(err), true); }
    finally { setSavingSec(false); }
  }

  return (
    <div>
      {/* Page header */}
      <div style={s.heroPanel}>
        <div style={{ ...s.pageTitle, marginBottom: 6 }}>Settings</div>
        <div style={{ color: "#607086", fontSize: 14 }}>
          Signed in as <strong>{user?.email}</strong>
          {user?.is_admin && (
            <span style={{ ...s.badge("rate_limited"), marginLeft: 10 }}>Admin</span>
          )}
        </div>
      </div>

      {/* Inline feedback */}
      {error   && <div style={{ ...s.alert("error"),   marginBottom: 16 }}>{error}</div>}
      {success && <div style={{ ...s.alert("success"), marginBottom: 16 }}>{success}</div>}

      {/* -- Profile -- */}
      <Card title="Profile" subtitle="Your public display name shown to teammates">
        <form onSubmit={saveProfile}>
          <div style={field}>
            <label style={label}>Display Name</label>
            <input style={input} value={fullName}
              onChange={e => setFullName(e.target.value)}
              required minLength={1} maxLength={120}
              placeholder="Your full name" />
          </div>
          <div style={field}>
            <label style={label}>Email</label>
            <input style={{ ...input, background: "#f8fbff", color: "#8a9bb0", cursor: "not-allowed" }}
              value={user?.email || ""} readOnly />
            <span style={hint}>Email cannot be changed from the dashboard.</span>
          </div>
          <SaveBtn saving={savingProfile} label="Save Profile" />
        </form>
      </Card>

      {/* -- Password -- */}
      <Card title="Change Password" subtitle="Use a strong password of at least 8 characters">
        <form onSubmit={savePassword}>
          <div style={field}>
            <label style={label}>Current Password</label>
            <input style={input} type="password" value={currentPw}
              onChange={e => setCurrentPw(e.target.value)} required
              placeholder="Enter current password" />
          </div>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 14, marginBottom: 18 }}>
            <div>
              <label style={label}>New Password</label>
              <input style={{ ...input, maxWidth: "100%" }} type="password" value={newPw}
                onChange={e => setNewPw(e.target.value)} required minLength={8}
                placeholder="At least 8 characters" />
            </div>
            <div>
              <label style={label}>Confirm New Password</label>
              <input style={{ ...input, maxWidth: "100%" }} type="password" value={confirmPw}
                onChange={e => setConfirmPw(e.target.value)} required minLength={8}
                placeholder="Repeat new password" />
            </div>
          </div>
          <SaveBtn saving={savingPw} label="Update Password" />
        </form>
      </Card>

      {/* -- Appearance -- */}
      <Card title="Appearance" subtitle="Customise how the dashboard looks">
        <div style={{ display: "flex", alignItems: "center", gap: 16, padding: "4px 0" }}>
          <div style={{ flex: 1 }}>
            <div style={{ fontSize: 14, fontWeight: 700, color: "#102033", marginBottom: 2 }}>Dark Mode</div>
            <div style={{ fontSize: 12, color: "#8a9bb0" }}>
              {darkMode ? "Currently using dark theme" : "Currently using light theme"}
            </div>
          </div>
          <button
            type="button"
            style={{ ...s.toggle(darkMode), flexShrink: 0, position: "relative" }}
            onClick={() => setDarkMode(d => !d)}
          >
            <div style={s.toggleDot(darkMode)} />
          </button>
        </div>
      </Card>

      {/* -- Organisation (admin only) -- */}
      {user?.is_admin && user?.org_id && (
        <Card title="Organisation" subtitle="Rename your organisation — the slug will update automatically">
          <form onSubmit={saveOrg}>
            <div style={field}>
              <label style={label}>Organisation Name</label>
              <input style={input} value={orgName}
                onChange={e => setOrgName(e.target.value)}
                required minLength={2} maxLength={120}
                placeholder="Acme Corp" />
            </div>
            <SaveBtn saving={savingOrg} label="Rename Organisation" />
          </form>
        </Card>
      )}

      {/* -- Security (admin only) -- */}
      {user?.is_admin && (
        <Card title="Security" subtitle="Guardrail webhook notifications and IP-level access control">
          <form onSubmit={saveSecurity}>
            <div style={field}>
              <label style={label}>Webhook URL</label>
              <input style={input} type="url" value={webhookUrl}
                onChange={e => setWebhookUrl(e.target.value)}
                placeholder="https://your-server.com/webhook" />
              <span style={hint}>
                Receives a POST request with JSON payload whenever a guardrail blocks a request.
              </span>
            </div>
            <div style={field}>
              <label style={label}>IP Blocklist</label>
              <textarea
                style={{
                  ...input, maxWidth: 440, height: 110,
                  resize: "vertical", fontFamily: "ui-monospace, monospace", fontSize: 12,
                  lineHeight: 1.6,
                }}
                placeholder={"192.168.1.100\n10.0.0.50"}
                value={blockedIpsText}
                onChange={e => setBlockedIpsText(e.target.value)}
              />
              <span style={hint}>One IP address per line. Requests from these IPs receive HTTP 403.</span>
            </div>
            <SaveBtn saving={savingSec} label="Save Security Settings" />
          </form>
        </Card>
      )}

      {/* -- Account / Sign out -- */}
      <Card title="Account" subtitle="Manage your session">
        <div style={{
          display: "flex", alignItems: "center", justifyContent: "space-between",
          flexWrap: "wrap", gap: 12,
        }}>
          <div style={{ fontSize: 13, color: "#607086", lineHeight: 1.6 }}>
            Signing out clears your local session token.<br />
            You can sign back in at any time.
          </div>
          <button
            style={{ ...s.btn("danger"), padding: "11px 28px", fontSize: 13 }}
            onClick={() => { if (confirm("Sign out of your account?")) onLogout(); }}
          >
            Sign out
          </button>
        </div>
      </Card>
    </div>
  );
}
