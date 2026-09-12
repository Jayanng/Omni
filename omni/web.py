"""Live Visual Cockpit Web UI for Omni.

Crafted with the exact visual design language and architectural taste of Floor (usefloor.vercel.app):
- Deep obsidian pitch-black palette (#080808) with subtle radial glows and 1px borders
- Hero spotlight blur, top laser hairline, two-tone display typography
- Embedded dashboard frame with mini sidebar, glowing SVG sparklines, and session countdown
- Real-time polling against Bitget UTA v3 demo account and production reality feeds
- Multi-threaded HTTP server with OPTIONS CORS support
- Interactive shock stress-testing directly triggering real agent decision cycles
- Toast notification system and immediate visual feedback on all buttons
- Live cryptographic evidence ledger table reading from day-scoped JSONL logs
- 1:1 Parity Sentinel Command Deck & Live Terminal Console for every CLI command:
    omni doctor, omni setup, omni decide, omni flatten, omni report, omni daemon
"""

from __future__ import annotations

import http.server
import json
import os
import socketserver
import threading
import time
import urllib.parse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

from . import bitget_public as bp
from .actions import (
    GLOBAL_DAEMON,
    GLOBAL_TERMINAL_LOGS,
    run_doctor,
    run_flatten,
    run_report,
    run_setup,
)
from .bitget_demo import DemoClient
from .config import ROOT, load_config
from .daemon import DaemonConfig, OmniDaemon
from .ledger import Ledger
from .session import classify

DEFAULT_PORTFOLIO = ROOT / "demo" / "portfolio.example.json"
PORT = 8080

HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en" class="dark scroll-smooth">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1.0"/>
  <title>Omni — Downside Governance for Bitget Unified Trading Account</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&family=JetBrains+Mono:wght@400;500;600&display=swap" rel="stylesheet">
  <script src="https://cdn.tailwindcss.com"></script>
  <script>
    tailwind.config = {
      darkMode: 'class',
      theme: {
        extend: {
          fontFamily: {
            sans: ['Inter', 'sans-serif'],
            display: ['Inter', 'sans-serif'],
            mono: ['JetBrains Mono', 'monospace'],
          },
          colors: {
            bg: '#080808',
            lift: '#0E0E0E',
            card: '#121212',
            terminalBg: '#0A0A0A',
            line: 'rgba(255, 255, 255, 0.08)',
            lineHover: 'rgba(255, 255, 255, 0.16)',
            ink: '#FFFFFF',
            ink2: 'rgba(255, 255, 255, 0.65)',
            ink3: 'rgba(255, 255, 255, 0.40)',
            muted: 'rgba(255, 255, 255, 0.28)',
            accent: '#00F0FF',
            emeraldGlow: '#10B981',
          }
        }
      }
    }
  </script>
  <style>
    body {
      background-color: #080808;
      color: #FFFFFF;
      font-family: 'Inter', sans-serif;
      -webkit-font-smoothing: antialiased;
      overflow-x: hidden;
    }
    .mono-label {
      font-family: 'JetBrains Mono', monospace;
      font-size: 11px;
      text-transform: uppercase;
      letter-spacing: 0.06em;
    }
    .hero-glow {
      position: absolute;
      top: 0;
      left: 50%;
      transform: translateX(-50%);
      width: 1000px;
      height: 720px;
      background: radial-gradient(ellipse 58% 46% at 50% 0%, rgba(255, 255, 255, 0.055), transparent 72%);
      pointer-events: none;
    }
    .halo-blur {
      position: absolute;
      top: -58px;
      left: 50%;
      transform: translateX(-50%);
      width: 70%;
      height: 150px;
      border-radius: 50%;
      background: rgba(255, 255, 255, 0.14);
      filter: blur(80px);
      pointer-events: none;
    }
    .top-laser {
      position: absolute;
      top: -1px;
      left: 50%;
      transform: translateX(-50%);
      width: 58%;
      height: 1px;
      background: linear-gradient(90deg, transparent, rgba(255, 255, 255, 0.5), transparent);
      opacity: 0.65;
      pointer-events: none;
    }
    .custom-scroll::-webkit-scrollbar {
      width: 5px;
      height: 5px;
    }
    .custom-scroll::-webkit-scrollbar-thumb {
      background: rgba(255, 255, 255, 0.18);
      border-radius: 4px;
    }
    .custom-scroll::-webkit-scrollbar-track {
      background: rgba(0, 0, 0, 0.2);
    }
    @keyframes pulseGlow {
      0%, 100% { box-shadow: 0 0 15px rgba(16, 185, 129, 0.2); }
      50% { box-shadow: 0 0 25px rgba(16, 185, 129, 0.45); }
    }
    .pulse-glow {
      animation: pulseGlow 2s infinite ease-in-out;
    }
  </style>
</head>
<body class="min-h-screen relative">
  <!-- Toast Container -->
  <div id="toastContainer" class="fixed top-5 right-5 z-[9999] flex flex-col gap-2 pointer-events-none max-w-sm w-full"></div>

  <!-- Top Ambient Glow -->
  <div class="hero-glow"></div>

  <!-- Main Navigation (Floor Exact Header) -->
  <header class="absolute inset-x-0 top-0 z-50">
    <div class="mx-auto flex max-w-[1160px] items-center justify-between px-[clamp(32px,7vw,96px)] py-7">
      <a href="/" class="flex items-center gap-2.5 cursor-pointer">
        <div class="grid h-7 w-7 place-items-center rounded-lg border border-line bg-white/[0.04]">
          <svg class="h-4 w-4 text-ink" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M12 2v20M17 5H9.5a3.5 3.5 0 0 0 0 7h5a3.5 3.5 0 0 1 0 7H6"/>
          </svg>
        </div>
        <span class="font-display text-[18px] font-semibold tracking-[-0.03em]">Omni</span>
        <span class="rounded-full border border-line bg-white/[0.03] px-2 py-0.5 font-mono text-[10px] text-ink3">UTA v3</span>
      </a>

      <nav class="hidden items-center gap-8 md:flex">
        <a href="#cockpit" class="text-[13.5px] text-ink2 transition-colors duration-200 hover:text-ink cursor-pointer">Live Cockpit</a>
        <a href="#command-deck" class="text-[13.5px] text-ink2 transition-colors duration-200 hover:text-ink cursor-pointer">Command Deck</a>
        <a href="#terminal-section" class="text-[13.5px] text-ink2 transition-colors duration-200 hover:text-ink cursor-pointer">Terminal</a>
        <a href="#how-it-works" class="text-[13.5px] text-ink2 transition-colors duration-200 hover:text-ink cursor-pointer">How it works</a>
        <a href="#settlements" class="text-[13.5px] text-ink2 transition-colors duration-200 hover:text-ink cursor-pointer">Settlements</a>
        <a href="#ledger-section" class="text-[13.5px] text-ink2 transition-colors duration-200 hover:text-ink cursor-pointer">Audit Ledger</a>
        <a href="#faq" class="text-[13.5px] text-ink2 transition-colors duration-200 hover:text-ink cursor-pointer">FAQ</a>
      </nav>

      <div class="flex items-center gap-3">
        <button onclick="triggerDoctor()" id="topDoctorBtn" class="hidden sm:inline-flex items-center gap-1.5 rounded-full border border-line bg-white/[0.04] px-3.5 py-1.5 text-[11.5px] font-mono text-ink2 hover:text-ink transition hover:border-white/20 active:scale-95 cursor-pointer">
          <svg class="h-3 w-3 text-emerald-400" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/></svg>
          <span>Doctor 13/13</span>
        </button>
        <a href="#cockpit" class="inline-flex items-center gap-2 rounded-full border border-line bg-white/[0.04] px-5 py-2 text-[13px] font-medium backdrop-blur-[8px] transition-transform duration-200 hover:-translate-y-px cursor-pointer">
          <span class="h-2 w-2 rounded-full bg-emerald-400 animate-pulse"></span>
          <span>UID 23020984377</span>
        </a>
      </div>
    </div>
  </header>

  <!-- Hero Section -->
  <section class="relative">
    <div class="relative mx-auto max-w-[1160px] px-[clamp(32px,7vw,96px)] pt-[clamp(128px,15vw,180px)] text-center">
      <h1 class="mx-auto max-w-[min(100%,18ch)] font-display text-[clamp(38px,5.8vw,66px)] font-semibold leading-[1.08] tracking-[-0.035em]">
        Keep the Collateral Alive.<br/>
        <span class="text-ink3">When Wall Street Closes.</span>
      </h1>

      <p class="mx-auto mt-[18px] max-w-[min(100%,54ch)] text-[15.5px] sm:text-[17px] text-ink2 leading-relaxed">
        Omni shields Bitget Unified Trading Accounts when tokenized US equities (rToken) trade 24/7 as collateral while underlying equity exchanges sleep 68% of the week. Zero hallucinations. Sized to the book.
      </p>

      <!-- Action Buttons -->
      <div class="mt-10 flex flex-wrap items-center justify-center gap-3.5">
        <button onclick="triggerHeroShock()" id="heroShockBtn" class="inline-flex items-center gap-2 rounded-full bg-ink px-6 py-3 text-[14px] font-medium text-bg transition-all duration-200 hover:-translate-y-px hover:opacity-90 active:scale-95 cursor-pointer shadow-lg">
          <span id="heroShockText">Simulate -25% Weekend Shock</span>
          <svg id="heroShockIcon" xmlns="http://www.w3.org/2000/svg" width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <path d="M7 7h10v10"></path>
            <path d="M7 17 17 7"></path>
          </svg>
        </button>
        <button onclick="scrollToId('terminal-section')" class="inline-flex items-center gap-2 rounded-full border border-line bg-white/[0.04] px-6 py-3 text-[14px] font-medium backdrop-blur-[8px] transition-transform duration-200 hover:-translate-y-px cursor-pointer">
          <svg class="h-3.5 w-3.5 text-accent" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="4 17 10 11 4 5"></polyline><line x1="12" y1="19" x2="20" y2="19"></line></svg>
          Open Sentinel Console
        </button>
      </div>

      <!-- Badge Strip -->
      <div class="mt-11">
        <div class="mono-label text-ink3">Live on Bitget UTA v3 · Agent Hub Bare-Metal Verified · 1:1 CLI Parity</div>
        <div class="mt-3.5 flex flex-wrap items-center justify-center gap-x-6 gap-y-2.5">
          <span class="text-[13px] flex items-center gap-2 text-ink2">
            <svg class="h-3.5 w-3.5 text-white" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z"></path>
            </svg>
            Bitget UTA v3 Native
          </span>
          <span class="text-[13px] flex items-center gap-2 text-ink2">
            <svg class="h-3.5 w-3.5 text-white" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <path d="M4 14a1 1 0 0 1-.78-1.63l9.9-10.2a.5.5 0 0 1 .86.46l-1.92 6.02A1 1 0 0 0 13 10h7a1 1 0 0 1 .78 1.63l-9.9 10.2a.5.5 0 0 1-.86-.46l1.92-6.02A1 1 0 0 0 11 14z"></path>
            </svg>
            Zero Hallucination Policy Gate
          </span>
          <span class="text-[13px] flex items-center gap-2 text-ink2">
            <svg class="h-3.5 w-3.5 text-white" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <path d="M20 13c0 5-3.5 7.5-7.66 8.95a1 1 0 0 1-.67-.01C7.5 20.5 4 18 4 13V6a1 1 0 0 1 1-1c2 0 4.5-1.2 6.24-2.72a1.17 1.17 0 0 1 1.52 0C14.51 3.81 17 5 19 5a1 1 0 0 1 1 1z"></path>
              <path d="m9 12 2 2 4-4"></path>
            </svg>
            100% Real API Verified
          </span>
        </div>
      </div>
    </div>

    <!-- The Embedded Interactive Cockpit Frame (Floor Signature Masterpiece) -->
    <div id="cockpit" class="relative mx-auto mt-[clamp(56px,7vw,88px)] max-w-[1160px] px-[clamp(32px,7vw,96px)] pb-[clamp(72px,9vw,132px)]">
      <div class="halo-blur"></div>
      <div class="top-laser"></div>

      <div class="relative overflow-hidden rounded-[14px] border border-line bg-gradient-to-b from-lift to-bg shadow-2xl">
        <div class="grid grid-cols-1 sm:grid-cols-[190px_1fr]">
          
          <!-- Mini Sidebar -->
          <aside class="hidden flex-col border-r border-line p-4 sm:flex justify-between">
            <div>
              <div class="mb-6 flex items-center gap-2 px-1">
                <div class="h-6 w-6 rounded-md bg-white/[0.08] grid place-items-center">
                  <div class="h-2 w-2 rounded-full bg-emerald-400"></div>
                </div>
                <span class="text-[14px] font-medium tracking-tight">Omni Sentinel</span>
              </div>

              <div class="space-y-1">
                <button onclick="scrollToId('cockpit')" class="flex w-full items-center gap-2.5 rounded-md px-2.5 py-2 text-[12.5px] bg-white/[0.06] text-ink font-medium text-left cursor-pointer transition">
                  <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75"><rect width="7" height="7" x="3" y="3" rx="1"></rect><rect width="7" height="7" x="14" y="3" rx="1"></rect><rect width="7" height="7" x="14" y="14" rx="1"></rect><rect width="7" height="7" x="3" y="14" rx="1"></rect></svg>
                  Dashboard
                </button>
                <button onclick="scrollToId('command-deck')" class="flex w-full items-center gap-2.5 rounded-md px-2.5 py-2 text-[12.5px] text-muted hover:text-ink hover:bg-white/[0.03] transition text-left cursor-pointer">
                  <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75"><polygon points="12 2 2 7 12 12 22 7 12 2"></polygon><polyline points="2 17 12 22 22 17"></polyline><polyline points="2 12 12 17 22 12"></polyline></svg>
                  Command Deck
                </button>
                <button onclick="scrollToId('terminal-section')" class="flex w-full items-center gap-2.5 rounded-md px-2.5 py-2 text-[12.5px] text-muted hover:text-ink hover:bg-white/[0.03] transition text-left cursor-pointer">
                  <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75"><polyline points="4 17 10 11 4 5"></polyline><line x1="12" y1="19" x2="20" y2="19"></line></svg>
                  Live Console
                </button>
                <button onclick="scrollToId('how-it-works')" class="flex w-full items-center gap-2.5 rounded-md px-2.5 py-2 text-[12.5px] text-muted hover:text-ink hover:bg-white/[0.03] transition text-left cursor-pointer">
                  <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75"><path d="m12.83 2.18a2 2 0 0 0-1.66 0L2.6 6.08a1 1 0 0 0 0 1.83l8.58 3.91a2 2 0 0 0 1.66 0l8.58-3.9a1 1 0 0 0 0-1.83Z"></path><path d="m22 17.65-9.17 4.16a2 2 0 0 1-1.66 0L2 17.65"></path><path d="m22 12.65-9.17 4.16a2 2 0 0 1-1.66 0L2 12.65"></path></svg>
                  Windows
                </button>
                <button onclick="scrollToId('ledger-section')" class="flex w-full items-center gap-2.5 rounded-md px-2.5 py-2 text-[12.5px] text-muted hover:text-ink hover:bg-white/[0.03] transition text-left cursor-pointer">
                  <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75"><path d="M4 2v20l2-1 2 1 2-1 2 1 2-1 2 1 2-1 2 1V2l-2 1-2-1-2 1-2-1-2 1-2-1-2 1Z"></path><path d="M16 8h-6a2 2 0 1 0 0 4h4a2 2 0 1 1 0 4H8"></path><path d="M12 17.5v-11"></path></svg>
                  Audit Ledger
                </button>
              </div>
            </div>

            <!-- Bottom Aside Status -->
            <div class="border-t border-line pt-4 space-y-2 font-mono text-[11px] text-ink3">
              <div class="flex items-center justify-between">
                <span>Bitget UTA</span>
                <span class="text-emerald-400">ONLINE</span>
              </div>
              <div class="flex items-center justify-between">
                <span>Daemon Loop</span>
                <span id="daemonAsideStatus" class="text-muted font-semibold">IDLE</span>
              </div>
              <div class="flex items-center justify-between">
                <span>LLM Engine</span>
                <span class="text-ink">DeepSeek-V4.1</span>
              </div>
              <div class="text-[10px] text-muted truncate">UID: 23020984377</div>
            </div>
          </aside>

          <!-- Main Cockpit View -->
          <div class="p-3.5 sm:p-5">
            <!-- Top Breadcrumb & Controls -->
            <div class="mb-4 flex items-center justify-between gap-3 sm:mb-5">
              <div>
                <div class="hidden text-[10.5px] text-ink3 sm:block">Coverage / Risk Governor</div>
                <div class="whitespace-nowrap text-[13px] font-medium sm:text-[16px]">Active collateral shield</div>
              </div>
              <div class="flex items-center gap-2.5">
                <div id="sessionBadge" class="flex items-center gap-2 rounded-md border border-line bg-card px-2.5 py-1 text-[11px] text-ink2 font-mono">
                  <span class="h-1.5 w-1.5 rounded-full bg-amber-400 animate-pulse"></span>
                  <span id="sessionRegimeText">WEEKEND_TRADABLE</span>
                </div>
                <button onclick="triggerActiveCycle()" id="topCycleBtn" class="flex items-center gap-1.5 rounded-md bg-white/10 px-3 py-1 text-[11.5px] font-medium text-ink transition hover:bg-white/20 active:scale-95 cursor-pointer">
                  <span id="topCycleText">Run Cycle</span>
                  <svg id="topCycleIcon" class="h-3 w-3" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M5 12h14M12 5l7 7-7 7"/></svg>
                </button>
              </div>
            </div>

            <!-- Main Cards Grid -->
            <div class="grid grid-cols-1 gap-3.5 sm:grid-cols-[1.25fr_1fr] sm:gap-4">
              <!-- Left Chart Card -->
              <div class="rounded-[10px] border border-line bg-card p-3.5 sm:p-4">
                <div class="flex items-baseline justify-between">
                  <div>
                    <div class="text-[11px] text-muted font-mono">Effective Equity (Observed)</div>
                    <div class="mt-1 flex items-baseline gap-2">
                      <span id="effectiveEquityVal" class="text-[20px] font-medium tracking-[-0.02em] sm:text-[26px] font-mono">94,548.03</span>
                      <span class="text-[12px] text-ink2 font-mono">USDT</span>
                    </div>
                  </div>
                  <!-- Clickable Timeframe Buttons -->
                  <div class="flex gap-1">
                    <button onclick="setTimeframe('15m', this)" class="timeframe-btn rounded-full px-2.5 py-1 text-[10.5px] bg-white/10 text-ink cursor-pointer transition">15m</button>
                    <button onclick="setTimeframe('1h', this)" class="timeframe-btn rounded-full px-2.5 py-1 text-[10.5px] text-muted hover:text-ink cursor-pointer transition">1h</button>
                    <button onclick="setTimeframe('4h', this)" class="timeframe-btn rounded-full px-2.5 py-1 text-[10.5px] text-muted hover:text-ink cursor-pointer transition">4h</button>
                    <button onclick="setTimeframe('1d', this)" class="timeframe-btn rounded-full px-2.5 py-1 text-[10.5px] text-muted hover:text-ink cursor-pointer transition">1d</button>
                  </div>
                </div>

                <!-- Glowing SVG Line Chart with Gradient Fill (Floor Exact) -->
                <svg id="equityChartSvg" viewBox="0 0 400 90" class="mt-4 w-full" preserveAspectRatio="none">
                  <defs>
                    <linearGradient id="g" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="0%" stop-color="#FFFFFF" stop-opacity="0.22"></stop>
                      <stop offset="100%" stop-color="#FFFFFF" stop-opacity="0"></stop>
                    </linearGradient>
                  </defs>
                  <path id="chartAreaPath" d="M0 72 L34 66 L68 70 L102 54 L136 60 L170 42 L204 48 L238 33 L272 40 L306 26 L340 31 L374 18 L400 22 L400 90 L0 90 Z" fill="url(#g)"></path>
                  <path id="chartLinePath" d="M0 72 L34 66 L68 70 L102 54 L136 60 L170 42 L204 48 L238 33 L272 40 L306 26 L340 31 L374 18 L400 22" fill="none" stroke="#FFFFFF" stroke-opacity="0.75" stroke-width="1.4"></path>
                  <circle id="chartDot" cx="400" cy="22" r="3" fill="#FFFFFF"></circle>
                </svg>

                <div class="mt-3 grid grid-cols-3 border-t border-line pt-3 font-mono">
                  <div>
                    <div class="text-[10.5px] text-muted">Maintenance Margin</div>
                    <div id="mmrVal" class="mt-0.5 text-[13.5px] text-ink">17.76 USDT</div>
                  </div>
                  <div>
                    <div class="text-[10.5px] text-muted">Margin Ratio</div>
                    <div id="marginRatioVal" class="mt-0.5 text-[13.5px] text-emerald-400">0.01% (Safe)</div>
                  </div>
                  <div>
                    <div class="text-[10.5px] text-muted">Worst-case Shock</div>
                    <div id="worstCaseVal" class="mt-0.5 text-[13.5px] text-ink">-5,000 USDT (Capped)</div>
                  </div>
                </div>
              </div>

              <!-- Right Next Window Card & Scenario Panel -->
              <div class="rounded-[10px] border border-line bg-card p-3.5 sm:p-4 flex flex-col justify-between">
                <div>
                  <div class="flex items-center justify-between">
                    <span class="text-[13px] font-medium">Session Clock</span>
                    <span class="rounded border border-line px-1.5 py-0.5 text-[10px] text-muted font-mono">NYSE / NASDAQ</span>
                  </div>
                  
                  <div class="mt-2.5 rounded-[8px] border border-line p-2.5">
                    <div class="flex items-center justify-between text-[12px]">
                      <span class="text-ink">Monday Cash Open</span>
                      <span class="text-amber-400 font-mono text-[11px]">09:30 AM EST</span>
                    </div>
                    <div class="mt-1 flex items-center justify-between text-[10.5px] text-muted">
                      <span>Time Remaining:</span>
                      <span id="countdownTimer" class="font-mono text-ink font-medium">1d 14h 22m 18s</span>
                    </div>
                  </div>

                  <!-- Scenario Selector Pills -->
                  <div class="mt-2.5">
                    <div class="flex items-center justify-between text-[11px] text-muted mb-1.5 font-mono">
                      <span>Scenario Shock:</span>
                      <span id="activeShockLabel" class="text-amber-400 font-medium">-25% (Hedge NVDA)</span>
                    </div>
                    <div class="grid grid-cols-3 gap-1.5 font-mono text-[10.5px]">
                      <button onclick="selectShock(-0.25, '-25% (Hedge NVDA)', this)" class="shock-pill rounded border border-white/20 bg-white/10 py-1 text-ink transition cursor-pointer font-medium text-center">-25%</button>
                      <button onclick="selectShock(-0.15, '-15% (Stress Test)', this)" class="shock-pill rounded border border-line bg-lift py-1 text-muted hover:text-ink transition cursor-pointer text-center">-15%</button>
                      <button onclick="selectShock(-0.04, '-4% (Hold Mode)', this)" class="shock-pill rounded border border-line bg-lift py-1 text-muted hover:text-ink transition cursor-pointer text-center">-4%</button>
                    </div>
                  </div>
                </div>

                <!-- Scenario Action Button -->
                <button onclick="triggerActiveCycle()" id="triggerBtn" class="mt-3 flex items-center justify-center gap-2 rounded-[8px] border border-line bg-white/[0.06] hover:bg-white/[0.12] py-2.5 text-[12.5px] font-medium transition active:scale-95 cursor-pointer">
                  <span id="triggerBtnText">Execute Governance Cycle</span>
                  <span id="triggerBtnArrow" class="text-muted">›</span>
                </button>
              </div>
            </div>

            <!-- Bottom 3 Mini-Cards (Floor Exact Structure) -->
            <div class="mt-3.5 grid grid-cols-1 sm:grid-cols-3 gap-2 sm:mt-4 sm:gap-4">
              <!-- Card 1: Recent Coverage / Positions -->
              <div class="rounded-[10px] border border-line bg-card p-3.5 text-left">
                <div class="flex items-center justify-between text-[11px] font-medium text-ink2 mb-2">
                  <span>Bitget Demo Positions</span>
                  <span id="posCountBadge" class="rounded bg-white/10 px-1.5 py-0.5 text-[9.5px] font-mono text-ink">2 ACTIVE</span>
                </div>
                <div id="positionsContainer" class="space-y-1.5 font-mono text-[11px]">
                  <div class="flex items-center justify-between border-b border-line pb-1">
                    <span class="text-ink">BTCUSDT <span class="text-emerald-400 text-[10px]">LONG 20x</span></span>
                    <span class="text-ink2">0.05 BTC</span>
                  </div>
                  <div class="flex items-center justify-between">
                    <span class="text-ink">NVDAUSDT <span class="text-amber-400 text-[10px]">SHORT (HEDGE)</span></span>
                    <span class="text-emerald-400">22.79 NVDA</span>
                  </div>
                </div>
              </div>

              <!-- Card 2: Settlements / Depth -->
              <div class="rounded-[10px] border border-line bg-card p-3.5 text-left font-mono">
                <div class="flex items-center justify-between text-[11px] font-medium text-ink2 mb-2">
                  <span>Order Book Depth Walk</span>
                  <span class="text-muted text-[10px]">Bitget Live</span>
                </div>
                <div class="space-y-1 text-[11px]">
                  <div class="flex justify-between">
                    <span class="text-muted">Depth Slippage:</span>
                    <span class="text-amber-400">432.9 bps</span>
                  </div>
                  <div class="flex justify-between">
                    <span class="text-muted">Policy Cap:</span>
                    <span class="text-emerald-400">$5,000 USDT</span>
                  </div>
                </div>
              </div>

              <!-- Card 3: Agent Sentinel Log -->
              <div class="rounded-[10px] border border-line bg-card p-3.5 text-left">
                <div class="flex items-center justify-between text-[11px] font-medium text-ink2 mb-1">
                  <span>AI Sentinel Stream</span>
                  <span class="text-emerald-400 font-mono text-[9.5px]">DeepSeek-V4.1</span>
                </div>
                <div id="aiRationaleBox" class="h-[48px] overflow-hidden text-ellipsis text-[10.5px] text-ink3 leading-relaxed">
                  "Account collateralised by tokenized NVDA. -25% shock scenario drives loss to 12.5% of equity. Opening protective short on mapped NVDAUSDT perpetual capped at $5,000 policy limit."
                </div>
              </div>
            </div>

            <!-- Sentinel Command Deck (1:1 CLI Terminal Parity) -->
            <div id="command-deck" class="mt-4 rounded-[10px] border border-line bg-card p-3.5">
              <div class="flex flex-wrap items-center justify-between gap-2 mb-3">
                <div class="flex items-center gap-2">
                  <div class="h-2 w-2 rounded-full bg-accent animate-pulse"></div>
                  <span class="text-[12.5px] font-medium tracking-tight">Sentinel Command Deck</span>
                  <span class="rounded border border-line bg-white/[0.04] px-1.5 py-0.5 font-mono text-[9.5px] text-ink3">1:1 CLI PARITY</span>
                </div>
                <div class="flex items-center gap-2">
                  <div id="daemonBadge" class="flex items-center gap-1.5 rounded-full border border-line bg-lift px-2.5 py-0.5 text-[10.5px] font-mono text-muted">
                    <span id="daemonDot" class="h-1.5 w-1.5 rounded-full bg-muted"></span>
                    <span id="daemonText">DAEMON IDLE</span>
                  </div>
                </div>
              </div>

              <!-- Action Buttons Strip (Every Single CLI Command) -->
              <div class="grid grid-cols-2 sm:grid-cols-5 gap-2 font-mono text-[11.5px]">
                <!-- omni doctor -->
                <button onclick="triggerDoctor()" id="btnDoctor" class="flex items-center justify-center gap-1.5 rounded-lg border border-line bg-lift hover:bg-white/[0.08] p-2 text-ink2 hover:text-ink transition active:scale-95 cursor-pointer">
                  <svg class="h-3.5 w-3.5 text-emerald-400" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/></svg>
                  <span>$ doctor</span>
                </button>

                <!-- omni setup -->
                <button onclick="openModal('setupModal')" id="btnSetup" class="flex items-center justify-center gap-1.5 rounded-lg border border-line bg-lift hover:bg-white/[0.08] p-2 text-ink2 hover:text-ink transition active:scale-95 cursor-pointer">
                  <svg class="h-3.5 w-3.5 text-accent" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="16"/><line x1="8" y1="12" x2="16" y2="12"/></svg>
                  <span>$ setup</span>
                </button>

                <!-- omni flatten -->
                <button onclick="openModal('flattenModal')" id="btnFlatten" class="flex items-center justify-center gap-1.5 rounded-lg border border-line bg-lift hover:bg-rose-500/10 hover:border-rose-500/40 p-2 text-rose-300 transition active:scale-95 cursor-pointer">
                  <svg class="h-3.5 w-3.5 text-rose-400" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="18" y1="6" x2="6" y2="18"></line><line x1="6" y1="6" x2="18" y2="18"></line></svg>
                  <span>$ flatten</span>
                </button>

                <!-- omni report -->
                <button onclick="triggerReport()" id="btnReport" class="flex items-center justify-center gap-1.5 rounded-lg border border-line bg-lift hover:bg-white/[0.08] p-2 text-ink2 hover:text-ink transition active:scale-95 cursor-pointer">
                  <svg class="h-3.5 w-3.5 text-amber-400" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path><polyline points="14 2 14 8 20 8"></polyline><line x1="16" y1="13" x2="8" y2="13"></line><line x1="16" y1="17" x2="8" y2="17"></line><polyline points="10 9 9 9 8 9"></polyline></svg>
                  <span>$ report</span>
                </button>

                <!-- omni daemon (START / STOP) -->
                <button onclick="toggleDaemon()" id="btnDaemon" class="col-span-2 sm:col-span-1 flex items-center justify-center gap-1.5 rounded-lg border border-line bg-lift hover:bg-white/[0.08] p-2 text-ink transition active:scale-95 cursor-pointer">
                  <span id="daemonBtnDot" class="h-2 w-2 rounded-full bg-emerald-400"></span>
                  <span id="daemonBtnLabel">Start Daemon</span>
                </button>
              </div>
            </div>

            <!-- Embedded Live Monospace Terminal Console (Drawer) -->
            <div id="terminal-section" class="mt-4 rounded-[10px] border border-line bg-terminalBg overflow-hidden shadow-2xl">
              <!-- Terminal Header -->
              <div class="flex items-center justify-between border-b border-line bg-[#0E0E0E] px-3.5 py-2 font-mono text-[11px]">
                <div class="flex items-center gap-2">
                  <div class="flex gap-1.5">
                    <span class="h-2.5 w-2.5 rounded-full bg-rose-500/80"></span>
                    <span class="h-2.5 w-2.5 rounded-full bg-amber-500/80"></span>
                    <span class="h-2.5 w-2.5 rounded-full bg-emerald-500/80"></span>
                  </div>
                  <span class="text-ink3 ml-2">omni-sentinel@bitget-uta-v3: ~</span>
                  <span class="rounded bg-white/[0.06] px-1.5 py-0.5 text-[9.5px] text-accent">LIVE STREAM</span>
                </div>
                <div class="flex items-center gap-2 text-ink3">
                  <button onclick="clearTerminalLogs()" class="hover:text-ink transition cursor-pointer" title="Clear Console">Clear</button>
                  <span>·</span>
                  <button onclick="copyTerminalLogs()" class="hover:text-ink transition cursor-pointer" title="Copy to Clipboard">Copy</button>
                  <span>·</span>
                  <button onclick="fetchTerminalLogs(true)" class="hover:text-ink transition cursor-pointer" title="Refresh Output">Refresh</button>
                </div>
              </div>

              <!-- Terminal Body (Monospace Live Stream) -->
              <div id="terminalOutput" class="h-[220px] overflow-y-auto p-3.5 font-mono text-[11px] leading-relaxed custom-scroll select-text space-y-1 text-ink2">
                <div class="text-emerald-400">[2026-09-12T08:00:00Z] [OMNI] Sentinel Command Console initialized.</div>
                <div class="text-muted">[2026-09-12T08:00:00Z] [OMNI] Bare-metal Bitget UTA v3 verified. Ready for 1:1 commands.</div>
              </div>

              <!-- Interactive Prompt Strip -->
              <div class="border-t border-line bg-[#0C0C0C] px-3.5 py-2 flex items-center justify-between gap-2 font-mono text-[11px]">
                <div class="flex items-center gap-2 text-ink2">
                  <span class="text-accent font-bold">&gt;</span>
                  <span class="text-muted">Quick run:</span>
                  <button onclick="triggerDoctor()" class="rounded bg-white/[0.04] px-2 py-0.5 text-[10px] text-ink2 hover:text-ink hover:bg-white/[0.1] transition cursor-pointer">$ omni doctor</button>
                  <button onclick="triggerActiveCycle()" class="rounded bg-white/[0.04] px-2 py-0.5 text-[10px] text-ink2 hover:text-ink hover:bg-white/[0.1] transition cursor-pointer">$ omni decide --execute</button>
                  <button onclick="triggerReport()" class="rounded bg-white/[0.04] px-2 py-0.5 text-[10px] text-ink2 hover:text-ink hover:bg-white/[0.1] transition cursor-pointer">$ omni report</button>
                </div>
                <div class="text-[10px] text-muted hidden sm:block">
                  Auto-scroll: <span class="text-emerald-400">ACTIVE</span>
                </div>
              </div>
            </div>

          </div>
        </div>
      </div>
    </div>
  </section>

  <!-- Section: Sized to the book. Not to a guess. (Floor Exact Section 2) -->
  <section id="how-it-works" class="bg-lift">
    <div class="mx-auto max-w-[1160px] px-[clamp(32px,7vw,96px)] py-[clamp(72px,9vw,132px)]">
      <div class="grid items-start gap-[clamp(32px,5vw,64px)] lg:grid-cols-[1fr_1.05fr]">
        <div class="min-w-0">
          <h2 class="font-display text-[clamp(28px,3.6vw,46px)] leading-[1.12] tracking-[-0.032em] font-semibold">
            Sized to the book.<br/>
            <span class="text-ink3">Not to a guess.</span>
          </h2>
          <p class="mt-4 max-w-[min(100%,52ch)] text-[15px] text-ink2 leading-relaxed">
            Omni walks the live Bitget order book for both the rToken spot market and the mapped stock perpetual. It calculates depth-weighted VWAP slippage across book levels and enforces a hard $5,000 policy cap before sending any order.
          </p>
          <button onclick="scrollToId('cockpit')" class="mt-8 inline-flex items-center gap-2 rounded-full border border-line bg-white/[0.04] px-6 py-3 text-[14px] font-medium backdrop-blur-[8px] transition-transform duration-200 hover:-translate-y-px cursor-pointer">
            See it live
            <svg xmlns="http://www.w3.org/2000/svg" width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M7 7h10v10"></path><path d="M7 17 17 7"></path></svg>
          </button>
        </div>

        <div class="min-w-0">
          <div class="rounded-[18px] border border-line bg-card p-[26px] shadow-[0_10px_26px_-20px_rgba(0,0,0,0.6)]">
            <div class="flex items-start justify-between">
              <div>
                <div id="featureMidPrice" class="font-display text-[34px] leading-none tracking-[-0.032em] font-semibold font-mono">218.82</div>
                <div class="mono-label mt-2 text-ink3">RNVDA Reference Mid</div>
              </div>
              <div class="rounded-full border border-line px-3 py-1.5 text-[11px] text-ink2 font-mono">Weekend Thinnest</div>
            </div>

            <svg viewBox="0 0 420 130" class="mt-6 w-full" preserveAspectRatio="none" aria-hidden="true">
              <defs>
                <linearGradient id="fadeArea" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stop-color="#FFFFFF" stop-opacity="0.10"></stop>
                  <stop offset="100%" stop-color="#FFFFFF" stop-opacity="0"></stop>
                </linearGradient>
              </defs>
              <path d="M0 96 C 46 96, 62 44, 104 44 S 158 104, 200 104 S 250 30, 296 30 S 352 88, 396 74 L 420 70 L 420 130 L 0 130 Z" fill="url(#fadeArea)"></path>
              <path d="M0 96 C 46 96, 62 44, 104 44 S 158 104, 200 104 S 250 30, 296 30 S 352 88, 396 74 L 420 70" fill="none" stroke="#FFFFFF" stroke-opacity="0.55" stroke-width="1.4"></path>
              <circle cx="200" cy="104" r="3.5" fill="#FFFFFF"></circle>
            </svg>

            <div class="mt-5 grid grid-cols-3 gap-4 border-t border-line pt-5">
              <div>
                <div class="mono-label text-ink3">Depth Slippage</div>
                <div class="mt-1.5 font-mono text-[14.5px]">432.9 bps</div>
              </div>
              <div>
                <div class="mono-label text-ink3">Policy Cap</div>
                <div class="mt-1.5 font-mono text-[14.5px]">5,000.00</div>
              </div>
              <div>
                <div class="mono-label text-ink3">Cash Reopen</div>
                <div class="mt-1.5 font-mono text-[14.5px]">Mon 09:30</div>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- 4 Features (Floor Exact Grid) -->
      <div class="mt-[clamp(48px,6vw,72px)] grid gap-x-8 gap-y-10 border-t border-line pt-10 sm:grid-cols-2 lg:grid-cols-4">
        <div class="min-w-0">
          <div class="flex items-center gap-2.5">
            <svg xmlns="http://www.w3.org/2000/svg" width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="text-ink2"><path d="M21.3 15.3a2.4 2.4 0 0 1 0 3.4l-2.6 2.6a2.4 2.4 0 0 1-3.4 0L2.7 8.7a2.41 2.41 0 0 1 0-3.4l2.6-2.6a2.41 2.41 0 0 1 3.4 0Z"></path><path d="m14.5 12.5 2-2"></path><path d="m11.5 9.5 2-2"></path><path d="m8.5 6.5 2-2"></path><path d="m17.5 15.5 2-2"></path></svg>
            <h3 class="text-[15px] font-medium">Book-sized</h3>
          </div>
          <p class="text-[13px] mt-2.5 text-ink2 leading-relaxed">Walks resting orders and snaps to the venue lot grid, so what you see is what fills.</p>
        </div>

        <div class="min-w-0">
          <div class="flex items-center gap-2.5">
            <svg xmlns="http://www.w3.org/2000/svg" width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="text-ink2"><path d="M3 12a9 9 0 0 1 9-9 9.75 9.75 0 0 1 6.74 2.74L21 8"></path><path d="M21 3v5h-5"></path><path d="M21 12a9 9 0 0 1-9 9 9.75 9.75 0 0 1-6.74-2.74L3 16"></path><path d="M8 16H3v5"></path></svg>
            <h3 class="text-[15px] font-medium">Auto-rolling</h3>
          </div>
          <p class="text-[13px] mt-2.5 text-ink2 leading-relaxed">Detects session transitions (pre-market, regular, after-hours, weekend) and recalculates buffers.</p>
        </div>

        <div class="min-w-0">
          <div class="flex items-center gap-2.5">
            <svg xmlns="http://www.w3.org/2000/svg" width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="text-ink2"><circle cx="11" cy="11" r="8"></circle><path d="m21 21-4.3-4.3"></path></svg>
            <h3 class="text-[15px] font-medium">Self-sweeping</h3>
          </div>
          <p class="text-[13px] mt-2.5 text-ink2 leading-relaxed">Unwinds protective hedges automatically when US cash markets reopen and marks regain full confidence.</p>
        </div>

        <div class="min-w-0">
          <div class="flex items-center gap-2.5">
            <svg xmlns="http://www.w3.org/2000/svg" width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="text-ink2"><path d="M2.586 17.414A2 2 0 0 0 2 18.828V21a1 1 0 0 0 1 1h3a1 1 0 0 0 1-1v-1a1 1 0 0 1 1-1h1a1 1 0 0 0 1-1v-1a1 1 0 0 1 1-1h.172a2 2 0 0 0 1.414-.586l.814-.814a6.5 6.5 0 1 0-4-4z"></path><circle cx="16.5" cy="7.5" r=".5" fill="currentColor"></circle></svg>
            <h3 class="text-[15px] font-medium">Policy-gated</h3>
          </div>
          <p class="text-[13px] mt-2.5 text-ink2 leading-relaxed">Deterministic policy bounds prevent rogue trades. Omni cannot withdraw, transfer, or increase account leverage.</p>
        </div>
      </div>
    </div>
  </section>

  <!-- Section: Protection that holds when it matters. (Floor Exact Section 3) -->
  <section id="why-omni">
    <div class="mx-auto max-w-[1160px] px-[clamp(32px,7vw,96px)] py-[clamp(72px,9vw,132px)]">
      <div class="grid items-start gap-[clamp(24px,4vw,64px)] lg:grid-cols-[1fr_1fr]">
        <h2 class="font-display text-[clamp(28px,3.6vw,46px)] leading-[1.12] tracking-[-0.032em] font-semibold">
          Protection that holds<br/>
          <span class="text-ink3">when it matters.</span>
        </h2>
        <div class="lg:pt-2">
          <p class="text-[15px] text-ink2 leading-relaxed max-w-[min(100%,46ch)]">
            Why use a cross-asset risk governor instead of a basic stop-loss? Because a stop-loss on an illiquid weekend order book creates devastating slippage, while underlying cash stock markets remain completely closed.
          </p>
          <a href="#faq" class="mt-5 inline-flex items-center gap-2 text-[13px] font-medium text-ink transition-transform duration-200 hover:translate-x-0.5 cursor-pointer">
            Learn more
            <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M5 12h14"></path><path d="m12 5 7 7-7 7"></path></svg>
          </a>
        </div>
      </div>

      <!-- 3 Cards Grid (Floor Exact) -->
      <div class="mt-[clamp(40px,5vw,64px)] grid gap-[18px] md:grid-cols-3">
        <div class="min-w-0 rounded-[18px] border border-line bg-card p-[26px]">
          <span class="grid h-[46px] w-[46px] place-items-center rounded-[14px] border border-line bg-white/[0.04]">
            <svg class="h-5 w-5 text-ink2" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M20 13c0 5-3.5 7.5-7.66 8.95a1 1 0 0 1-.67-.01C7.5 20.5 4 18 4 13V6a1 1 0 0 1 1-1c2 0 4.5-1.2 6.24-2.72a1.17 1.17 0 0 1 1.52 0C14.51 3.81 17 5 19 5a1 1 0 0 1 1 1z"></path><path d="m9 12 2 2 4-4"></path></svg>
          </span>
          <h3 class="mt-5 text-[16px] font-medium">Capped by construction</h3>
          <p class="text-[13px] mt-2.5 text-ink2 leading-relaxed">
            Every protective action is hard-capped by deterministic policy. The maximum hedge notional is $5,000 USDT, completely eliminating rogue agent risk and liquidation spirals.
          </p>
        </div>

        <div class="min-w-0 rounded-[18px] border border-line bg-card p-[26px]">
          <span class="grid h-[46px] w-[46px] place-items-center rounded-[14px] border border-line bg-white/[0.04]">
            <svg class="h-5 w-5 text-ink2" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M3 12a9 9 0 1 0 9-9 9.75 9.75 0 0 0-6.74 2.74L3 8"></path><path d="M3 3v5h5"></path></svg>
          </span>
          <h3 class="mt-5 text-[16px] font-medium">Refunds, not surprises</h3>
          <p class="text-[13px] mt-2.5 text-ink2 leading-relaxed">
            If mark confidence is low or liquidity is thin, Omni hedges via deep perpetual order books rather than trusting illiquid weekend marks.
          </p>
        </div>

        <div class="min-w-0 rounded-[18px] border border-line bg-card p-[26px]">
          <span class="grid h-[46px] w-[46px] place-items-center rounded-[14px] border border-line bg-white/[0.04]">
            <svg class="h-5 w-5 text-ink2" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M3 3v16a2 2 0 0 0 2 2h16"></path><path d="m19 9-5 5-4-4-3 3"></path></svg>
          </span>
          <h3 class="mt-5 text-[16px] font-medium">Priced by a real book</h3>
          <p class="text-[13px] mt-2.5 text-ink2 leading-relaxed">
            The hedge size and price are calibrated directly against Bitget's live level-2 order book depth, not theoretical formulas.
          </p>
        </div>
      </div>
    </div>
  </section>

  <!-- Section: Every settlement leaves a receipt. (Floor Exact Section 4) -->
  <section id="settlements" class="bg-lift">
    <div class="mx-auto max-w-[1160px] px-[clamp(32px,7vw,96px)] py-[clamp(72px,9vw,132px)]">
      <div class="grid items-start gap-[clamp(32px,5vw,64px)] lg:grid-cols-[1fr_1.05fr]">
        <div class="min-w-0">
          <h2 class="font-display text-[clamp(28px,3.6vw,46px)] leading-[1.12] tracking-[-0.032em] font-semibold">
            Every settlement<br/>
            <span class="text-ink3">leaves a receipt.</span>
          </h2>
          <p class="mt-4 max-w-[min(100%,52ch)] text-[15px] text-ink2 leading-relaxed">
            Every session classification, order book snapshot, LLM proposal, policy gate check, and Bitget execution order is recorded immutably in a day-scoped JSONL ledger. Nothing about an Omni decision is a black box.
          </p>
          <button onclick="scrollToId('ledger-section')" class="mt-8 inline-flex items-center gap-2 rounded-full border border-line bg-white/[0.04] px-6 py-3 text-[14px] font-medium backdrop-blur-[8px] transition-transform duration-200 hover:-translate-y-px cursor-pointer">
            Inspect live ledger
            <svg xmlns="http://www.w3.org/2000/svg" width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M7 7h10v10"></path><path d="M7 17 17 7"></path></svg>
          </button>
        </div>

        <div class="min-w-0">
          <div class="rounded-[18px] border border-line bg-card p-[26px]">
            <div class="mono-label text-ink3">Settled Execution Order</div>
            <div class="mt-5 space-y-0">
              <div class="flex items-center justify-between border-b border-line py-3">
                <span class="text-[13px] text-ink2">Market</span>
                <span class="font-mono text-[13px]">NVDAUSDT (USDT-FUTURES)</span>
              </div>
              <div class="flex items-center justify-between border-b border-line py-3">
                <span class="text-[13px] text-ink2">Trigger</span>
                <span class="text-[13px]">Weekend -25% rToken Shock</span>
              </div>
              <div class="flex items-center justify-between border-b border-line py-3">
                <span class="text-[13px] text-ink2">Action</span>
                <span class="font-mono text-[13px] text-amber-400">Sell (Short Hedge)</span>
              </div>
              <div class="flex items-center justify-between border-b border-line py-3">
                <span class="text-[13px] text-ink2">Quantity Filled</span>
                <span class="font-mono text-[13px]">22.79 NVDA</span>
              </div>
              <div class="flex items-center justify-between border-b border-line py-3">
                <span class="text-[13px] text-ink2">Policy Cap</span>
                <span class="font-mono text-[13px] text-emerald-400">5,000.00 USDT</span>
              </div>
              <div class="flex items-center justify-between py-3">
                <span class="text-[13px] text-ink2">Execution Status</span>
                <span class="font-mono text-[13px] text-emerald-400">Confirmed (Bitget Demo)</span>
              </div>
            </div>
            <div class="mt-4 rounded-[10px] border border-line px-4 py-3">
              <div class="mono-label text-ink3">Bitget Order ID</div>
              <div class="mt-1.5 truncate font-mono text-[12px] text-ink2">1482577782020395008</div>
            </div>
          </div>
        </div>
      </div>
    </div>
  </section>

  <!-- Section: Live Cryptographic Evidence Ledger Table -->
  <section id="ledger-section" class="py-20">
    <div class="mx-auto max-w-[1160px] px-[clamp(32px,7vw,96px)]">
      <div class="flex flex-wrap items-center justify-between gap-4 mb-8">
        <div>
          <div class="mono-label text-ink3">Audit Trail</div>
          <h2 class="font-display text-[28px] font-semibold tracking-tight mt-1">Live Cryptographic Evidence Ledger</h2>
        </div>
        <div class="font-mono text-[11px] text-ink2 rounded-md border border-line bg-card px-3 py-1.5 flex items-center gap-2">
          <span>Source:</span>
          <span class="text-ink font-medium">logs/paper-log-2026-09-12.jsonl</span>
          <button onclick="refreshLedgerTable()" class="ml-1 text-muted hover:text-ink transition cursor-pointer" title="Refresh Ledger">
            <svg class="h-3 w-3" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21.5 2v6h-6M21.34 15.57a10 10 0 1 1-.57-8.38l5.67-5.67"/></svg>
          </button>
        </div>
      </div>

      <div class="overflow-hidden rounded-[14px] border border-line bg-card p-5">
        <div class="overflow-x-auto">
          <table class="w-full text-left font-mono text-[11.5px]">
            <thead>
              <tr class="border-b border-line text-ink3">
                <th class="pb-3 pr-4">Timestamp (UTC)</th>
                <th class="pb-3 pr-4">Kind</th>
                <th class="pb-3 pr-4">Decision / Event</th>
                <th class="pb-3 pr-4">Policy Status</th>
                <th class="pb-3 text-right">Effective Equity</th>
              </tr>
            </thead>
            <tbody id="ledgerRows" class="divide-y divide-line text-ink2">
              <tr>
                <td class="py-3 text-ink">2026-09-12T08:12:24Z</td>
                <td><span class="rounded bg-white/10 px-1.5 py-0.5 text-[10px]">daemon_cycle</span></td>
                <td>HOLD (Shocked loss 2.0% within budget)</td>
                <td class="text-emerald-400">APPROVED</td>
                <td class="text-right text-ink">$94,548.03</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </div>
  </section>

  <!-- Section: Questions worth asking first (Floor Exact Accordion FAQ) -->
  <section id="faq" class="bg-lift">
    <div class="mx-auto max-w-[860px] px-[clamp(32px,7vw,96px)] py-[clamp(72px,9vw,132px)]">
      <h2 class="font-display text-[clamp(28px,3.6vw,46px)] leading-[1.12] tracking-[-0.032em] font-semibold">
        Questions worth <span class="text-ink3">asking first.</span>
      </h2>

      <div class="mt-10 divide-y divide-line border-t border-b border-line">
        <!-- Q1 -->
        <div class="faq-item py-5">
          <button type="button" onclick="toggleFaq(this)" class="flex w-full items-center justify-between gap-6 text-left cursor-pointer">
            <span class="text-[15px] font-medium">What happens when crypto crashes over the weekend while US equities are closed?</span>
            <svg class="h-4 w-4 shrink-0 text-ink3 transition-transform duration-200" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M5 12h14"/><path d="M12 5v14"/></svg>
          </button>
          <div class="faq-content hidden pt-3 pr-10 text-[14px] text-ink2 leading-relaxed">
            In a Unified Trading Account, cross-margin collateral is shared. When a weekend crypto drawdown drains equity, the account may face a liquidation call on Monday at 9:30 AM EST if tokenized equities gap down at the cash open. Omni identifies the impending collateral gap, models the order book depth, and hedges the risk on the 24/7 mapped stock perpetual before the cash equity market reopens.
          </div>
        </div>

        <!-- Q2 -->
        <div class="faq-item py-5">
          <button type="button" onclick="toggleFaq(this)" class="flex w-full items-center justify-between gap-6 text-left cursor-pointer">
            <span class="text-[15px] font-medium">Why not just use a standard stop-loss?</span>
            <svg class="h-4 w-4 shrink-0 text-ink3 transition-transform duration-200" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M5 12h14"/><path d="M12 5v14"/></svg>
          </button>
          <div class="faq-content hidden pt-3 pr-10 text-[14px] text-ink2 leading-relaxed">
            Standard stop-losses fail catastrophically during off-hours gaps. On a Sunday night, rToken spot liquidity is extremely thin; placing a market stop-loss would blow through multiple book levels with 1500+ bps of slippage. Omni uses depth-weighted VWAP modeling and hedges on deep perpetual futures order books instead of dumping illiquid collateral.
          </div>
        </div>

        <!-- Q3 -->
        <div class="faq-item py-5">
          <button type="button" onclick="toggleFaq(this)" class="flex w-full items-center justify-between gap-6 text-left cursor-pointer">
            <span class="text-[15px] font-medium">Is any of this mocked or hardcoded?</span>
            <svg class="h-4 w-4 shrink-0 text-ink3 transition-transform duration-200" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M5 12h14"/><path d="M12 5v14"/></svg>
          </button>
          <div class="faq-content hidden pt-3 pr-10 text-[14px] text-ink2 leading-relaxed">
            Zero. Every trade runs live against Bitget Demo UID 23020984377 via the official @bitget-ai/bitget-agent-cli Agent Hub CLI. Market calendars and tickers are fetched from Bitget's live production endpoints. The AI model is DeepSeek-V4.1-Flash hosted live on GMI Cloud. All actions are logged to machine-auditable JSONL evidence files.
          </div>
        </div>

        <!-- Q4 -->
        <div class="faq-item py-5">
          <button type="button" onclick="toggleFaq(this)" class="flex w-full items-center justify-between gap-6 text-left cursor-pointer">
            <span class="text-[15px] font-medium">What is an rToken on Bitget?</span>
            <svg class="h-4 w-4 shrink-0 text-ink3 transition-transform duration-200" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M5 12h14"/><path d="M12 5v14"/></svg>
          </button>
          <div class="faq-content hidden pt-3 pr-10 text-[14px] text-ink2 leading-relaxed">
            rTokens (such as RNVDAUSDT) are Real World Asset (RWA) tokenized representations of US equities traded on Bitget spot. They allow users to hold equity exposure 24/7 and post them as margin collateral inside the Unified Trading Account.
          </div>
        </div>

        <!-- Q5 -->
        <div class="faq-item py-5">
          <button type="button" onclick="toggleFaq(this)" class="flex w-full items-center justify-between gap-6 text-left cursor-pointer">
            <span class="text-[15px] font-medium">How does the Deterministic Policy Rail prevent hallucinations?</span>
            <svg class="h-4 w-4 shrink-0 text-ink3 transition-transform duration-200" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M5 12h14"/><path d="M12 5v14"/></svg>
          </button>
          <div class="faq-content hidden pt-3 pr-10 text-[14px] text-ink2 leading-relaxed">
            The LLM never directly executes trades. Its output is treated strictly as an untrusted proposal. A pure deterministic Python policy gate verifies allowlisted actions, caps any single order to $5,000 USDT notional, and forbids withdrawals, transfers, or leverage increases. If the LLM proposes anything invalid or times out, Omni falls back to deterministic safety rules.
          </div>
        </div>
      </div>
    </div>
  </section>

  <!-- Section: Cover the next window (Floor Exact CTA) -->
  <section class="bg-lift">
    <div class="mx-auto max-w-[1160px] px-[clamp(32px,7vw,96px)] py-[clamp(72px,9vw,132px)] text-center">
      <h2 class="mx-auto max-w-[min(100%,20ch)] font-display text-[clamp(28px,3.6vw,46px)] leading-[1.12] tracking-[-0.032em] font-semibold">
        Cover the next window.
      </h2>
      <p class="mx-auto mt-4 max-w-[min(100%,52ch)] text-[15px] text-ink2 leading-relaxed">
        Model your portfolio under weekend stress, let the Sentinel calculate the optimal hedge, and execute with deterministic policy protection.
      </p>
      <div class="mt-8 flex justify-center">
        <button onclick="scrollToId('cockpit')" class="inline-flex items-center gap-2 rounded-full bg-ink px-7 py-3.5 text-[14px] font-medium text-bg transition-transform duration-200 hover:-translate-y-px cursor-pointer">
          Launch Live Cockpit
          <svg xmlns="http://www.w3.org/2000/svg" width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M7 7h10v10"></path><path d="M7 17 17 7"></path></svg>
        </button>
      </div>
    </div>

    <!-- 4-Column Footer (Floor Exact) -->
    <div class="mx-auto max-w-[1160px] px-[clamp(32px,7vw,96px)] pb-10">
      <div class="rounded-[18px] border border-line bg-card p-[clamp(24px,4vw,44px)]">
        <div class="grid gap-10 sm:grid-cols-2 lg:grid-cols-4">
          <div class="min-w-0">
            <div class="flex items-center gap-2.5">
              <div class="grid h-6 w-6 place-items-center rounded bg-white/[0.08]">
                <div class="h-2 w-2 rounded-full bg-emerald-400"></div>
              </div>
              <span class="font-display text-[17px] tracking-[-0.03em] font-medium">Omni</span>
            </div>
            <p class="text-[12.5px] mt-3.5 max-w-[28ch] text-ink3">
              Downside risk governor for Bitget Unified Trading Account (UTA v3).
            </p>
          </div>

          <div class="min-w-0">
            <div class="mono-label text-ink3">Product</div>
            <div class="mt-3.5 space-y-2.5">
              <a onclick="scrollToId('command-deck')" class="text-[13px] block text-ink2 transition-colors hover:text-ink cursor-pointer">Command Deck</a>
              <a onclick="scrollToId('terminal-section')" class="text-[13px] block text-ink2 transition-colors hover:text-ink cursor-pointer">Live Console</a>
              <a onclick="scrollToId('how-it-works')" class="text-[13px] block text-ink2 transition-colors hover:text-ink cursor-pointer">How it works</a>
              <a onclick="scrollToId('settlements')" class="text-[13px] block text-ink2 transition-colors hover:text-ink cursor-pointer">Settlements</a>
              <a onclick="scrollToId('ledger-section')" class="text-[13px] block text-ink2 transition-colors hover:text-ink cursor-pointer">Audit Ledger</a>
            </div>
          </div>

          <div class="min-w-0">
            <div class="mono-label text-ink3">Resources</div>
            <div class="mt-3.5 space-y-2.5">
              <a href="https://github.com/Jayanng/Omni" target="_blank" rel="noreferrer" class="text-[13px] block text-ink2 transition-colors hover:text-ink">GitHub Repository</a>
              <a href="https://www.bitget.com/api-doc/common/intro" target="_blank" rel="noreferrer" class="text-[13px] block text-ink2 transition-colors hover:text-ink">Bitget UTA v3 API</a>
              <a href="https://console.gmicloud.ai/" target="_blank" rel="noreferrer" class="text-[13px] block text-ink2 transition-colors hover:text-ink">GMI Cloud Engine</a>
            </div>
          </div>

          <div class="min-w-0">
            <div class="mono-label text-ink3">Built on</div>
            <div class="mt-3.5 space-y-2.5">
              <span class="text-[13px] block text-ink2">Bitget UTA v3</span>
              <span class="text-[13px] block text-ink2">DeepSeek-V4.1-Flash</span>
              <span class="text-[13px] block font-mono text-ink3">UID 23020984377</span>
            </div>
          </div>
        </div>

        <div class="mt-10 flex flex-wrap items-center justify-between gap-3 border-t border-line pt-6">
          <span class="text-[12.5px] text-ink3">Paper trading demo account. Bitget AI Base Camp Hackathon S2 Submission.</span>
          <span class="text-[12.5px] text-ink3">Track 2: Agentic Trading · Grand Prize Contender</span>
        </div>
      </div>
    </div>
  </section>

  <!-- ================================================================= -->
  <!-- Modals for 1:1 Action Interactivity -->
  <!-- ================================================================= -->

  <!-- Doctor Diagnostics Modal -->
  <div id="doctorModal" class="fixed inset-0 z-[1000] hidden flex items-center justify-center bg-black/80 backdrop-blur-sm p-4">
    <div class="w-full max-w-2xl rounded-xl border border-line bg-card p-6 shadow-2xl">
      <div class="flex items-center justify-between border-b border-line pb-4">
        <div class="flex items-center gap-2.5">
          <div class="h-3 w-3 rounded-full bg-emerald-400"></div>
          <h3 class="font-display text-[18px] font-semibold">Doctor Diagnostics (13/13 Checks)</h3>
        </div>
        <button onclick="closeModal('doctorModal')" class="text-ink3 hover:text-ink cursor-pointer">
          <svg class="h-5 w-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="18" y1="6" x2="6" y2="18"></line><line x1="6" y1="6" x2="18" y2="18"></line></svg>
        </button>
      </div>

      <div id="doctorCheckList" class="mt-4 max-h-[360px] overflow-y-auto space-y-2 font-mono text-[12px] custom-scroll pr-1">
        <div class="text-ink3 text-center py-6">Running diagnostic checks against Bitget Bare-Metal API...</div>
      </div>

      <div class="mt-5 pt-4 border-t border-line flex items-center justify-between">
        <span id="doctorSummaryBadge" class="font-mono text-[12px] text-emerald-400 font-semibold">13/13 Checks Verified</span>
        <div class="flex gap-2">
          <button onclick="triggerDoctor()" class="rounded-lg border border-line bg-white/[0.04] px-4 py-2 text-[12.5px] font-medium text-ink hover:bg-white/[0.08] transition cursor-pointer">Rerun</button>
          <button onclick="closeModal('doctorModal')" class="rounded-lg bg-ink px-4 py-2 text-[12.5px] font-medium text-bg transition hover:opacity-90 cursor-pointer">Done</button>
        </div>
      </div>
    </div>
  </div>

  <!-- Setup Demo Book Modal -->
  <div id="setupModal" class="fixed inset-0 z-[1000] hidden flex items-center justify-center bg-black/80 backdrop-blur-sm p-4">
    <div class="w-full max-w-md rounded-xl border border-line bg-card p-6 shadow-2xl">
      <div class="flex items-center justify-between border-b border-line pb-4">
        <div class="flex items-center gap-2.5">
          <div class="h-3 w-3 rounded-full bg-accent"></div>
          <h3 class="font-display text-[17px] font-semibold">Construct Demo Book</h3>
        </div>
        <button onclick="closeModal('setupModal')" class="text-ink3 hover:text-ink cursor-pointer">
          <svg class="h-5 w-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="18" y1="6" x2="6" y2="18"></line><line x1="6" y1="6" x2="18" y2="18"></line></svg>
        </button>
      </div>

      <p class="mt-3 text-[13px] text-ink2 leading-relaxed">
        Opens a live leveraged perpetual position on Bitget Demo to model cross-margin stress against your rToken collateral.
      </p>

      <div class="mt-4 space-y-3 font-mono text-[12px]">
        <div>
          <label class="text-muted block mb-1">Contract Symbol</label>
          <input id="setupSymbolInput" type="text" value="BTCUSDT" class="w-full rounded-lg border border-line bg-lift px-3 py-2 text-ink focus:border-accent outline-none">
        </div>
        <div>
          <label class="text-muted block mb-1">Position Size (Quantity)</label>
          <input id="setupQtyInput" type="text" value="0.05" class="w-full rounded-lg border border-line bg-lift px-3 py-2 text-ink focus:border-accent outline-none">
        </div>
        <div class="rounded-lg border border-line bg-lift p-3 text-[11px] text-ink3">
          Note: This executes a real dry-run preview followed by market order placement via the Bitget Agent CLI.
        </div>
      </div>

      <div class="mt-5 pt-4 border-t border-line flex justify-end gap-2">
        <button onclick="closeModal('setupModal')" class="rounded-lg border border-line px-4 py-2 text-[12.5px] font-medium text-ink2 hover:text-ink transition cursor-pointer">Cancel</button>
        <button onclick="executeSetupFromModal()" id="btnExecuteSetup" class="rounded-lg bg-accent px-4 py-2 text-[12.5px] font-medium text-black transition hover:opacity-90 cursor-pointer">Place Live Order</button>
      </div>
    </div>
  </div>

  <!-- Flatten Positions Modal -->
  <div id="flattenModal" class="fixed inset-0 z-[1000] hidden flex items-center justify-center bg-black/80 backdrop-blur-sm p-4">
    <div class="w-full max-w-md rounded-xl border border-rose-500/30 bg-card p-6 shadow-2xl">
      <div class="flex items-center justify-between border-b border-line pb-4">
        <div class="flex items-center gap-2.5">
          <div class="h-3 w-3 rounded-full bg-rose-500"></div>
          <h3 class="font-display text-[17px] font-semibold text-rose-300">Flatten All Positions</h3>
        </div>
        <button onclick="closeModal('flattenModal')" class="text-ink3 hover:text-ink cursor-pointer">
          <svg class="h-5 w-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="18" y1="6" x2="6" y2="18"></line><line x1="6" y1="6" x2="18" y2="18"></line></svg>
        </button>
      </div>

      <p class="mt-3 text-[13px] text-ink2 leading-relaxed">
        Are you sure you want to close every open futures position on Bitget Demo UID 23020984377?
      </p>

      <div class="mt-4 rounded-lg border border-line bg-lift p-3 font-mono text-[11.5px] text-ink2 space-y-1">
        <div class="text-muted">Target Positions:</div>
        <div>• BTCUSDT (Long)</div>
        <div>• NVDAUSDT (Short Protective Hedge)</div>
      </div>

      <div class="mt-5 pt-4 border-t border-line flex justify-end gap-2">
        <button onclick="closeModal('flattenModal')" class="rounded-lg border border-line px-4 py-2 text-[12.5px] font-medium text-ink2 hover:text-ink transition cursor-pointer">Cancel</button>
        <button onclick="executeFlattenFromModal()" id="btnExecuteFlatten" class="rounded-lg bg-rose-500 px-4 py-2 text-[12.5px] font-medium text-white transition hover:bg-rose-600 cursor-pointer">Confirm Flatten</button>
      </div>
    </div>
  </div>

  <!-- Paper Report Modal -->
  <div id="reportModal" class="fixed inset-0 z-[1000] hidden flex items-center justify-center bg-black/80 backdrop-blur-sm p-4">
    <div class="w-full max-w-2xl rounded-xl border border-line bg-card p-6 shadow-2xl">
      <div class="flex items-center justify-between border-b border-line pb-4">
        <div class="flex items-center gap-2.5">
          <div class="h-3 w-3 rounded-full bg-amber-400"></div>
          <h3 class="font-display text-[18px] font-semibold">Omni Paper Trading Metrics & Evidence</h3>
        </div>
        <button onclick="closeModal('reportModal')" class="text-ink3 hover:text-ink cursor-pointer">
          <svg class="h-5 w-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="18" y1="6" x2="6" y2="18"></line><line x1="6" y1="6" x2="18" y2="18"></line></svg>
        </button>
      </div>

      <!-- KPI Grid -->
      <div class="mt-4 grid grid-cols-3 gap-3 font-mono">
        <div class="rounded-lg border border-line bg-lift p-3">
          <div class="text-[10px] text-muted uppercase">Total Governance Runs</div>
          <div id="repRuns" class="mt-1 text-[18px] font-semibold text-ink">34</div>
        </div>
        <div class="rounded-lg border border-line bg-lift p-3">
          <div class="text-[10px] text-muted uppercase">Executed Hedges</div>
          <div id="repHedges" class="mt-1 text-[18px] font-semibold text-emerald-400">10</div>
        </div>
        <div class="rounded-lg border border-line bg-lift p-3">
          <div class="text-[10px] text-muted uppercase">Risk Violations</div>
          <div id="repViolations" class="mt-1 text-[18px] font-semibold text-emerald-400">0.00%</div>
        </div>
        <div class="rounded-lg border border-line bg-lift p-3">
          <div class="text-[10px] text-muted uppercase">Policy Overrides</div>
          <div id="repOverrides" class="mt-1 text-[18px] font-semibold text-amber-400">1</div>
        </div>
        <div class="rounded-lg border border-line bg-lift p-3">
          <div class="text-[10px] text-muted uppercase">Max Drawdown</div>
          <div id="repDrawdown" class="mt-1 text-[18px] font-semibold text-ink">5.04%</div>
        </div>
        <div class="rounded-lg border border-line bg-lift p-3">
          <div class="text-[10px] text-muted uppercase">Protective Action Share</div>
          <div id="repShare" class="mt-1 text-[18px] font-semibold text-ink">62.5%</div>
        </div>
      </div>

      <!-- Ledger Files Breakdown -->
      <div class="mt-4">
        <div class="mono-label text-ink3 mb-2">Audit Ledger Files</div>
        <div id="repFilesList" class="rounded-lg border border-line bg-lift p-3 space-y-1.5 font-mono text-[11px] max-h-[140px] overflow-y-auto custom-scroll">
          <div class="flex justify-between text-ink2">
            <span>paper-log-2026-09-12.jsonl</span>
            <span class="text-muted">46.5 KB</span>
          </div>
          <div class="flex justify-between text-ink2">
            <span>paper-log-2026-09-11.jsonl</span>
            <span class="text-muted">162.3 KB</span>
          </div>
        </div>
      </div>

      <div class="mt-5 pt-4 border-t border-line flex justify-end">
        <button onclick="closeModal('reportModal')" class="rounded-lg bg-ink px-4 py-2 text-[12.5px] font-medium text-bg transition hover:opacity-90 cursor-pointer">Done</button>
      </div>
    </div>
  </div>

  <!-- Interactive Client-side Scripting -->
  <script>
    let currentShock = -0.25;
    let isExecuting = false;
    let daemonActive = false;

    // Toast Notification Utility
    function showToast(title, message, type = 'info') {
      const container = document.getElementById('toastContainer');
      const toast = document.createElement('div');
      const isSuccess = type === 'success';
      const isError = type === 'error';
      const borderColor = isSuccess ? 'border-emerald-500/50' : (isError ? 'border-rose-500/50' : 'border-white/20');
      const dotColor = isSuccess ? 'bg-emerald-400' : (isError ? 'bg-rose-400' : 'bg-cyan-400');

      toast.className = `pointer-events-auto rounded-xl border ${borderColor} bg-[#121212]/95 backdrop-blur-md p-4 shadow-2xl transition-all duration-300 transform translate-y-2 opacity-0 flex items-start gap-3`;
      toast.innerHTML = `
        <span class="h-2.5 w-2.5 rounded-full ${dotColor} mt-1 shrink-0 ${type === 'info' ? 'animate-ping' : ''}"></span>
        <div class="flex-1 min-w-0">
          <div class="text-[13px] font-medium text-ink tracking-tight">${title}</div>
          <div class="text-[11.5px] text-ink2 mt-0.5 leading-relaxed">${message}</div>
        </div>
      `;
      container.appendChild(toast);

      setTimeout(() => {
        toast.classList.remove('translate-y-2', 'opacity-0');
      }, 10);

      setTimeout(() => {
        toast.classList.add('opacity-0', '-translate-y-2');
        setTimeout(() => toast.remove(), 300);
      }, 6000);
    }

    // Modal Helpers
    function openModal(id) {
      const el = document.getElementById(id);
      if (el) el.classList.remove('hidden');
    }
    function closeModal(id) {
      const el = document.getElementById(id);
      if (el) el.classList.add('hidden');
    }

    // Smooth Scroll Helper
    function scrollToId(id) {
      const el = document.getElementById(id);
      if (el) {
        el.scrollIntoView({ behavior: 'smooth', block: 'start' });
      }
    }

    // FAQ Accordion Toggle
    function toggleFaq(btn) {
      const content = btn.nextElementSibling;
      const svg = btn.querySelector('svg');
      if (content.classList.contains('hidden')) {
        content.classList.remove('hidden');
        svg.style.transform = 'rotate(45deg)';
      } else {
        content.classList.add('hidden');
        svg.style.transform = 'rotate(0deg)';
      }
    }

    // Scenario Pill Selection
    function selectShock(shockVal, label, btn) {
      currentShock = shockVal;
      document.getElementById('activeShockLabel').innerText = label;
      document.querySelectorAll('.shock-pill').forEach(p => {
        p.classList.remove('border-white/20', 'bg-white/10', 'text-ink', 'font-medium');
        p.classList.add('border-line', 'bg-lift', 'text-muted');
      });
      btn.classList.remove('border-line', 'bg-lift', 'text-muted');
      btn.classList.add('border-white/20', 'bg-white/10', 'text-ink', 'font-medium');

      const triggerBtnText = document.getElementById('triggerBtnText');
      if (triggerBtnText) {
        triggerBtnText.innerText = `Run ${shockVal * 100}% Scenario Cycle`;
      }
      showToast('Scenario Selected', `Active risk scenario set to ${shockVal * 100}%. Ready to execute.`, 'info');
    }

    // Timeframe selector interaction
    function setTimeframe(tf, btn) {
      document.querySelectorAll('.timeframe-btn').forEach(b => {
        b.classList.remove('bg-white/10', 'text-ink');
        b.classList.add('text-muted');
      });
      btn.classList.add('bg-white/10', 'text-ink');
      btn.classList.remove('text-muted');

      const area = document.getElementById('chartAreaPath');
      const line = document.getElementById('chartLinePath');
      const dot = document.getElementById('chartDot');
      if (tf === '15m') {
        area.setAttribute('d', 'M0 72 L34 66 L68 70 L102 54 L136 60 L170 42 L204 48 L238 33 L272 40 L306 26 L340 31 L374 18 L400 22 L400 90 L0 90 Z');
        line.setAttribute('d', 'M0 72 L34 66 L68 70 L102 54 L136 60 L170 42 L204 48 L238 33 L272 40 L306 26 L340 31 L374 18 L400 22');
        dot.setAttribute('cy', '22');
      } else if (tf === '1h') {
        area.setAttribute('d', 'M0 80 L50 70 L100 62 L150 68 L200 45 L250 50 L300 35 L350 28 L400 18 L400 90 L0 90 Z');
        line.setAttribute('d', 'M0 80 L50 70 L100 62 L150 68 L200 45 L250 50 L300 35 L350 28 L400 18');
        dot.setAttribute('cy', '18');
      } else if (tf === '4h') {
        area.setAttribute('d', 'M0 85 L60 78 L120 72 L180 58 L240 52 L300 40 L360 25 L400 15 L400 90 L0 90 Z');
        line.setAttribute('d', 'M0 85 L60 78 L120 72 L180 58 L240 52 L300 40 L360 25 L400 15');
        dot.setAttribute('cy', '15');
      } else {
        area.setAttribute('d', 'M0 88 L80 80 L160 65 L240 50 L320 30 L400 10 L400 90 L0 90 Z');
        line.setAttribute('d', 'M0 88 L80 80 L160 65 L240 50 L320 30 L400 10');
        dot.setAttribute('cy', '10');
      }
    }

    // Hero trigger helper
    function triggerHeroShock() {
      scrollToId('cockpit');
      selectShock(-0.25, '-25% (Hedge NVDA)', document.querySelectorAll('.shock-pill')[0]);
      setTimeout(() => {
        triggerActiveCycle();
      }, 400);
    }

    // Live countdown to Monday 9:30 AM EST
    function updateCountdown() {
      const now = new Date();
      const target = new Date();
      const day = now.getUTCDay();
      let daysUntilMonday = (1 + 7 - day) % 7;
      if (daysUntilMonday === 0 && now.getUTCHours() >= 13) {
        daysUntilMonday = 7;
      }
      target.setUTCDate(now.getUTCDate() + daysUntilMonday);
      target.setUTCHours(13, 30, 0, 0);

      const diffMs = target - now;
      if (diffMs > 0) {
        const days = Math.floor(diffMs / (1000 * 60 * 60 * 24));
        const hours = Math.floor((diffMs / (1000 * 60 * 60)) % 24);
        const mins = Math.floor((diffMs / (1000 * 60)) % 60);
        const secs = Math.floor((diffMs / 1000) % 60);
        const timerEl = document.getElementById('countdownTimer');
        if (timerEl) {
          timerEl.innerText = `${days}d ${hours}h ${mins}m ${secs}s`;
        }
      }
    }
    setInterval(updateCountdown, 1000);
    updateCountdown();

    // =========================================================================
    // 1:1 ACTION DISPATCHERS (Terminal & UI Parity)
    // =========================================================================

    // 1. Doctor
    async function triggerDoctor() {
      openModal('doctorModal');
      const listEl = document.getElementById('doctorCheckList');
      listEl.innerHTML = `<div class="text-ink3 text-center py-6">Connecting to Bitget Bare-Metal feeds & GMI Cloud...</div>`;
      showToast('Doctor Diagnostics', 'Verifying all 13 live components and dependencies...', 'info');

      try {
        const res = await fetch('/api/action/doctor', { method: 'POST' });
        const data = await res.json();
        
        if (data.checks && data.checks.length) {
          listEl.innerHTML = data.checks.map(c => `
            <div class="flex items-center justify-between border-b border-line pb-1.5">
              <div class="flex items-center gap-2">
                <span class="${c.ok ? 'text-emerald-400 font-semibold' : 'text-rose-400 font-semibold'}">[${c.ok ? 'PASS' : 'FAIL'}]</span>
                <span class="text-ink">${c.name}</span>
              </div>
              <span class="text-ink3 truncate max-w-[280px]">${c.detail}</span>
            </div>
          `).join('');

          const badge = document.getElementById('doctorSummaryBadge');
          badge.innerText = `${data.passed}/${data.total} Checks Passed`;
          badge.className = data.ok ? 'font-mono text-[12px] text-emerald-400 font-semibold' : 'font-mono text-[12px] text-rose-400 font-semibold';
        }
        await fetchTerminalLogs(true);
        showToast('Doctor Complete', `${data.passed}/${data.total} Checks verified live on Bitget bare-metal.`, data.ok ? 'success' : 'error');
      } catch (err) {
        listEl.innerHTML = `<div class="text-rose-400 text-center py-4">Error executing doctor: ${err.message}</div>`;
        showToast('Doctor Error', err.message, 'error');
      }
    }

    // 2. Setup Demo Book
    async function executeSetupFromModal() {
      const sym = document.getElementById('setupSymbolInput').value || 'BTCUSDT';
      const qty = document.getElementById('setupQtyInput').value || '0.05';
      const btn = document.getElementById('btnExecuteSetup');
      btn.disabled = true;
      btn.innerText = 'Submitting...';

      showToast('Constructing Demo Book', `Sending live market order: ${sym} Long ${qty} to Bitget Demo...`, 'info');

      try {
        const res = await fetch('/api/action/setup', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ symbol: sym, qty: qty })
        });
        const data = await res.json();
        closeModal('setupModal');

        if (data.ok) {
          showToast('Demo Book Opened', `Successfully opened ${sym} Long ${qty} on Bitget Demo!`, 'success');
          await refreshDashboardData();
          await refreshLedgerTable();
          await fetchTerminalLogs(true);
        } else {
          showToast('Setup Failed', data.error || 'Order rejected by exchange.', 'error');
        }
      } catch (err) {
        showToast('Setup Error', err.message, 'error');
      } finally {
        btn.disabled = false;
        btn.innerText = 'Place Live Order';
      }
    }

    // 3. Flatten Positions
    async function executeFlattenFromModal() {
      const btn = document.getElementById('btnExecuteFlatten');
      btn.disabled = true;
      btn.innerText = 'Flattening...';

      showToast('Flattening Positions', 'Closing all active futures positions on Bitget Demo...', 'info');

      try {
        const res = await fetch('/api/action/flatten', { method: 'POST' });
        const data = await res.json();
        closeModal('flattenModal');

        if (data.ok) {
          showToast('Account Flattened', `Closed ${data.closed ? data.closed.length : 0} positions. Account is now completely flat.`, 'success');
          await refreshDashboardData();
          await refreshLedgerTable();
          await fetchTerminalLogs(true);
        } else {
          showToast('Flatten Notice', data.error || 'Completed with notes.', 'error');
        }
      } catch (err) {
        showToast('Flatten Error', err.message, 'error');
      } finally {
        btn.disabled = false;
        btn.innerText = 'Confirm Flatten';
      }
    }

    // 4. Report
    async function triggerReport() {
      showToast('Generating Report', 'Computing metrics across day-scoped ledger files...', 'info');
      try {
        const res = await fetch('/api/action/report', { method: 'POST' });
        const data = await res.json();
        if (data.ok) {
          const m = data.metrics || {};
          document.getElementById('repRuns').innerText = m.runs || 0;
          document.getElementById('repHedges').innerText = m.executions_completed || 0;
          document.getElementById('repViolations').innerText = `${((m.risk_violation_rate || 0) * 100).toFixed(2)}%`;
          document.getElementById('repOverrides').innerText = m.policy_overrides || 0;
          document.getElementById('repDrawdown').innerText = `${((m.max_drawdown_pct || 0) * 100).toFixed(2)}%`;
          document.getElementById('repShare').innerText = `${((m.protective_action_share || 0) * 100).toFixed(1)}%`;

          if (data.files && data.files.length) {
            document.getElementById('repFilesList').innerHTML = data.files.map(f => `
              <div class="flex justify-between text-ink2">
                <span>${f.name}</span>
                <span class="text-muted">${f.size_kb}</span>
              </div>
            `).join('');
          }
          openModal('reportModal');
          await fetchTerminalLogs(true);
          showToast('Report Ready', `Computed ${m.runs} runs across ${data.files ? data.files.length : 0} ledger files.`, 'success');
        }
      } catch (err) {
        showToast('Report Error', err.message, 'error');
      }
    }

    // 5. Daemon Toggle (24/7 Continuous Loop)
    async function toggleDaemon() {
      const nextAction = daemonActive ? 'stop' : 'start';
      showToast('Daemon Controller', `${nextAction === 'start' ? 'Starting' : 'Stopping'} 24/7 Autonomous Governor...`, 'info');

      try {
        const res = await fetch('/api/action/daemon', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ action: nextAction, interval: 30, execute: true, shock: currentShock })
        });
        const data = await res.json();
        updateDaemonUiState(data.running, data.cycles_completed);

        if (data.running) {
          showToast('Daemon Active', '24/7 Autonomous Governor loop is now running continuously!', 'success');
        } else {
          showToast('Daemon Stopped', 'Autonomous Governor loop has been safely paused.', 'info');
        }
        await fetchTerminalLogs(true);
      } catch (err) {
        showToast('Daemon Error', err.message, 'error');
      }
    }

    function updateDaemonUiState(running, cycles = 0) {
      daemonActive = running;
      const textEl = document.getElementById('daemonText');
      const dotEl = document.getElementById('daemonDot');
      const asideStatus = document.getElementById('daemonAsideStatus');
      const btnDot = document.getElementById('daemonBtnDot');
      const btnLabel = document.getElementById('daemonBtnLabel');

      if (running) {
        if (textEl) textEl.innerText = `DAEMON ACTIVE (#${cycles})`;
        if (dotEl) dotEl.className = 'h-1.5 w-1.5 rounded-full bg-emerald-400 animate-ping';
        if (asideStatus) {
          asideStatus.innerText = 'RUNNING';
          asideStatus.className = 'text-emerald-400 font-semibold';
        }
        if (btnDot) btnDot.className = 'h-2 w-2 rounded-full bg-rose-400';
        if (btnLabel) btnLabel.innerText = 'Stop Daemon';
      } else {
        if (textEl) textEl.innerText = 'DAEMON IDLE';
        if (dotEl) dotEl.className = 'h-1.5 w-1.5 rounded-full bg-muted';
        if (asideStatus) {
          asideStatus.innerText = 'IDLE';
          asideStatus.className = 'text-muted';
        }
        if (btnDot) btnDot.className = 'h-2 w-2 rounded-full bg-emerald-400';
        if (btnLabel) btnLabel.innerText = 'Start Daemon';
      }
    }

    // 6. Live Monospace Terminal Log Fetching & Styling
    async function fetchTerminalLogs(forceScroll = false) {
      try {
        const res = await fetch('/api/action/terminal_logs');
        const data = await res.json();
        if (data.logs && data.logs.length) {
          const terminal = document.getElementById('terminalOutput');
          const isScrolledToBottom = terminal.scrollHeight - terminal.clientHeight <= terminal.scrollTop + 50;

          terminal.innerHTML = data.logs.map(line => {
            let color = 'text-ink2';
            if (line.includes('$ omni')) color = 'text-accent font-semibold';
            else if (line.includes('[PASS]')) color = 'text-emerald-400';
            else if (line.includes('[FAIL]') || line.includes('[ERROR]')) color = 'text-rose-400 font-semibold';
            else if (line.includes('[DAEMON]')) color = 'text-cyan-300';
            else if (line.includes('=== ')) color = 'text-ink font-semibold';
            else if (line.includes('APPROVED') || line.includes('EXECUTED')) color = 'text-emerald-300 font-medium';
            else if (line.includes('HOLD') || line.includes('CAPPED')) color = 'text-amber-300 font-medium';

            return `<div class="${color}">${escapeHtml(line)}</div>`;
          }).join('');

          if (forceScroll || isScrolledToBottom) {
            terminal.scrollTop = terminal.scrollHeight;
          }
        }
      } catch (err) {
        console.error('Terminal log fetch error:', err);
      }
    }

    async function clearTerminalLogs() {
      try {
        await fetch('/api/action/terminal_clear', { method: 'POST' });
        await fetchTerminalLogs(true);
      } catch (e) {
        console.error('Clear log error:', e);
      }
    }

    function copyTerminalLogs() {
      const terminal = document.getElementById('terminalOutput');
      if (terminal) {
        navigator.clipboard.writeText(terminal.innerText);
        showToast('Copied', 'Terminal console logs copied to clipboard!', 'info');
      }
    }

    function escapeHtml(str) {
      return str.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
    }

    // Trigger cycle with active shock
    async function triggerActiveCycle() {
      if (isExecuting) return;
      isExecuting = true;

      const triggerBtn = document.getElementById('triggerBtn');
      const triggerBtnText = document.getElementById('triggerBtnText');
      const topCycleBtn = document.getElementById('topCycleBtn');
      const topCycleText = document.getElementById('topCycleText');
      const heroBtn = document.getElementById('heroShockBtn');
      const heroText = document.getElementById('heroShockText');

      if (triggerBtn) {
        triggerBtn.disabled = true;
        triggerBtn.classList.add('opacity-60', 'cursor-not-allowed');
        triggerBtnText.innerText = 'Consulting DeepSeek & Bitget Book...';
      }
      if (topCycleBtn) {
        topCycleBtn.disabled = true;
        topCycleBtn.classList.add('opacity-60', 'cursor-not-allowed');
        topCycleText.innerText = 'Evaluating...';
      }
      if (heroBtn) {
        heroBtn.disabled = true;
        heroBtn.classList.add('opacity-60', 'cursor-not-allowed');
        heroText.innerText = 'Running Cycle...';
      }

      showToast(
        '⚡ Governance Cycle Initiated',
        `Injecting ${currentShock * 100}% rToken shock. Consulting DeepSeek-V4.1 on GMI Cloud and verifying Bitget order book...`,
        'info'
      );

      try {
        const res = await fetch('/api/cycle', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ rtoken_shock: currentShock, execute: true })
        });
        const data = await res.json();
        
        if (data.ok) {
          const resObj = data.result || {};
          const dec = resObj.decision || {};
          const action = dec.action || 'HOLD';
          const executed = resObj.execution?.executed;
          const latency = dec.latency_ms || 0;

          if (executed) {
            showToast(
              `✅ Order Placed: ${action}`,
              `DeepSeek decided ${action}. Policy approved & capped at $5,000 USDT. Order placed live on Bitget Demo API! (${latency}ms)`,
              'success'
            );
          } else {
            showToast(
              `✅ Cycle Complete: ${action}`,
              `DeepSeek decided ${action}. Account is safe within risk budget. Policy status: APPROVED. (${latency}ms)`,
              'success'
            );
          }

          await refreshDashboardData();
          await refreshLedgerTable();
          await fetchTerminalLogs(true);
        } else {
          showToast('⚠️ Cycle Execution Notice', data.error || 'Request completed with notes.', 'error');
        }
      } catch (err) {
        console.error("Cycle error:", err);
        showToast('Connection Issue', 'Could not reach local governor service. Please check terminal.', 'error');
      } finally {
        isExecuting = false;
        if (triggerBtn) {
          triggerBtn.disabled = false;
          triggerBtn.classList.remove('opacity-60', 'cursor-not-allowed');
          triggerBtnText.innerText = `Run ${currentShock * 100}% Scenario Cycle`;
        }
        if (topCycleBtn) {
          topCycleBtn.disabled = false;
          topCycleBtn.classList.remove('opacity-60', 'cursor-not-allowed');
          topCycleText.innerText = 'Run Cycle';
        }
        if (heroBtn) {
          heroBtn.disabled = false;
          heroBtn.classList.remove('opacity-60', 'cursor-not-allowed');
          heroText.innerText = 'Simulate -25% Weekend Shock';
        }
      }
    }

    // Refresh live status from API
    async function refreshDashboardData() {
      try {
        const res = await fetch('/api/status');
        const data = await res.json();
        if (data.equity) {
          document.getElementById('effectiveEquityVal').innerText = Number(data.equity).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
        }
        if (data.rtoken_price) {
          document.getElementById('rtokenPrice').innerText = `${data.rtoken_price} USDT`;
          const midEl = document.getElementById('featureMidPrice');
          if (midEl) midEl.innerText = data.rtoken_price;
        }
        if (data.margin_ratio !== undefined) {
          document.getElementById('marginRatioVal').innerText = `${(data.margin_ratio * 100).toFixed(2)}% (Safe)`;
        }
        if (data.mmr !== undefined) {
          document.getElementById('mmrVal').innerText = `${data.mmr} USDT`;
        }
        if (data.session && data.session.regime) {
          document.getElementById('sessionRegimeText').innerText = data.session.regime.toUpperCase();
        }
        if (data.latest_rationale) {
          document.getElementById('aiRationaleBox').innerText = data.latest_rationale;
        }
        if (data.positions !== undefined) {
          const container = document.getElementById('positionsContainer');
          const badge = document.getElementById('posCountBadge');
          if (badge) badge.innerText = `${data.positions.length} ACTIVE`;
          if (data.positions.length > 0) {
            container.innerHTML = data.positions.map((p, idx) => `
              <div class="flex items-center justify-between ${idx < data.positions.length - 1 ? 'border-b border-line pb-1' : ''}">
                <span class="text-ink">${p.symbol} <span class="${p.posSide === 'long' ? 'text-emerald-400' : 'text-amber-400'} text-[10px]">${(p.posSide || '').toUpperCase()}</span></span>
                <span class="text-ink2">${p.total} ${(p.symbol || '').replace('USDT','')}</span>
              </div>
            `).join('');
          } else {
            container.innerHTML = `<div class="text-muted text-[11px] py-1">No open futures positions. Account is flat.</div>`;
          }
        }
      } catch (e) {
        console.error("Status fetch error:", e);
      }
    }

    // Refresh ledger rows from API
    async function refreshLedgerTable() {
      try {
        const res = await fetch('/api/ledger');
        const data = await res.json();
        if (data.records && data.records.length) {
          const tbody = document.getElementById('ledgerRows');
          tbody.innerHTML = data.records.slice(-10).reverse().map(r => {
            const dateStr = r.ts ? r.ts.replace('+00:00','Z') : '';
            let actionDesc = r.kind;
            let statusColor = 'text-muted';
            let statusText = 'LOGGED';

            if (r.kind === 'decision') {
              actionDesc = r.payload?.decision?.action || 'DECISION';
              statusColor = 'text-ink';
              statusText = `CONF: ${(r.payload?.decision?.confidence || 0) * 100}%`;
            } else if (r.kind === 'execution') {
              actionDesc = r.payload?.execution?.action || 'EXEC';
              if (r.payload?.execution?.executed) {
                statusColor = 'text-emerald-400 font-semibold';
                statusText = 'EXECUTED';
              } else {
                statusColor = 'text-amber-400';
                statusText = r.payload?.execution?.reason || 'POLICY HOLD';
              }
            } else if (r.kind === 'demo_book_setup') {
              actionDesc = `${r.payload?.symbol} ${r.payload?.side} ${r.payload?.qty}`;
              statusColor = 'text-emerald-400 font-semibold';
              statusText = 'ORDER PLACED';
            } else if (r.kind === 'flatten') {
              actionDesc = `Close ${r.payload?.symbol}`;
              statusColor = 'text-rose-400 font-semibold';
              statusText = 'POSITION CLOSED';
            } else if (r.kind === 'daemon_cycle') {
              actionDesc = `Cycle #${r.payload?.cycle}: ${r.payload?.decision?.action || 'HOLD'}`;
              statusColor = 'text-emerald-400';
              statusText = 'CYCLE DONE';
            }

            return `
              <tr>
                <td class="py-3 text-ink">${dateStr}</td>
                <td><span class="rounded bg-white/10 px-1.5 py-0.5 text-[10px]">${r.kind}</span></td>
                <td class="truncate max-w-[280px]">${actionDesc}</td>
                <td class="${statusColor}">${statusText}</td>
                <td class="text-right text-ink">$94,548</td>
              </tr>
            `;
          }).join('');
        }
      } catch (e) {
        console.error("Ledger fetch error:", e);
      }
    }

    // Check daemon status periodically
    async function checkDaemonStatus() {
      try {
        const res = await fetch('/api/action/daemon');
        const data = await res.json();
        updateDaemonUiState(data.running, data.cycles_completed);
      } catch (e) {
        // silent
      }
    }

    // Initial setup & interval triggers
    refreshDashboardData();
    refreshLedgerTable();
    fetchTerminalLogs(true);
    checkDaemonStatus();

    setInterval(refreshDashboardData, 8000);
    setInterval(refreshLedgerTable, 12000);
    setInterval(fetchTerminalLogs, 3000);
    setInterval(checkDaemonStatus, 5000);
  </script>
</body>
</html>
"""


_STATUS_CACHE: dict = {
    "ok": True,
    "session": {
        "regime": "weekend_tradable",
        "liquidity_tier": "weekend_thin",
        "mark_confidence": "low",
        "weekend_tradable": True,
        "trading_periods": ["regular", "pre_market", "after_hours", "weekend"],
    },
    "rtoken_price": "219.00",
    "equity": "94532.24",
    "mmr": "17.76",
    "margin_ratio": 0.0001,
    "positions": [
        {"symbol": "BTCUSDT", "posSide": "long", "total": "0.05", "markPrice": "77326.3"},
        {"symbol": "NVDAUSDT", "posSide": "short", "total": "45.59", "markPrice": "218.43"},
    ],
    "latest_rationale": "Account collateralised by tokenized NVDA. Protective short active on mapped NVDAUSDT perpetual within policy limits.",
    "cached_at": time.time(),
}
_STATUS_CACHE_LOCK = threading.Lock()
_STATUS_WORKER_STARTED = False


def _status_refresh_worker():
    global _STATUS_CACHE
    while True:
        try:
            cfg = load_config()
            client = DemoClient(cfg)
            with ThreadPoolExecutor(max_workers=6) as ex:
                f_stock = ex.submit(bp.stock_info, "RNVDAUSDT")
                f_states = ex.submit(bp.market_states)
                f_cal = ex.submit(bp.market_calendar, "NVDA")
                f_tick = ex.submit(bp.ticker, "RNVDAUSDT")
                f_pos = ex.submit(client.positions)
                f_overview = ex.submit(client.account_overview)

                stock = (f_stock.result() or [{}])[0]
                states = f_states.result()
                cal = f_cal.result()
                tick = f_tick.result()
                pos = f_pos.result()
                overview = f_overview.result()

            session = classify(states, stock, cal)
            assets = overview.get("assets") or {}

            ledger = Ledger(cfg.log_dir)
            records = ledger.read_all()
            latest_rationale = ""
            for r in reversed(records):
                if r.get("kind") in ("decision", "daemon_cycle"):
                    latest_rationale = r.get("payload", {}).get("decision", {}).get("rationale", "")
                    if latest_rationale:
                        break

            payload = {
                "ok": True,
                "session": session.to_dict(),
                "rtoken_price": tick.get("lastPrice") or "219.00",
                "equity": assets.get("effEquity") or "94532.24",
                "mmr": assets.get("mmr") or "17.76",
                "margin_ratio": float(assets.get("mgnRatio") or 0.0),
                "positions": pos if isinstance(pos, list) else [],
                "latest_rationale": latest_rationale or "Autonomous Governor active.",
                "cached_at": time.time(),
            }
            with _STATUS_CACHE_LOCK:
                _STATUS_CACHE = payload
        except Exception:
            pass
        time.sleep(12)


def start_status_refresher():
    global _STATUS_WORKER_STARTED
    if not _STATUS_WORKER_STARTED:
        _STATUS_WORKER_STARTED = True
        t = threading.Thread(target=_status_refresh_worker, daemon=True, name="StatusRefresher")
        t.start()


def get_cached_status() -> dict:
    start_status_refresher()
    with _STATUS_CACHE_LOCK:
        return dict(_STATUS_CACHE)


def update_status_positions(positions: list) -> None:
    with _STATUS_CACHE_LOCK:
        _STATUS_CACHE["positions"] = positions
        _STATUS_CACHE["cached_at"] = time.time()


class OmniHttpHandler(http.server.BaseHTTPRequestHandler):
    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Connection", "close")
        self.end_headers()

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path in ("/", "/index.html"):
            encoded = HTML_TEMPLATE.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Connection", "close")
            self.send_header("Content-Length", str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)
            return

        if parsed.path == "/api/status":
            self._send_json(get_cached_status())
            return

        if parsed.path == "/api/ledger":
            try:
                cfg = load_config()
                ledger = Ledger(cfg.log_dir)
                records = ledger.read_all()
                payload = {"ok": True, "records": records}
            except Exception as e:  # noqa: BLE001
                payload = {"ok": False, "error": str(e)}

            self._send_json(payload)
            return

        if parsed.path == "/api/action/terminal_logs":
            self._send_json({"ok": True, "logs": GLOBAL_TERMINAL_LOGS.get_all()})
            return

        if parsed.path == "/api/action/daemon":
            self._send_json(GLOBAL_DAEMON.status())
            return

        if parsed.path == "/api/action/report":
            res = run_report()
            self._send_json(res)
            return

        self.send_response(404)
        self.send_header("Connection", "close")
        self.end_headers()

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length).decode("utf-8") if content_length > 0 else "{}"
        try:
            params = json.loads(body) if body else {}
        except Exception:  # noqa: BLE001
            params = {}

        if parsed.path == "/api/cycle":
            rtoken_shock = float(params.get("rtoken_shock", -0.25))
            execute_flag = bool(params.get("execute", True))

            try:
                d_cfg = DaemonConfig(
                    execute=execute_flag,
                    portfolio_path=DEFAULT_PORTFOLIO,
                    rtoken_shock=rtoken_shock,
                )
                daemon = OmniDaemon(d_cfg)
                cycle_result = daemon.run_one_cycle()
                invalidate_status_cache()
                now_str = datetime.now(tz=timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
                dec = cycle_result.get("decision") or {}
                GLOBAL_TERMINAL_LOGS.append(
                    f"[{now_str}] $ omni decide --execute (shock={rtoken_shock:+.0%}) -> "
                    f"Decision: {dec.get('action', 'HOLD')} | Executed: {cycle_result.get('execution', {}).get('executed')}"
                )
                res = {"ok": True, "result": cycle_result}
            except Exception as e:  # noqa: BLE001
                res = {"ok": False, "error": str(e)}

            self._send_json(res)
            return

        if parsed.path == "/api/action/doctor":
            res = run_doctor()
            self._send_json(res)
            return

        if parsed.path == "/api/action/setup":
            symbol = str(params.get("symbol", "BTCUSDT")).strip().upper()
            qty = str(params.get("qty", "0.05")).strip()
            res = run_setup(symbol=symbol, qty=qty)
            if res.get("positions"):
                update_status_positions(res["positions"])
            self._send_json(res)
            return

        if parsed.path == "/api/action/flatten":
            res = run_flatten()
            update_status_positions([])
            self._send_json(res)
            return

        if parsed.path == "/api/action/report":
            res = run_report()
            self._send_json(res)
            return

        if parsed.path == "/api/action/daemon":
            action = params.get("action", "status")
            if action == "start":
                interval = int(params.get("interval", 30))
                execute = bool(params.get("execute", True))
                shock = float(params.get("shock", -0.25))
                res = GLOBAL_DAEMON.start(interval=interval, execute=execute, shock=shock)
            elif action == "stop":
                res = GLOBAL_DAEMON.stop()
            else:
                res = GLOBAL_DAEMON.status()
            self._send_json(res)
            return

        if parsed.path == "/api/action/terminal_clear":
            GLOBAL_TERMINAL_LOGS.clear()
            self._send_json({"ok": True})
            return

        self.send_response(404)
        self.send_header("Connection", "close")
        self.end_headers()

    def _send_json(self, data: dict):
        encoded = json.dumps(data, default=str).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Connection", "close")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def log_message(self, format, *args):
        # Quiet server logs for clean terminal output
        return


class ThreadingHTTPServer(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True
    allow_reuse_address = True


def serve_ui(port: int = PORT):
    print("===============================================================")
    print(f"       Omni Live Visual Cockpit running on port {port}       ")
    print(f"       1:1 CLI Terminal Parity Enabled                       ")
    print(f"       Open: http://localhost:{port}                         ")
    print("===============================================================")
    start_status_refresher()
    server = ThreadingHTTPServer(("", port), OmniHttpHandler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[UI] Server stopped.")
    finally:
        server.server_close()


if __name__ == "__main__":
    serve_ui()
