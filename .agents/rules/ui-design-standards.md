# StockAI UI & Mobile Design Standards (Persistent Workspace Memory)

These design standards are mandatory across every new page, modal, table, card, and component in `frontend/` unless the user explicitly asks for modifications.

## 1. Visual Language & Anti-Bloat Discipline

- **Clean Institutional FinTech Aesthetic**: Crisp slate/charcoal surfaces (`--color-bg-primary`, `--color-bg-secondary`, `--color-bg-card`, `--color-bg-tertiary`), hairline `1px` borders (`--color-border`, `--color-border-light`), and tabular monospace numbers (`--font-mono`) for all prices, percentages, and P&L values (`--color-bullish`, `--color-bearish`, `--color-neutral`, `--color-pnl-zero`).
- **Zero Emoji & AI-Bloat Rule**:
  - Do NOT use decorative Unicode emojis (🚀, ⚡, 🔥, 🎯, 📊, 🌐, 🛡️, etc.) in headings, buttons, filter pills, status badges, or tabs. Use crisp **Lucide icons** (`lucide-react`) sized `14px–18px` with `1.75–2px` stroke width.
  - Do NOT clutter labels with verbose parenthetical explanations (`(100+ Stocks)`, `(Before Buy Price)`, `(Optimal Entry)`) or decorative gradient/neon gimmick banners. Keep labels concise and trader-focused (`All Sectors`, `Pre-Buy`, `At Best Buy`, `Holdings`, `Orders`, `F&O`).
  - Do NOT expose internal engineering jargon (e.g., `single-flight`, `semaphore`, `rate governor`, `buffer`, `Celery beat`, `fallback`) in end-user UI copy; reserve diagnostics strictly for **Admin Control -> Sentinel / Threats & Logs**.
  - Never display uncleaned Markdown (`**bold**`, `###`, escaped strings) inside UI text; sanitize with `cleanBriefMarkdown` and format timestamps consistently with `formatISTTimestamp` (`utils/formatters.ts`).
- **Theme Token Parity**:
  - Always reference theme CSS variables (`--color-bg-primary`, `--color-bg-card`, `--color-bg-tertiary`, `--color-border`, `--color-text-primary`, `--color-text-secondary`, `--color-text-muted`, `--color-accent-blue`, and compatibility aliases `--bg-color`, `--surface-color`, `--border-color`, `--text-color`, `--text-secondary`) so Dark and Light themes remain legible with high contrast.
  - Use global button classes (`.btn`, `.btn-primary`, `.btn-secondary`, `.btn-danger`, `.button`, `.button-outline`) cleanly; never invent missing CSS variables like `--bg-secondary`.
- **Currency & Locale Rules**:
  - Use **INR (`₹`) exclusively** for equity pricing, paper trading, portfolio values, and subscription plans (`₹0`, `₹2,499`).
  - Never prefix benchmark index points (`NIFTY 50`, `SENSEX`, `BANK NIFTY`, `INDIA VIX`) with `₹`.

## 2. Navigation, Notifications & URL Privacy

- **Primary NavBar Hierarchy (`NavBar.tsx`)**:
  - Keep desktop primary links concise (`Dashboard`, `Screener`, `Orders`, `Holdings`, `Charts`, `F&O`, `Alerts`) plus a clean `Tools` dropdown (`Scanner`, `SMC Zones`, `Heatmap`, `Backtest`), right-aligned `Inbox` (`<NotificationBell />` with unseen red count badge + sound toggle), `Settings`, and Admin-only `Admin` link.
  - Preserve `<NotificationBell />` real-time unread count badge, unseen tab dots/badges, browser notification sound, and mark-as-seen behavior.
- **No Exposed Query State & Predictable Auth Redirects**:
  - Never leak internal UI navigation state into URL query parameters (`?tab=`, `?redirect=`). Pass sub-tab selections internally via React Router `location.state` and keep browser URLs clean (`/dashboard`, `/alerts`, `/paper-trading`, `/admin`).
  - Never return a newly logged-in or switched-account user to a stale `?redirect=` URL (especially `/admin` or another user's route). Every fresh login, OTP login, or Google Sign-In must land cleanly on `/dashboard`.
- **Strict Role Separation**:
  - Non-admin users must never see Admin links, system-wide Algo Configuration (`SettingsPage`), Cycle Rollover / Global Sync triggers (`SwingScreenerPage`), or Sentinel controls; protected `/admin*` routes redirect non-admins cleanly to `/dashboard`.

## 3. Responsive & Mobile-First Layout Invariants

- **Zero Horizontal Overflow (`0px` on `390×844` and Desktop `1200+`)**:
  - Never hardcode multi-column fixed grids like `repeat(3, 1fr)` or `repeat(4, 1fr)` or wide `minmax(340px, 1fr)` without clamping. Always use `minmax(0, 1fr)` or `repeat(auto-fit, minmax(min(100%, <minpx>), 1fr))`.
- **Dual Table / Card Pattern**:
  - Use `.desktop-only-table` for wide financial tables on desktop and `.mobile-only-cards` for clean stacked mobile cards below tablet/mobile breakpoints so table cells never compress or clip.
- **Fluid Buttons, Tabs & Spacing**:
  - Buttons must use fluid height on mobile (`height: auto; min-height: 36px; white-space: normal; word-break: break-word`) so labels never overflow their borders.
  - Multi-tab headers (`AdminPage`, `AlertsPage`, `PaperTradingPage`) must use `.mobile-scroll-tabs` for smooth horizontal touch scrolling on narrow viewports.
  - Keep `84px` bottom clearance on `.main-content` on mobile viewports so floating widgets (`AIAssistantWidget`) never overlap actionable page content, and keep `CookieConsentBanner` hidden once saved (re-openable from Settings).
- **Consolidated UI Controls**:
  - Never render duplicate dropdowns, duplicate switches (`SettingsPage` single master `enable_swing_algo_trading` switch), or redundant multi-selector chrome (`ChartPage` single consolidated `Indicators` dropdown).
  - Pre-populated `StockSearchBox` defaults must use `userTypedRef` so initial mount values never auto-trigger `"No stocks found"` dropdown popovers.
