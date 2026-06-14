import React, { useState, useEffect } from "react";
import { api } from "../utils/api";
import { s } from "../styles/theme";

export default function ProfileView({ user, onUserUpdate }) {
  const [fullName, setFullName] = useState(user?.full_name || "");
  const [orgName, setOrgName] = useState("");
  const [webhookUrl, setWebhookUrl] = useState("");
  const [blockedIpsText, setBlockedIpsText] = useState("");
  const [saving, setSaving] = useState(false);
  const [savingOrg, setSavingOrg] = useState(false);
  const [savingPolicy, setSavingPolicy] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");

  useEffect(() => {
    Promise.all([
      user?.org_id ? api("/org") : Promise.resolve(null),
      api("/policy"),
    ]).then(([org, policy]) => {
      if (org) setOrgName(org.name);
      const cr = policy?.compliance_rules || {};
      setWebhookUrl(cr.webhook_url || "");
      setBlockedIpsText((cr.blocked_ips || []).join("\n"));
    }).catch(() => {});
  }, [user]);

  async function saveProfile(e) {
    e.preventDefault();
    setSaving(true); setError(""); setSuccess("");
    try {
      const updated = await api("/auth/profile", { method: "PATCH", body: { full_name: fullName } });
      onUserUpdate && onUserUpdate(updated);
      setSuccess("Profile updated.");
    } catch (e) { setError(e.message); }
    finally { setSaving(false); }
  }

  async function saveOrg(e) {
    e.preventDefault();
    setSavingOrg(true); setError(""); setSuccess("");
    try {
      await api("/org", { method: "PATCH", body: { name: orgName } });
      setSuccess("Organisation name updated.");
    } catch (e) { setError(e.message); }
    finally { setSavingOrg(false); }
  }

  async function savePolicy(e) {
    e.preventDefault();
    setSavingPolicy(true); setError(""); setSuccess("");
    try {
      const blocked_ips = blockedIpsText
        .split("\n")
        .map(l => l.trim())
        .filter(Boolean);
      await api("/policy", {
        method: "PATCH",
        body: {
          compliance_rules: {
            webhook_url: webhookUrl.trim() || undefined,
            blocked_ips,
          },
        },
      });
      setSuccess("Security settings saved.");
    } catch (e) { setError(e.message); }
    finally { setSavingPolicy(false); }
  }

  return (
    <div>
      <div style={s.heroPanel}>
        <div style={{ ...s.pageTitle, marginBottom: 8 }}>Profile & Settings</div>
        <div style={{ color: "#405166", fontSize: 15, lineHeight: 1.6 }}>
          Manage your personal profile, organisation settings, and security configuration.
        </div>
      </div>

      {error && <div style={s.alert("error")}>{error}</div>}
      {success && <div style={s.alert("success")}>{success}</div>}

      {/* Personal */}
      <div style={{ ...s.card, marginBottom: 20 }}>
        <div style={s.sectionTitle}>Personal Profile</div>
        <div style={{ fontSize: 12, color: "#8a9bb0", marginBottom: 16 }}>
          Email: <strong>{user?.email}</strong>
        </div>
        <form onSubmit={saveProfile}>
          <label style={s.label}>Display Name</label>
          <input
            style={{ ...s.input, marginBottom: 16, maxWidth: 360 }}
            value={fullName}
            onChange={e => setFullName(e.target.value)}
            required minLength={1} maxLength={120}
          />
          <div>
            <button style={s.btn("primary")} type="submit" disabled={saving}>
              {saving ? "Saving..." : "Save Profile"}
            </button>
          </div>
        </form>
      </div>

      {/* Organisation */}
      {user?.is_admin && user?.org_id && (
        <div style={{ ...s.card, marginBottom: 20 }}>
          <div style={s.sectionTitle}>Organisation Settings</div>
          <form onSubmit={saveOrg}>
            <label style={s.label}>Organisation Name</label>
            <input
              style={{ ...s.input, marginBottom: 16, maxWidth: 360 }}
              value={orgName}
              onChange={e => setOrgName(e.target.value)}
              required minLength={2} maxLength={120}
            />
            <div>
              <button style={s.btn("primary")} type="submit" disabled={savingOrg}>
                {savingOrg ? "Saving..." : "Rename Organisation"}
              </button>
            </div>
          </form>
        </div>
      )}

      {/* Security */}
      {user?.is_admin && (
        <div style={s.card}>
          <div style={s.sectionTitle}>Security Settings</div>
          <form onSubmit={savePolicy}>
            <label style={s.label}>Webhook URL</label>
            <div style={{ fontSize: 12, color: "#8a9bb0", marginBottom: 6 }}>
              Receives a POST request with JSON payload whenever a guardrail blocks a request.
            </div>
            <input
              style={{ ...s.input, marginBottom: 20, maxWidth: 480 }}
              type="url"
              placeholder="https://your-server.com/webhook"
              value={webhookUrl}
              onChange={e => setWebhookUrl(e.target.value)}
            />

            <label style={s.label}>IP Blocklist</label>
            <div style={{ fontSize: 12, color: "#8a9bb0", marginBottom: 6 }}>
              One IP address per line. Requests from these addresses will be rejected with HTTP 403.
            </div>
            <textarea
              style={{
                ...s.input, marginBottom: 20, maxWidth: 480,
                height: 120, resize: "vertical", fontFamily: "ui-monospace, monospace", fontSize: 12,
              }}
              placeholder={"192.168.1.100\n10.0.0.50"}
              value={blockedIpsText}
              onChange={e => setBlockedIpsText(e.target.value)}
            />

            <div>
              <button style={s.btn("primary")} type="submit" disabled={savingPolicy}>
                {savingPolicy ? "Saving..." : "Save Security Settings"}
              </button>
            </div>
          </form>
        </div>
      )}
    </div>
  );
}
