import React, { useState, useEffect, useCallback, useRef } from "react";
import { api, getToken, setTokens, clearTokens, getGatewayKey, setGatewayKey, maskGatewayKey, gatewayKeyInputProps, formatApiError } from "../utils/api";
import { s } from "../styles/theme";

const passwordStyles = {
  wrap: { position: "relative", width: "100%" },
  codeInput: {
    fontFamily: "ui-monospace, SFMono-Regular, Menlo, Consolas, monospace",
    fontSize: 13,
  },
  toggle: {
    position: "absolute",
    right: 8,
    top: "50%",
    transform: "translateY(-50%)",
    border: "none",
    background: "transparent",
    color: "#64748b",
    fontSize: 11,
    fontWeight: 700,
    fontFamily: "ui-monospace, SFMono-Regular, Menlo, Consolas, monospace",
    cursor: "pointer",
    padding: "6px 8px",
    borderRadius: 6,
    lineHeight: 1,
  },
};

export default function PasswordInput({ value, onChange, placeholder, autoComplete }) {
  const [visible, setVisible] = useState(false);

  return (
    <div style={passwordStyles.wrap}>
      <input
        style={{ ...s.input, ...passwordStyles.codeInput, paddingRight: 72 }}
        type={visible ? "text" : "password"}
        placeholder={placeholder}
        value={value}
        onChange={onChange}
        autoComplete={autoComplete}
      />
      <button
        type="button"
        className="auth-password-toggle"
        style={passwordStyles.toggle}
        onClick={() => setVisible((v) => !v)}
        aria-label={visible ? "Hide password" : "Show password"}
        title={visible ? "Hide password" : "Show password"}
      >
        {visible ? "hide()" : "show()"}
      </button>
    </div>
  );
}

