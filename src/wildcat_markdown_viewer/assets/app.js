/* Wildcat Markdown Viewer - page script (runs under a nonce-based CSP). */
(() => {
  "use strict";
  const cfg = JSON.parse(document.getElementById("wmv-config").textContent);
  const NONCE = document.currentScript.nonce;
  const ASSETS = cfg.prefix + "/_app";
  const DOC_PREFIX = cfg.prefix + "/doc/";
  const MD_EXT = /\.(md|markdown|mdown|mkdn?|mdwn|mdtxt|mdtext)$/i;
  const content = document.getElementById("content");
  const statusEl = document.getElementById("status");

  // ---------------------------------------------------------------- pywebview bridge
  const apiReady = new Promise((resolve) => {
    if (window.pywebview && window.pywebview.api) resolve();
    else window.addEventListener("pywebviewready", () => resolve(), { once: true });
  });
  async function call(name, ...args) {
    await apiReady;
    const fn = window.pywebview.api[name];
    return fn ? fn(...args) : undefined;
  }

  // ---------------------------------------------------------------- helpers
  const scripts = {};
  function loadScript(src) {
    if (!scripts[src]) {
      scripts[src] = new Promise((resolve, reject) => {
        const s = document.createElement("script");
        s.nonce = NONCE;
        s.src = src;
        s.onload = resolve;
        s.onerror = () => reject(new Error("failed to load " + src));
        document.head.appendChild(s);
      });
    }
    return scripts[src];
  }

  function isDark() {
    return cfg.theme === "dark" ||
      (cfg.theme === "auto" && matchMedia("(prefers-color-scheme: dark)").matches);
  }

  let statusTimer;
  function flash(msg) {
    statusEl.textContent = msg;
    clearTimeout(statusTimer);
    statusTimer = setTimeout(() => (statusEl.textContent = ""), 2500);
  }

  function errorBox(title, message, source) {
    const box = document.createElement("div");
    box.className = "render-error";
    const t = document.createElement("div");
    t.className = "render-error-title";
    t.textContent = title;
    const pre = document.createElement("pre");
    pre.textContent = message;
    box.append(t, pre);
    if (source) {
      const d = document.createElement("details");
      const s = document.createElement("summary");
      s.textContent = "Source";
      const p = document.createElement("pre");
      p.textContent = source;
      d.append(s, p);
      box.append(d);
    }
    return box;
  }

  // ---------------------------------------------------------------- enhancers
  async function renderMath(root) {
    const els = root.querySelectorAll(".math.inline, .math.block");
    if (!els.length) return;
    try {
      await loadScript(ASSETS + "/katex/katex.min.js");
    } catch (e) { return; }
    for (const el of els) {
      const tex = el.dataset.tex ?? el.textContent;
      el.dataset.tex = tex;
      try {
        window.katex.render(tex, el, {
          displayMode: el.tagName === "DIV",
          throwOnError: false,
          output: "htmlAndMathml",
        });
      } catch (e) {
        el.title = String(e);
      }
    }
  }

  let mermaidSeq = 0;
  async function renderMermaid(root) {
    const els = [...root.querySelectorAll("pre.mermaid")];
    if (!els.length) return;
    try {
      await loadScript(ASSETS + "/mermaid/mermaid.min.js");
    } catch (e) { return; }
    const mermaid = window.mermaid;
    mermaid.initialize({
      startOnLoad: false,
      securityLevel: "strict",
      theme: isDark() ? "dark" : "default",
      fontFamily: '-apple-system,"Segoe UI","Noto Sans",Helvetica,Arial,sans-serif',
    });
    for (const el of els) {
      const src = el.textContent;
      try {
        const { svg } = await mermaid.render("wmv-mermaid-" + ++mermaidSeq, src);
        const holder = document.createElement("div");
        holder.className = "mermaid-rendered";
        holder.innerHTML = svg;
        el.replaceWith(holder);
      } catch (e) {
        el.replaceWith(errorBox("Mermaid diagram error", String(e && e.message || e), src));
        // mermaid leaves a temp element behind on failure
        document.getElementById("dwmv-mermaid-" + mermaidSeq)?.remove();
      }
    }
  }

  function addCopyButtons(root) {
    for (const block of root.querySelectorAll(".highlight")) {
      if (block.querySelector(".copy-btn")) continue;
      const pre = block.querySelector("pre");
      if (!pre) continue;
      const btn = document.createElement("button");
      btn.className = "copy-btn";
      btn.type = "button";
      btn.title = "Copy";
      btn.textContent = "Copy";
      btn.addEventListener("click", async (ev) => {
        ev.stopPropagation();
        try {
          await navigator.clipboard.writeText(pre.innerText.replace(/\n$/, ""));
          btn.textContent = "Copied!";
        } catch (e) {
          btn.textContent = "Failed";
        }
        setTimeout(() => (btn.textContent = "Copy"), 1500);
      });
      block.appendChild(btn);
    }
  }

  // ---------------------------------------------------------------- outline
  const outline = document.getElementById("outline");
  function buildOutline() {
    outline.textContent = "";
    const heads = content.querySelectorAll("h1[id],h2[id],h3[id],h4[id],h5[id],h6[id]");
    if (!heads.length) {
      const p = document.createElement("p");
      p.className = "muted";
      p.textContent = "No headings";
      outline.appendChild(p);
      return;
    }
    for (const h of heads) {
      const a = document.createElement("a");
      a.href = "#" + h.id;
      a.textContent = h.textContent.trim();
      a.className = "l" + h.tagName[1];
      a.title = a.textContent;
      outline.appendChild(a);
    }
    spy();
  }
  function spy() {
    if (!document.body.classList.contains("show-outline")) return;
    const heads = content.querySelectorAll("h1[id],h2[id],h3[id],h4[id],h5[id],h6[id]");
    let current = null;
    for (const h of heads) {
      if (h.getBoundingClientRect().top < 90) current = h.id;
      else break;
    }
    for (const a of outline.querySelectorAll("a")) {
      a.classList.toggle("active", a.getAttribute("href") === "#" + current);
    }
  }
  addEventListener("scroll", () => requestAnimationFrame(spy), { passive: true });

  function setOutline(show, persist) {
    document.body.classList.toggle("show-outline", show);
    if (show) buildOutline();
    if (persist) call("set_outline", show);
  }

  // ---------------------------------------------------------------- enhance + live reload
  async function enhance() {
    addCopyButtons(content);
    if (document.body.classList.contains("show-outline")) buildOutline();
    await Promise.all([renderMath(content), renderMermaid(content)]);
  }

  let reloading = false;
  async function poll() {
    if (!cfg.docUrlPart || document.hidden || reloading) return;
    try {
      const r = await fetch(cfg.prefix + "/stat/" + cfg.docUrlPart, { cache: "no-store" });
      const { mtime } = await r.json();
      if (mtime && mtime !== cfg.mtime) await refresh();
    } catch (e) { /* server going away on exit */ }
  }
  async function refresh() {
    reloading = true;
    try {
      const r = await fetch(cfg.prefix + "/fragment/" + cfg.docUrlPart, { cache: "no-store" });
      const data = await r.json();
      if (data.error) { flash("File missing"); return; }
      const y = scrollY;
      content.innerHTML = data.html;
      cfg.mtime = data.mtime;
      document.title = data.title;
      call("set_title", data.title);
      await enhance();
      scrollTo(0, y);
      flash("Reloaded " + new Date().toLocaleTimeString());
    } finally {
      reloading = false;
    }
  }
  setInterval(poll, 800);

  // ---------------------------------------------------------------- links
  document.addEventListener("click", (ev) => {
    const cmdEl = ev.target.closest("[data-cmd]");
    if (cmdEl && cmdEl.tagName === "BUTTON") {
      ev.preventDefault();
      command(cmdEl.dataset.cmd);
      return;
    }
    const a = ev.target.closest("a[href]");
    if (!a || ev.defaultPrevented) return;
    let url;
    try { url = new URL(a.getAttribute("href"), location.href); } catch (e) { return; }

    if (url.origin !== location.origin) {
      ev.preventDefault();
      if (/^(https?|mailto):$/.test(url.protocol)) call("open_external", url.href);
      return;
    }
    // In-page anchor: let the browser scroll.
    if (url.pathname === location.pathname && url.hash) return;

    if (url.pathname.startsWith(DOC_PREFIX)) {
      const fsPath = decodeURIComponent(url.pathname.slice(DOC_PREFIX.length));
      const last = fsPath.split("/").pop();
      const isDirLike = fsPath.endsWith("/") || !last.includes(".");
      if (MD_EXT.test(fsPath) || isDirLike) return; // navigate inside the viewer
      ev.preventDefault();
      call("open_path", fsPath);
    }
  });

  // ---------------------------------------------------------------- find
  const findbar = document.getElementById("findbar");
  const findinput = document.getElementById("findinput");
  function find(backwards) {
    const q = findinput.value;
    if (!q) return;
    if (!window.find(q, false, backwards, true, false, false, false)) flash("No matches");
  }
  findinput.addEventListener("keydown", (ev) => {
    if (ev.key === "Enter") { ev.preventDefault(); find(ev.shiftKey); }
    else if (ev.key === "Escape") command("findclose");
  });

  // ---------------------------------------------------------------- commands
  let zoom = 1;
  function setZoom(z) {
    zoom = Math.min(3, Math.max(0.5, Math.round(z * 10) / 10));
    document.getElementById("layout").style.zoom = zoom;
    flash("Zoom " + Math.round(zoom * 100) + "%");
  }

  async function command(cmd) {
    switch (cmd) {
      case "open": {
        const url = await call("open_dialog");
        if (url) location.href = url;
        break;
      }
      case "back": history.back(); break;
      case "forward": history.forward(); break;
      case "reload": location.reload(); break;
      case "outline": setOutline(!document.body.classList.contains("show-outline"), true); break;
      case "edit": if (cfg.doc) call("edit", cfg.doc); break;
      case "reveal": if (cfg.doc) call("reveal", cfg.doc); break;
      case "print": window.print(); break;
      case "find":
        findbar.hidden = false;
        findinput.focus();
        findinput.select();
        break;
      case "findnext": find(false); break;
      case "findprev": find(true); break;
      case "findclose": findbar.hidden = true; getSelection().removeAllRanges(); break;
      case "theme": {
        const order = ["auto", "light", "dark"];
        await setTheme(order[(order.indexOf(cfg.theme) + 1) % order.length]);
        break;
      }
    }
  }

  const themeSel = document.getElementById("theme");
  themeSel.value = cfg.theme;
  themeSel.addEventListener("change", () => setTheme(themeSel.value));
  async function setTheme(t) {
    await call("set_theme", t);
    location.reload();
  }
  matchMedia("(prefers-color-scheme: dark)").addEventListener("change", () => {
    if (cfg.theme === "auto") location.reload();
  });

  document.addEventListener("keydown", (ev) => {
    const ctrl = ev.ctrlKey || ev.metaKey;
    const k = ev.key.toLowerCase();
    let handled = true;
    if (ctrl && !ev.shiftKey && k === "o") command("open");
    else if (ctrl && ev.shiftKey && k === "o") command("outline");
    else if (ctrl && k === "f") command("find");
    else if (ctrl && k === "e") command("edit");
    else if (ctrl && k === "p") command("print");
    else if (ctrl && k === "t") command("theme");
    else if ((ctrl && k === "r") || ev.key === "F5") command("reload");
    else if (ev.key === "F3") find(ev.shiftKey);
    else if (ev.altKey && ev.key === "ArrowLeft") command("back");
    else if (ev.altKey && ev.key === "ArrowRight") command("forward");
    else if (ctrl && (k === "=" || k === "+")) setZoom(zoom + 0.1);
    else if (ctrl && k === "-") setZoom(zoom - 0.1);
    else if (ctrl && k === "0") setZoom(1);
    else if (ev.key === "Escape" && !findbar.hidden) command("findclose");
    else handled = false;
    if (handled) ev.preventDefault();
  });
  addEventListener("wheel", (ev) => {
    if (ev.ctrlKey) { ev.preventDefault(); setZoom(zoom + (ev.deltaY < 0 ? 0.1 : -0.1)); }
  }, { passive: false });

  // ---------------------------------------------------------------- boot
  if (cfg.outline && cfg.doc) setOutline(true, false);
  call("set_title", document.title);
  enhance();
})();
