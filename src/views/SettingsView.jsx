import React, { useState, useEffect } from "react";
import { api } from "../utils/api";
import { s } from "../styles/theme";

function Section({ title, children }) {
  return (
    <div style={{ ...s.card, marginBottom: 20 }}>
      <div style={{ ...s.sectionTitle, marginBottom: 18 }}>{title}</div>
      {children}
    </div>
  );
}

export default function SettingsView({ user, onUserUpdate, darkMode, setDarkMode, onLogout }) {
  // Profile
  const [fullName, setFullName] = useState(user?.full_name || "");
  const [savingProfile, setSavingProfile] = useState(false);

  // Password
  const [currentPw, setCurrentPw] = useState("");
  const [newPw, setNewPw] = useState("");
  const [confirmPw, setConfirmPw] = useState("");
  const [savingPw, setSavingPw] = useState(false);

  // Org settings (admin only)
  const [orgName, setOrgName] = useState("");
  const [savingOrg, setSavingOrg] = useState(false);

  // Webhook + IP blocklist (admin only)
  const [webhookUrl, setWebhookUrl] = useState("");
  const [blockedIpsText, setBlockedIpsText] = useState("");
  const [savingSec, setSavingSec] = useState(false);

  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");

  useEffect(() => {
    const loads = [api("/policy")];
    if (user?.org_id) loads.push(api("/org"));
    Promise.all(loads).then(([policy, org]) => {
      const cr = policy?.compliance_rules || {};
      setWebhookUrl(cr.webhook_url || "");
      setBlockedIpsText((cr.blocked_ips || []).join("\n"));
      if (org) setOrgName(org.name);
    }).catch(() => {});
  }, [user]);

  function flash(msg, isErr = false) {
    if (isErr) { setError(msg); setSuccess(""); }
    else { setSuccess(msg); setError(""); }
  }

  async function saveProfile(e) {
    e.preventDefault();
    setSavingProfile(true);
    try {
      const updated = await api("/auth/profile", { method: "PATCH", body: { full_name: fullName } });
      onUserUpdate?.(updated);
      flash("Profile updated.");
    } catch (e) { flash(e.message, true); }
    finally { setSavingProfile(false); }
  }

  async function savePassword(e) {
    e.preventDefault();
    if (newPw !== confirmPw) { flash("New passwords do not match.", true); return; }
    setSavingPw(true);
    try {
      const res = await api("/auth/change-password", {
        method: "POST",
        body: { current_password: currentPw, new_password: newPw },
      });
      flash(res.message || "Password changed.");
      setCurrentPw(""); setNewPw(""); setConfirmPw("");
    } catch (e) { flash(e.message, true); }
    finally { setSavingPw(false); }
  }

  async function saveOrg(e) {
    e.preventDefault();
    setSavingOrg(true);
    try {
      await api("/org", { method: "PATCH", body: { name: orgName } });
      flash("Organisation renamed.");
    } catch (e) { flash(e.message, true); }
    finally { setSavingOrg(false); }
  }

  async function saveSecurity(e) {
    e.preventDefault();
    setSavingSec(true);
    try {
      const blocked_ips = blockedIpsText.split("\n").map(l => l.trim()).filter(Boolean);
      await api("/policy", {
        method: "PATCH",
        body: {
          compliance_rules: {
            webhook_url: webhookUrl.trim() || undefined,
            blocked_ips,
          },
        },
      });
      flash("Security settings saved.");
    } catch (e) { flash(e.message, true); }
    finally { setSavingSec(false); }
  }

  const inputStyle = { ...s.input, marginBottom: 14, maxWidth: 400 };

  return (
    <div>
      <div style={s.heroPanel}>
        <div style={{ ...s.pageTitle, marginBottom: 8 }}>Settings</div>
        <div style={{ color: "#405166", fontSize: 15, lineHeight: 1.6 }}>
          Account, security, appearance, and organisation configuration.
        </div>
      </div>

      {error   && <div style={s.alert("error")}>{error}</div>}
      {success && <div style={s.alert("success")}>{success}</div>}

      {/* Profile */}
      <Section title="Profile">
        <div style={{ fontSize: 13, color: "#8a9bb0", marginBottom: 14 }}>
          Email: <strong style={{ color: "#405166" }}>{user?.email}</strong>
        </div>
        <form onSubmit={saveProfile}>
          <label style={s.label}>Display Name</label>
          <input style={inputStyle} value={fullName}
            onChange={e => setFullName(e.target.value)} required minLength={1} maxLength={120} />
          <button style={s.btn("primary")} type="submit" disabled={savingProfile}>
            {savingProfile ? "Saving..." : "Save Profile"}
          </button>
        </form>
      </Section>

      {/* Password */}
      <Section title="Change Password">
        <form onSubmit={savePassword}>
          <label style={s.label}>Current Password</label>
          <input style={inputStyle} type="password" value={currentPw}
            onChange={e => setCurrentPw(e.target.value)} required />
          <label style={s.label}>New Password</label>
          <input style={inputStyle} type="password" value={newPw}
            onChange={e => setNewPw(e.target.value)} required minLength={8} />
          <label style={s.label}>Confirm New Password</label>
          <input style={inputStyle} type="password" value={confirmPw}
            onChange={e => setConfirmPw(e.target.value)} required minLength={8} />
          <button style={s.btn("primary")} type="submit" disabled={savingPw}>
            {savingPw ? "Updating..." : "Update Password"}
          </button>
        </form>
      </Section>

      {/* Appearance */}
      <Section title="Appearance">
        <div style={{ display: "flex", alignItems: "center", gap: 16 }}>
          <div>
            <div style={{ fontSize: 13, fontWeight: 700, color: "#405166", marginBottom: 2 }}>Dark Mode</div>
            <div style={{ fontSize: 12, color: "#8a9bb0" }}>Toggle between light and dark theme</div>
          </div>
          <button
            style={{
              ...s.toggle(darkMode), marginLeft: "auto",
              position: "relative", outline: "none",
            }}
            onClick={() => setDarkMode(d => !d)}
            type="button"
          >
            <div style={s.toggleDot(darkMode)} />
          </button>
        </div>
      </Section>

      {/* Org settings — admin only */}
      {user?.is_admin && user?.org_id && (
        <Section title="Organisation">
          <form onSubmit={saveOrg}>
            <label style={s.label}>Organisation Name</label>
            <input style={inputStyle} value={orgName}
              onChange={e => setOrgName(e.target.value)} required minLength={2} maxLength={120} />
            <button style={s.btn("primary")} type="submit" disabled={savingOrg}>
              {savingOrg ? "Saving..." : "Rename Organisation"}
            </button>
          </form>
        </Section>
      )}

      {/* Security — admin only */}
      {user?.is_admin && (
        <Section title="Security">
          <form onSubmit={saveSecurity}>
            <label style={s.label}>Webhook URL</label>
            <div style={{ fontSize: 12, color: "#8a9bb0", marginBottom: 8 }}>
              Receives a POST with JSON when a guardrail blocks a request.
            </div>
            <input
              style={inputStyle}
              type="url"
              placeholder="https://your-server.com/webhook"
              value={webhookUrl}
              onChange={e => setWebhookUrl(e.target.value)}
            />

            <label style={s.label}>IP Blocklist</label>
            <div style={{ fontSize: 12, color: "#8a9bb0", marginBottom: 8 }}>
              One IP per line. Blocked IPs receive HTTP 403.
            </div>
            <textarea
              style={{
                ...s.input, marginBottom: 14, maxWidth: 400,
                height: 110, resize: "vertical",
                fontFamily: "ui-monospace, monospace", fontSize: 12,
              }}
              placeholder={"192.168.1.100\n10.0.0.50"}
              value={blockedIpsText}
              onChange={e => setBlockedIpsText(e.target.value)}
            />

            <button style={s.btn("primary")} type="submit" disabled={savingSec}>
              {savingSec ? "Saving..." : "Save Security Settings"}
            </button>
          </form>
        </Section>
      )}

      {/* Danger zone */}
      <Section title="Account">
        <div style={{ fontSize: 13, color: "#607086", marginBottom: 16, lineHeight: 1.6 }}>
          Signing out will clear your local session. You can sign back in at any time.
        </div>
        <button
          style={{ ...s.btn("danger"), padding: "11px 24px" }}
          onClick={() => {
            if (confirm("Sign out of your account?")) onLogout();
          }}
        >
          Sign out
        </button>
      </Section>
    </div>
  );
}
