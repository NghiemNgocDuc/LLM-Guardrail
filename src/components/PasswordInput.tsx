import React, { useState } from "react";
import AppIcon from "./AppIcon";
import { s } from "../styles/theme";
import type { CSSProperties, InputHTMLAttributes } from "react";

const passwordStyles: Record<string, CSSProperties> = {
  wrap: { position: "relative", width: "100%" },
  codeInput: {
    fontFamily: "inherit",
    fontSize: 16,
  },
  toggle: {
    position: "absolute",
    right: 3,
    top: "50%",
    transform: "translateY(-50%)",
    border: "none",
    background: "transparent",
    color: "var(--gr-muted)",
    fontSize: 11,
    fontWeight: 700,
    fontFamily: "ui-monospace, SFMono-Regular, Menlo, Consolas, monospace",
    cursor: "pointer",
    padding: 10,
    width: 44,
    height: 44,
    display: "grid",
    placeItems: "center",
    borderRadius: 6,
    lineHeight: 1,
  },
};

export default function PasswordInput({ value, onChange, style, ...inputProps }: {
  value: string;
  onChange: (e: React.ChangeEvent<HTMLInputElement>) => void;
} & Omit<InputHTMLAttributes<HTMLInputElement>, "type" | "value" | "onChange">) {
  const [visible, setVisible] = useState(false);

  return (
    <div style={passwordStyles.wrap}>
      <input
        {...inputProps}
        style={{ ...s.input, ...passwordStyles.codeInput, ...style, paddingRight: 50 }}
        type={visible ? "text" : "password"}
        value={value}
        onChange={onChange}
      />
      <button
        type="button"
        className="auth-password-toggle"
        style={passwordStyles.toggle}
        onClick={() => setVisible((v) => !v)}
        aria-label={visible ? "Hide password" : "Show password"}
        aria-pressed={visible}
        title={visible ? "Hide password" : "Show password"}
      >
        <AppIcon name={visible ? "eye-off" : "eye"} size={18} />
      </button>
    </div>
  );
}

