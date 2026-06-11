import React, { useState, useEffect, useCallback, useRef } from "react";
import { api, getToken, setTokens, clearTokens, getGatewayKey, setGatewayKey, maskGatewayKey, gatewayKeyInputProps, formatApiError } from "../utils/api";
import { s } from "../styles/theme";
export default function AuthFlowBackground() {
  return (
    <div className="auth-hero-bg" aria-hidden>
      <div className="auth-hero-noise" />
      <div className="auth-hero-orb auth-hero-orb-1" />
      <div className="auth-hero-orb auth-hero-orb-2" />
      <div className="auth-hero-orb auth-hero-orb-3" />
      <div className="auth-hero-orb auth-hero-orb-4" />
      <svg className="auth-hero-svg" viewBox="0 0 1440 900" preserveAspectRatio="xMidYMid slice">
        <path className="auth-hero-path auth-hero-path-1" d="M-100 600 C 200 100, 500 700, 800 350 S 1300 150, 1540 450" />
        <path className="auth-hero-path auth-hero-path-2" d="M-80 200 C 300 500, 600 50, 900 300 S 1200 650, 1540 280" />
        <path className="auth-hero-path auth-hero-path-3" d="M100 800 C 400 550, 700 820, 1000 580 S 1350 350, 1540 620" />
      </svg>
      <div className="auth-hero-grid" />
      <div className="auth-hero-glow" />
    </div>
  );
}

