import { css } from "lit";

/**
 * Panel styles. Only Home Assistant theme variables are used, each with a
 * light fallback so the panel also renders without a theme.
 */
export const panelStyles = css`
  :host {
    --ef-primary: var(--primary-color, #03a9f4);
    --ef-on-primary: var(--text-primary-color, #fff);
    --ef-bg: var(--primary-background-color, #fafafa);
    --ef-card: var(--card-background-color, #fff);
    --ef-text: var(--primary-text-color, #212121);
    --ef-text2: var(--secondary-text-color, #727272);
    --ef-divider: var(--divider-color, rgba(0, 0, 0, 0.12));
    --ef-error: var(--error-color, #db4437);
    --ef-success: var(--success-color, #43a047);
    --ef-radius: var(--ha-card-border-radius, 12px);
    --ef-header-bg: var(--app-header-background-color, var(--ef-bg));
    --ef-header-text: var(--app-header-text-color, var(--ef-text));
    --ef-tint: color-mix(in srgb, var(--ef-primary) 14%, transparent);
    --ef-tint-strong: color-mix(in srgb, var(--ef-primary) 24%, transparent);
    --ef-hover: color-mix(in srgb, var(--ef-text) 7%, transparent);
    display: block;
    height: 100dvh;
    max-width: 100%;
    overflow: hidden;
    background: var(--ef-bg);
    color: var(--ef-text);
    font-family: var(--ha-font-family-body, var(--mdc-typography-font-family, Roboto, system-ui, -apple-system, "Segoe UI", sans-serif));
    font-size: clamp(14px, calc(13px + 0.25vw), 16px);
    line-height: 1.45;
    -webkit-font-smoothing: antialiased;
    -webkit-tap-highlight-color: transparent;
  }
  *, *::before, *::after { box-sizing: border-box; }
  [hidden] { display: none !important; }

  .shell { display: flex; flex-direction: column; height: 100%; min-width: 0; }

  /* Header */
  .top {
    flex: none;
    display: flex;
    align-items: center;
    gap: 4px;
    min-height: 56px;
    padding: 0 8px 0 4px;
    background: var(--ef-header-bg);
    color: var(--ef-header-text);
    border-bottom: 1px solid var(--ef-divider);
  }
  .top h1 {
    flex: 1;
    min-width: 0;
    margin: 0 0 0 12px;
    font-size: 1.25em;
    font-weight: 500;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }
  .top .icon-btn + h1 { margin-left: 4px; }
  .top-nav { display: flex; gap: 4px; }

  /* Body with scrolling main area and toast layer */
  .body { position: relative; flex: 1; min-height: 0; display: flex; }
  main {
    flex: 1;
    min-width: 0;
    overflow-x: hidden;
    overflow-y: auto;
    overscroll-behavior: contain;
    -webkit-overflow-scrolling: touch;
  }
  .content { width: 100%; max-width: 1120px; margin: 0 auto; padding: 16px; }
  /* Collection: the selection bar always sits at the bottom of the window,
     also when the list is short, so a hint above it never covers it. */
  .content.fill { min-height: 100%; display: flex; flex-direction: column; }
  .content.fill > .action-bar { margin-top: auto; }
  .content.fill > .grid { margin-bottom: 16px; }

  /* Bottom navigation (narrow layouts) */
  .bottom-nav {
    flex: none;
    display: flex;
    background: var(--ef-card);
    border-top: 1px solid var(--ef-divider);
  }
  .bottom-nav .nav-btn {
    flex: 1;
    flex-direction: column;
    gap: 2px;
    min-height: 56px;
    border-radius: 0;
    font-size: 0.8em;
  }

  /* Buttons */
  button, a.btn { font: inherit; color: inherit; }
  button { cursor: pointer; }
  button:disabled { cursor: default; opacity: 0.5; }
  .icon-btn {
    flex: none;
    display: inline-grid;
    place-items: center;
    width: 44px;
    height: 44px;
    padding: 0;
    border: 0;
    border-radius: 50%;
    background: transparent;
  }
  .icon-btn:hover { background: var(--ef-hover); }
  .nav-btn {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    gap: 6px;
    min-height: 44px;
    min-width: 44px;
    padding: 0 14px;
    border: 0;
    border-radius: 22px;
    background: transparent;
    color: var(--ef-text2);
    font-weight: 500;
  }
  .nav-btn[aria-current="page"] { color: var(--ef-primary); }
  .top-nav .nav-btn[aria-current="page"] { background: var(--ef-tint); }
  .nav-btn:hover { background: var(--ef-hover); }
  .btn {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    gap: 8px;
    min-height: 44px;
    padding: 0 18px;
    border: 1px solid var(--ef-divider);
    border-radius: 22px;
    background: var(--ef-card);
    color: var(--ef-text);
    font-weight: 500;
    text-decoration: none;
    white-space: nowrap;
  }
  .btn:hover { background: color-mix(in srgb, var(--ef-card) 90%, var(--ef-text)); }
  .btn.primary { background: var(--ef-primary); border-color: var(--ef-primary); color: var(--ef-on-primary); }
  .btn.primary:hover { background: color-mix(in srgb, var(--ef-primary) 88%, #000); }
  .btn.small { min-height: 44px; padding: 0 14px; }
  :focus-visible { outline: 2px solid var(--ef-primary); outline-offset: 2px; }
  svg.i { width: 24px; height: 24px; fill: currentColor; flex: none; }
  svg.i.s { width: 18px; height: 18px; }

  /* Search form */
  .search-form { display: flex; gap: 8px; }
  .field {
    flex: 1;
    min-width: 0;
    display: flex;
    align-items: center;
    gap: 6px;
    min-height: 48px;
    padding: 0 6px 0 12px;
    border: 1px solid var(--ef-divider);
    border-radius: 24px;
    background: var(--ef-card);
    color: var(--ef-text2);
  }
  .field:focus-within { border-color: var(--ef-primary); box-shadow: 0 0 0 1px var(--ef-primary); }
  .field input {
    flex: 1;
    min-width: 0;
    height: 46px;
    border: 0;
    outline: 0;
    background: transparent;
    color: var(--ef-text);
    font: inherit;
    font-size: max(16px, 1em); /* 16px stops iOS from zooming */
  }
  .field input::placeholder { color: var(--ef-text2); opacity: 0.8; }
  .search-form .btn { min-height: 48px; }

  .chips { display: flex; flex-wrap: wrap; gap: 8px; margin: 12px 0 0; padding: 0; border: 0; }
  .chips legend { position: absolute; width: 1px; height: 1px; overflow: hidden; clip: rect(0 0 0 0); }
  .chip {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    min-height: 44px;
    padding: 0 14px;
    border: 1px solid var(--ef-divider);
    border-radius: 22px;
    background: transparent;
    color: var(--ef-text);
    font-size: 0.93em;
  }
  .chip[aria-pressed="true"] { background: var(--ef-tint); border-color: transparent; color: var(--ef-text); }
  .chip svg.i { width: 18px; height: 18px; }

  .link-box { margin-top: 20px; padding: 14px 16px 16px; border-radius: var(--ef-radius); background: var(--ef-card); border: 1px solid var(--ef-divider); }
  .link-box h2 { margin: 0 0 2px; font-size: 1em; font-weight: 500; display: flex; gap: 8px; align-items: center; }
  .link-box p { margin: 0 0 10px; color: var(--ef-text2); font-size: 0.93em; }
  .link-box .field { min-height: 44px; }
  .link-box .field input { height: 42px; }

  /* Status messages */
  .note { margin: 28px auto; max-width: 34em; text-align: center; color: var(--ef-text2); }
  .note > svg.i { display: block; margin: 0 auto 8px; width: 40px; height: 40px; opacity: 0.6; }
  .note .btn { margin-top: 12px; }
  .banner {
    display: flex;
    align-items: flex-start;
    gap: 10px;
    margin: 12px 0 0;
    padding: 10px 12px;
    border-radius: 10px;
    background: color-mix(in srgb, var(--ef-error) 12%, transparent);
    color: var(--ef-text);
    font-size: 0.93em;
  }
  .banner svg.i { color: var(--ef-error); width: 20px; height: 20px; margin-top: 1px; }
  .banner.info { background: var(--ef-tint); }
  .banner.info svg.i { color: var(--ef-primary); }
  .error-text { color: var(--ef-error); }

  /* Recipe cards */
  .grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(min(100%, 150px), 1fr));
    gap: 12px;
    margin-top: 16px;
  }
  .wide .grid { grid-template-columns: repeat(auto-fill, minmax(210px, 1fr)); gap: 16px; }
  .card {
    position: relative;
    min-width: 0;
    display: flex;
    flex-direction: column;
    overflow: hidden;
    border-radius: var(--ef-radius);
    background: var(--ef-card);
    border: 1px solid var(--ef-divider);
    box-shadow: var(--ha-card-box-shadow, none);
  }
  .card-link {
    display: flex;
    flex-direction: column;
    flex: 1;
    width: 100%;
    padding: 0;
    border: 0;
    background: transparent;
    color: inherit;
    text-align: left;
    text-decoration: none;
  }
  .card-link:hover .card-title { color: var(--ef-primary); }
  .photo {
    position: relative;
    display: grid;
    place-items: center;
    width: 100%;
    aspect-ratio: 4 / 3;
    overflow: hidden;
    background: color-mix(in srgb, var(--ef-primary) 10%, var(--ef-card));
    color: color-mix(in srgb, var(--ef-primary) 55%, var(--ef-card));
  }
  .photo svg.i { width: 36px; height: 36px; }
  .photo img { position: absolute; inset: 0; width: 100%; height: 100%; object-fit: cover; }
  .card-body { display: flex; flex-direction: column; gap: 4px; padding: 10px 12px 12px; min-width: 0; }
  .card-title {
    margin: 0;
    font-size: 1em;
    font-weight: 500;
    line-height: 1.3;
    display: -webkit-box;
    -webkit-line-clamp: 2;
    -webkit-box-orient: vertical;
    overflow: hidden;
    overflow-wrap: anywhere;
  }
  .meta { display: flex; flex-wrap: wrap; align-items: center; gap: 4px 10px; color: var(--ef-text2); font-size: 0.86em; min-width: 0; }
  .meta span { display: inline-flex; align-items: center; gap: 4px; min-width: 0; }
  .meta .src { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .meta svg.i { width: 16px; height: 16px; }
  .heart {
    position: absolute;
    top: 4px;
    right: 4px;
    width: 44px;
    height: 44px;
    display: grid;
    place-items: center;
    padding: 0;
    border: 0;
    border-radius: 50%;
    background: transparent;
    color: #fff;
  }
  .heart::before {
    content: "";
    position: absolute;
    inset: 4px;
    border-radius: 50%;
    background: rgba(0, 0, 0, 0.38);
  }
  .heart svg.i { position: relative; width: 22px; height: 22px; transition: transform 0.15s ease; }
  .heart[aria-pressed="true"] svg.i { color: #ff5a70; }
  .heart:active svg.i { transform: scale(0.85); }
  .heart.busy svg.i { opacity: 0.75; }

  /* Collection selection */
  .card.selectable .card-link { cursor: pointer; }
  .card.selected { border-color: var(--ef-primary); box-shadow: 0 0 0 2px var(--ef-primary); }
  .check {
    position: absolute;
    top: 10px;
    left: 10px;
    width: 28px;
    height: 28px;
    display: grid;
    place-items: center;
    border-radius: 50%;
    border: 2px solid #fff;
    background: rgba(0, 0, 0, 0.3);
    color: #fff;
  }
  .card.selected .check { background: var(--ef-primary); border-color: var(--ef-primary); color: var(--ef-on-primary); }
  .check svg.i { width: 18px; height: 18px; }
  .open-btn {
    position: absolute;
    top: 4px;
    right: 4px;
    color: #fff;
  }
  .open-btn::before { content: ""; position: absolute; inset: 4px; border-radius: 50%; background: rgba(0, 0, 0, 0.38); }
  .open-btn svg.i { position: relative; width: 20px; height: 20px; }
  .intro { margin: 0; color: var(--ef-text2); }

  .action-bar {
    position: sticky;
    bottom: 0;
    z-index: 2;
    display: flex;
    align-items: center;
    gap: 8px;
    margin: 16px -16px -16px;
    padding: 10px 16px;
    background: color-mix(in srgb, var(--ef-card) 94%, transparent);
    backdrop-filter: blur(8px);
    -webkit-backdrop-filter: blur(8px);
    border-top: 1px solid var(--ef-divider);
  }
  .action-bar .count { flex: 1; min-width: 0; font-weight: 500; }
  .action-bar .btn.primary { flex: none; }

  /* Recipe view */
  .recipe-head { display: grid; gap: 16px; }
  .wide .recipe-head { grid-template-columns: minmax(0, 5fr) minmax(0, 6fr); align-items: start; gap: 24px; }
  .hero { border-radius: var(--ef-radius); aspect-ratio: 16 / 10; }
  .hero svg.i { width: 48px; height: 48px; }
  .recipe-title { margin: 0; font-size: 1.5em; font-weight: 500; line-height: 1.25; overflow-wrap: anywhere; }
  .recipe-desc { margin: 8px 0 0; color: var(--ef-text2); }
  .facts { display: flex; flex-wrap: wrap; gap: 8px; margin: 12px 0 0; padding: 0; list-style: none; }
  .facts li {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    padding: 6px 12px;
    border-radius: 16px;
    background: var(--ef-tint);
    font-size: 0.9em;
  }
  .facts svg.i { width: 16px; height: 16px; color: var(--ef-primary); }
  .actions { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 16px; }
  .btn.fav[aria-pressed="true"] svg.i { color: #e2405a; }
  .hint { margin: 10px 0 0; color: var(--ef-text2); font-size: 0.9em; }
  .recipe-body { display: grid; gap: 16px; margin-top: 20px; }
  .wide .recipe-body { grid-template-columns: minmax(0, 5fr) minmax(0, 6fr); gap: 24px; align-items: start; }
  .panel-box { padding: 16px; border-radius: var(--ef-radius); background: var(--ef-card); border: 1px solid var(--ef-divider); min-width: 0; }
  .panel-box h2 { margin: 0 0 8px; font-size: 1.1em; font-weight: 500; }
  .ingredients { margin: 0; padding: 0; list-style: none; }
  .ingredients li { display: flex; gap: 12px; padding: 9px 0; border-bottom: 1px solid var(--ef-divider); overflow-wrap: anywhere; }
  .ingredients li:last-child { border-bottom: 0; }
  .ingredients .qty { flex: none; width: 6.5em; color: var(--ef-text2); font-variant-numeric: tabular-nums; }
  .ingredients .note { margin: 0; text-align: left; color: var(--ef-text2); }
  .steps { margin: 0; padding: 0; list-style: none; counter-reset: step; }
  .steps li { position: relative; padding: 4px 0 14px 44px; counter-increment: step; overflow-wrap: anywhere; }
  .steps li::before {
    content: counter(step);
    position: absolute;
    left: 0;
    top: 0;
    width: 30px;
    height: 30px;
    display: grid;
    place-items: center;
    border-radius: 50%;
    background: var(--ef-tint);
    color: var(--ef-primary);
    font-weight: 500;
    font-size: 0.9em;
  }
  .back-row { margin: -4px 0 12px -8px; }
  .back-row .nav-btn { color: var(--ef-text); padding-left: 8px; }

  /* Skeletons */
  .skel { background: var(--ef-hover); border-radius: 6px; animation: pulse 1.4s ease-in-out infinite; }
  .skel.line { height: 0.9em; margin: 6px 0; }
  .skel.line.short { width: 55%; }
  @keyframes pulse { 50% { opacity: 0.45; } }
  @media (prefers-reduced-motion: reduce) {
    .skel { animation: none; }
    .heart svg.i { transition: none; }
  }

  /* Toast */
  .toast {
    position: absolute;
    left: 50%;
    bottom: 16px;
    z-index: 5;
    transform: translateX(-50%);
    display: flex;
    align-items: center;
    gap: 8px;
    width: max-content;
    max-width: calc(100% - 32px);
    padding: 4px 4px 4px 16px;
    border-radius: 12px;
    background: color-mix(in srgb, var(--ef-text) 90%, var(--ef-bg));
    color: var(--ef-bg);
    box-shadow: 0 4px 16px rgba(0, 0, 0, 0.25);
  }
  .toast.raised { bottom: 84px; }
  .toast .msg { flex: 1; min-width: 0; padding: 8px 0; overflow-wrap: anywhere; }
  .toast .icon-btn:hover { background: rgba(127, 127, 127, 0.25); }
  .toast.error .lead { color: color-mix(in srgb, var(--ef-error) 70%, var(--ef-bg)); }
  .toast.ok .lead { color: color-mix(in srgb, var(--ef-success) 70%, var(--ef-bg)); }
  .sr { position: absolute; width: 1px; height: 1px; overflow: hidden; clip: rect(0 0 0 0); white-space: nowrap; }
`;
