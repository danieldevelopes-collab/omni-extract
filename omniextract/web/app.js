/* =========================================================================
   omni-extract — front-end logic (vanilla JS, no dependencies, fully offline)

   Talks to the local API:
     GET  /api/capabilities
     POST /api/extract     { files:[{name,data_b64}], options:{ocr_lang,ocr_psm} }
     POST /api/shutdown
   ========================================================================= */
(function () {
  "use strict";

  /* ----------------------------- Element refs ---------------------------- */
  const $ = (id) => document.getElementById(id);

  const dropzone = $("dropzone");
  const fileInput = $("fileInput");
  const ocrLang = $("ocrLang");
  const ocrPsm = $("ocrPsm");

  const loading = $("loading");
  const loadingTitle = $("loadingTitle");
  const loadingMeta = $("loadingMeta");

  const errorBanner = $("errorBanner");
  const errorBannerText = $("errorBannerText");

  const results = $("results");
  const resultsSummary = $("resultsSummary");
  const cards = $("cards");
  const formatSegmented = $("formatSegmented");
  const downloadBtn = $("downloadBtn");

  const capList = $("capList");
  const capMeta = $("capMeta");

  const quitBtn = $("quitBtn");
  const quitOverlay = $("quitOverlay");

  /* ------------------------------- State --------------------------------- */
  let lastDocuments = [];      // array of DOC dicts from the most recent run
  let currentFormat = "txt";   // selected download format
  let busy = false;

  /* ----------------------------- Utilities ------------------------------- */
  function show(el) { if (el) el.hidden = false; }
  function hide(el) { if (el) el.hidden = true; }

  function escapeHtml(s) {
    return String(s == null ? "" : s)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function fmtNum(n) {
    const v = Number(n || 0);
    return v.toLocaleString();
  }

  // Read a File as base64 WITHOUT the "data:...;base64," prefix.
  function fileToBase64(file) {
    return new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = () => {
        const res = String(reader.result || "");
        const comma = res.indexOf(",");
        resolve(comma >= 0 ? res.slice(comma + 1) : res);
      };
      reader.onerror = () => reject(reader.error || new Error("read failed"));
      reader.readAsDataURL(file);
    });
  }

  /* =======================================================================
     Drop zone — click, keyboard, and drag-and-drop
     ======================================================================= */
  function openPicker() { if (!busy) fileInput.click(); }

  dropzone.addEventListener("click", openPicker);
  dropzone.addEventListener("keydown", (e) => {
    if (e.key === "Enter" || e.key === " " || e.key === "Spacebar") {
      e.preventDefault();
      openPicker();
    }
  });

  fileInput.addEventListener("change", () => {
    if (fileInput.files && fileInput.files.length) {
      handleFiles(Array.from(fileInput.files));
    }
    // Reset so picking the same file twice still fires "change".
    fileInput.value = "";
  });

  // Drag visuals — count enters/leaves so nested elements don't flicker.
  let dragDepth = 0;
  function isFileDrag(e) {
    return e.dataTransfer && Array.prototype.indexOf.call(e.dataTransfer.types || [], "Files") !== -1;
  }
  ["dragenter", "dragover"].forEach((type) => {
    dropzone.addEventListener(type, (e) => {
      if (!isFileDrag(e)) return;
      e.preventDefault();
      e.dataTransfer.dropEffect = "copy";
      if (type === "dragenter") dragDepth++;
      dropzone.classList.add("is-dragover");
    });
  });
  dropzone.addEventListener("dragleave", (e) => {
    if (!isFileDrag(e)) return;
    dragDepth = Math.max(0, dragDepth - 1);
    if (dragDepth === 0) dropzone.classList.remove("is-dragover");
  });
  dropzone.addEventListener("drop", (e) => {
    e.preventDefault();
    dragDepth = 0;
    dropzone.classList.remove("is-dragover");
    const files = e.dataTransfer && e.dataTransfer.files;
    if (files && files.length) handleFiles(Array.from(files));
  });
  // Stop the browser from navigating if a file is dropped outside the zone.
  window.addEventListener("dragover", (e) => { if (isFileDrag(e)) e.preventDefault(); });
  window.addEventListener("drop", (e) => { if (isFileDrag(e)) e.preventDefault(); });

  /* =======================================================================
     Extract flow
     ======================================================================= */
  async function handleFiles(files) {
    if (busy || !files.length) return;
    busy = true;
    hide(errorBanner);
    hide(results);
    cards.innerHTML = "";

    loadingTitle.textContent =
      files.length === 1 ? "Reading 1 file" : "Reading " + files.length + " files";
    loadingMeta.textContent = "Encoding…";
    show(loading);

    try {
      const payloadFiles = [];
      for (let i = 0; i < files.length; i++) {
        loadingMeta.textContent = "Encoding " + (i + 1) + " of " + files.length;
        const data_b64 = await fileToBase64(files[i]);
        payloadFiles.push({ name: files[i].name, data_b64: data_b64 });
      }

      loadingTitle.textContent = "Extracting text";
      loadingMeta.textContent = "Working locally…";

      const psm = parseInt(ocrPsm.value, 10);
      const body = {
        files: payloadFiles,
        options: {
          ocr_lang: (ocrLang.value || "eng").trim() || "eng",
          ocr_psm: Number.isFinite(psm) ? psm : 3
        }
      };

      const resp = await fetch("/api/extract", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body)
      });

      if (!resp.ok) {
        throw new Error("Server responded " + resp.status + " " + resp.statusText);
      }

      const data = await resp.json();
      const docs = (data && Array.isArray(data.documents)) ? data.documents : [];
      lastDocuments = docs;
      renderResults(docs);
    } catch (err) {
      lastDocuments = [];
      showError(
        "Could not extract those files. " +
        (err && err.message ? err.message : "The local server may not be running.")
      );
    } finally {
      hide(loading);
      busy = false;
    }
  }

  function showError(msg) {
    errorBannerText.textContent = msg;
    show(errorBanner);
  }

  /* =======================================================================
     Rendering
     ======================================================================= */
  function statusOf(doc) {
    if (doc && doc.ok) return { cls: "status-ok", label: "ok" };
    // Honestly distinguish "no backend / unavailable" from a real failure.
    const blob = ((doc && doc.error) || "") + " " +
      (((doc && doc.warnings) || []).join(" "));
    if (/no available backend|unavailable|not installed|hint:/i.test(blob)) {
      return { cls: "status-unavailable", label: "unavailable" };
    }
    return { cls: "status-failed", label: "failed" };
  }

  function renderResults(docs) {
    cards.innerHTML = "";

    if (!docs.length) {
      showError("No documents came back from the server.");
      return;
    }

    const okCount = docs.filter((d) => d && d.ok).length;
    resultsSummary.textContent =
      docs.length + (docs.length === 1 ? " document" : " documents") +
      " · " + okCount + " extracted";

    docs.forEach((doc, i) => {
      cards.appendChild(buildCard(doc, i));
    });

    show(results);
    results.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }

  function buildCard(doc, index) {
    const card = document.createElement("article");
    card.className = "card";
    card.style.setProperty("--stagger", (index * 70) + "ms");

    const status = statusOf(doc);
    const name = (doc && doc.path) || "(unnamed)";
    const text = (doc && doc.text) || "";
    const warnings = (doc && doc.warnings) || [];

    /* ---- head: filename + status pill ---- */
    const head = document.createElement("div");
    head.className = "card-head";
    head.innerHTML =
      '<div class="card-file">' +
        '<span class="card-file-icon" aria-hidden="true">' +
          '<svg viewBox="0 0 24 24" width="18" height="18" fill="none">' +
            '<path d="M7 3h7l4 4v14a1 1 0 0 1-1 1H7a1 1 0 0 1-1-1V4a1 1 0 0 1 1-1z" stroke="currentColor" stroke-width="1.6"/>' +
            '<path d="M14 3v4h4" stroke="currentColor" stroke-width="1.6"/>' +
          '</svg>' +
        '</span>' +
        '<span class="card-name" title="' + escapeHtml(name) + '">' + escapeHtml(name) + '</span>' +
      '</div>' +
      '<span class="status-pill ' + status.cls + '">' +
        '<span class="dot" aria-hidden="true"></span>' + status.label +
      '</span>';
    card.appendChild(head);

    /* ---- stat grid ---- */
    const grid = document.createElement("div");
    grid.className = "stat-grid";
    const stats = [
      ["kind", (doc && doc.kind) || "—"],
      ["backend", (doc && doc.backend) || "—"],
      ["chars", fmtNum(doc && doc.chars)],
      ["words", fmtNum(doc && doc.words)],
      ["time", fmtNum(doc && doc.duration_ms) + " ms"]
    ];
    grid.innerHTML = stats.map((s) =>
      '<div class="stat"><span class="stat-key">' + s[0] + '</span>' +
      '<span class="stat-val" title="' + escapeHtml(s[1]) + '">' + escapeHtml(s[1]) + '</span></div>'
    ).join("");
    card.appendChild(grid);

    /* ---- issues block when not ok ---- */
    if (!(doc && doc.ok) || warnings.length) {
      const issues = document.createElement("div");
      issues.className = "card-issues";
      let html = "";
      if (doc && doc.error) {
        html += '<p class="issue-error">' + escapeHtml(doc.error) + '</p>';
      } else if (!(doc && doc.ok)) {
        html += '<p class="issue-error">No text could be extracted.</p>';
      }
      if (warnings.length) {
        html += '<ul class="issue-warn-list">' +
          warnings.map((w) => '<li>' + escapeHtml(w) + '</li>').join("") +
          '</ul>';
      }
      issues.innerHTML = html;
      card.appendChild(issues);
    }

    /* ---- expandable text panel + copy ---- */
    const wrap = document.createElement("div");
    wrap.className = "card-text";

    const controls = document.createElement("div");
    controls.className = "text-controls";

    const panelId = "panel-" + index;
    const disclosure = document.createElement("button");
    disclosure.type = "button";
    disclosure.className = "disclosure";
    disclosure.setAttribute("aria-expanded", "false");
    disclosure.setAttribute("aria-controls", panelId);
    disclosure.innerHTML =
      '<span class="chevron" aria-hidden="true">' +
        '<svg viewBox="0 0 24 24" width="14" height="14" fill="none">' +
          '<path d="M9 6l6 6-6 6" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>' +
        '</svg>' +
      '</span>' +
      '<span>' + (text ? "Show extracted text" : "No text") + '</span>';

    const copyBtn = document.createElement("button");
    copyBtn.type = "button";
    copyBtn.className = "copy-btn";
    copyBtn.innerHTML =
      '<svg viewBox="0 0 24 24" width="13" height="13" fill="none" aria-hidden="true">' +
        '<rect x="9" y="9" width="11" height="11" rx="2" stroke="currentColor" stroke-width="1.7"/>' +
        '<path d="M5 15V5a2 2 0 0 1 2-2h10" stroke="currentColor" stroke-width="1.7"/>' +
      '</svg><span>Copy</span>';
    if (!text) copyBtn.disabled = true;

    controls.appendChild(disclosure);
    controls.appendChild(copyBtn);
    wrap.appendChild(controls);

    const panel = document.createElement("div");
    panel.className = "text-panel";
    panel.id = panelId;
    const pre = document.createElement("pre");
    pre.className = "text-pre";
    if (text) {
      pre.textContent = text;
    } else {
      pre.innerHTML = '<span class="text-empty">This file produced no text.</span>';
    }
    panel.appendChild(pre);
    wrap.appendChild(panel);

    disclosure.addEventListener("click", () => {
      const open = panel.classList.toggle("is-open");
      disclosure.setAttribute("aria-expanded", open ? "true" : "false");
      const lbl = disclosure.querySelector("span:last-child");
      if (lbl && text) lbl.textContent = open ? "Hide extracted text" : "Show extracted text";
    });

    copyBtn.addEventListener("click", () => copyText(text, copyBtn));

    card.appendChild(wrap);
    return card;
  }

  async function copyText(text, btn) {
    const label = btn.querySelector("span");
    let done = false;
    try {
      if (navigator.clipboard && navigator.clipboard.writeText) {
        await navigator.clipboard.writeText(text);
        done = true;
      }
    } catch (e) { /* fall through to legacy path */ }

    if (!done) {
      const ta = document.createElement("textarea");
      ta.value = text;
      ta.style.position = "fixed";
      ta.style.opacity = "0";
      document.body.appendChild(ta);
      ta.select();
      try { done = document.execCommand("copy"); } catch (e) { done = false; }
      document.body.removeChild(ta);
    }

    if (label) label.textContent = done ? "Copied" : "Press Ctrl+C";
    btn.classList.toggle("is-copied", done);
    setTimeout(() => {
      if (label) label.textContent = "Copy";
      btn.classList.remove("is-copied");
    }, 1600);
  }

  /* =======================================================================
     Client-side export — txt / json / jsonl / csv / md
     Built directly from the documents array. Mirrors omniextract/export.py.
     ======================================================================= */
  function csvField(value) {
    const s = value == null ? "" : String(value);
    // Quote, doubling any embedded quotes (RFC 4180).
    return '"' + s.replace(/"/g, '""') + '"';
  }

  function toCSV(docs) {
    const header = "path,kind,backend,ok,chars,words,duration_ms,warnings,text";
    const rows = docs.map((d) => [
      csvField(d.path || ""),
      csvField(d.kind || ""),
      csvField(d.backend || ""),
      csvField(d.ok ? "True" : "False"),
      csvField(d.chars || 0),
      csvField(d.words || 0),
      csvField(d.duration_ms || 0),
      csvField((d.warnings || []).join("; ")),
      csvField(d.text || "")
    ].join(","));
    return [header].concat(rows).join("\r\n");
  }

  function toJSONL(docs) {
    // One compact object per line — the whole DOC dict.
    return docs.map((d) => JSON.stringify(d)).join("\n");
  }

  function toJSON(docs) {
    return JSON.stringify(docs, null, 2);
  }

  function toText(docs) {
    if (docs.length === 1) return docs[0].text || "";
    return docs.map((d) =>
      "===== " + (d.path || "") + " =====\n" + (d.text || "")
    ).join("\n");
  }

  function toMarkdown(docs) {
    const out = ["# Extraction report", ""];
    docs.forEach((d) => {
      out.push("## " + (d.path || ""));
      out.push("");
      out.push("- kind: " + (d.kind || ""));
      out.push("- backend: " + (d.backend || ""));
      out.push("- chars: " + (d.chars || 0));
      out.push("- words: " + (d.words || 0));
      out.push("- duration_ms: " + (d.duration_ms || 0));
      if ((d.warnings || []).length) {
        out.push("- warnings: " + d.warnings.join("; "));
      }
      out.push("");
      out.push("```");
      out.push(d.text || "");
      out.push("```");
      out.push("");
    });
    return out.join("\n");
  }

  const EXPORTERS = {
    txt:   { build: toText,     ext: "txt",   mime: "text/plain;charset=utf-8" },
    json:  { build: toJSON,     ext: "json",  mime: "application/json;charset=utf-8" },
    jsonl: { build: toJSONL,    ext: "jsonl", mime: "application/x-ndjson;charset=utf-8" },
    csv:   { build: toCSV,      ext: "csv",   mime: "text/csv;charset=utf-8" },
    md:    { build: toMarkdown, ext: "md",    mime: "text/markdown;charset=utf-8" }
  };

  function downloadCurrent() {
    if (!lastDocuments.length) return;
    const spec = EXPORTERS[currentFormat] || EXPORTERS.txt;
    const content = spec.build(lastDocuments);
    const blob = new Blob([content], { type: spec.mime });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "omni-extract." + spec.ext;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }

  // Segmented format control
  formatSegmented.addEventListener("click", (e) => {
    const btn = e.target.closest(".seg-btn");
    if (!btn) return;
    currentFormat = btn.getAttribute("data-fmt") || "txt";
    Array.prototype.forEach.call(formatSegmented.querySelectorAll(".seg-btn"), (b) => {
      const on = b === btn;
      b.classList.toggle("is-active", on);
      b.setAttribute("aria-checked", on ? "true" : "false");
    });
  });

  downloadBtn.addEventListener("click", downloadCurrent);

  /* =======================================================================
     Capabilities — "what can run here"
     ======================================================================= */
  function capIcon(on) {
    if (on) {
      return '<span class="cap-glyph cap-on" aria-hidden="true">' +
        '<svg viewBox="0 0 24 24" width="18" height="18" fill="none">' +
          '<circle cx="12" cy="12" r="9" stroke="currentColor" stroke-width="1.8"/>' +
          '<path d="M8 12.5l2.5 2.5L16 9.5" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/>' +
        '</svg></span>';
    }
    return '<span class="cap-glyph cap-off" aria-hidden="true">' +
      '<svg viewBox="0 0 24 24" width="18" height="18" fill="none">' +
        '<circle cx="12" cy="12" r="3.2" fill="currentColor"/>' +
      '</svg></span>';
  }

  async function loadCapabilities() {
    try {
      const resp = await fetch("/api/capabilities");
      if (!resp.ok) throw new Error("status " + resp.status);
      const data = await resp.json();
      renderCapabilities(data);
    } catch (err) {
      capList.innerHTML =
        '<li class="cap-item cap-loading">Extractor status is unavailable right now.</li>';
      capMeta.textContent = "";
    }
  }

  function renderCapabilities(data) {
    const backends = (data && Array.isArray(data.backends)) ? data.backends : [];

    const metaBits = [];
    if (data && data.platform) metaBits.push(String(data.platform));
    const langs = data && data.tesseract_langs;
    if (typeof langs === "number" && langs > 0) {
      metaBits.push(langs + (langs === 1 ? " OCR language" : " OCR languages"));
    }
    capMeta.textContent = metaBits.join(" · ");

    if (!backends.length) {
      capList.innerHTML =
        '<li class="cap-item cap-loading">No extractors were reported.</li>';
      return;
    }

    // Available first, then alphabetical for a calm, scannable list.
    backends.sort((a, b) => {
      if (!!a.available !== !!b.available) return a.available ? -1 : 1;
      return String(a.name).localeCompare(String(b.name));
    });

    capList.innerHTML = backends.map((b) => {
      const on = !!b.available;
      const kinds = Array.isArray(b.kinds) ? b.kinds.join(", ") : "";
      const title = on
        ? (b.name + " is available")
        : (b.hint ? ("Install: " + b.hint) : (b.name + " is unavailable"));
      return '<li class="cap-item' + (on ? "" : " is-off") + '" title="' + escapeHtml(title) + '">' +
        capIcon(on) +
        '<span class="cap-body">' +
          '<span class="cap-name">' + escapeHtml(b.name || "") + '</span>' +
          '<span class="cap-kinds">' + escapeHtml(kinds || (on ? "ready" : "not installed")) + '</span>' +
        '</span>' +
      '</li>';
    }).join("");
  }

  /* =======================================================================
     Quit
     ======================================================================= */
  quitBtn.addEventListener("click", async () => {
    quitBtn.disabled = true;
    try {
      await fetch("/api/shutdown", { method: "POST" });
    } catch (e) {
      // The server going away mid-request is expected; show the overlay anyway.
    }
    show(quitOverlay);
  });

  /* ------------------------------- Boot ---------------------------------- */
  loadCapabilities();
})();
