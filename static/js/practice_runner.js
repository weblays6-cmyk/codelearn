(function () {
  "use strict";

  const csrfToken = document.querySelector('input[name="csrfmiddlewaretoken"]')?.value || document.querySelector('meta[name="csrf-token"]')?.content || "";

  document.querySelectorAll("[data-practice-editor]").forEach((root) => {
    const textarea = root.querySelector("[data-code-input]");
    const host = root.querySelector("[data-monaco-host]");
    const output = root.querySelector("[data-run-output]");
    const status = root.querySelector("[data-run-status]");
    const language = root.querySelector("[data-language]");
    const sourceUrl = root.dataset.runUrl;
    const submitUrl = root.dataset.submitUrl;
    const saveUrl = root.dataset.saveUrl;
    let editor = null;
    let sessionId = root.dataset.sessionId || "";
    const playgroundLightTheme = "vgrowhub-playground-light";
    const originalCode = textarea.value;
    const starterNode = root.querySelector("#practice-starter-codes");
    let starterCodes = {};
    if (starterNode) {
      try { starterCodes = JSON.parse(starterNode.textContent); } catch (_error) { starterCodes = {}; }
    }

    const isLightTheme = () => document.body.classList.contains("light-theme");
    const syncEditorTheme = () => {
      if (editor) {
        window.monaco.editor.setTheme(
          isLightTheme() ? playgroundLightTheme : "vs-dark",
        );
      }
    };
    const themeObserver = new MutationObserver(syncEditorTheme);
    themeObserver.observe(document.body, {
      attributes: true,
      attributeFilter: ["class"],
    });

    root.querySelectorAll("[data-playground-tab]").forEach((button) => {
      button.addEventListener("click", () => {
        const tabList = button.closest('[role="tablist"]');
        const paneContainer = tabList?.parentElement;
        if (!tabList || !paneContainer) return;

        tabList.querySelectorAll("[data-playground-tab]").forEach((tab) => {
          const selected = tab === button;
          tab.classList.toggle("active", selected);
          tab.setAttribute("aria-selected", String(selected));
        });
        paneContainer.querySelectorAll("[data-playground-pane]").forEach((pane) => {
          pane.hidden = pane.dataset.playgroundPane !== button.dataset.playgroundTab;
        });
      });
    });

    const getCode = () => editor ? editor.getValue() : textarea.value;
    const setCode = (value) => {
      if (editor) editor.setValue(value);
      textarea.value = value;
    };
    const setStatus = (message, kind) => {
      if (!status) return;
      status.textContent = message;
      status.dataset.kind = kind || "";
    };
    const activatePlaygroundTab = (name) => {
      root.querySelector(`[data-playground-tab="${name}"]`)?.click();
    };
    const showResult = (result) => {
      if (!output) return;
      const tests = (result.testResults || []).map((test, index) => {
        const heading = `Test ${index + 1}: ${test.passed ? "Passed" : "Failed"}`;
        const details = test.hidden ? "Hidden test" : `Input: ${test.input}\nExpected: ${test.expected}\nActual: ${test.actual}`;
        return `${heading}\n${details}`;
      });
      output.textContent = [result.stdout || "", result.stderr || "", ...tests].filter(Boolean).join("\n\n") || "No output.";
      const testSummary = result.total == null ? "" : ` · ${result.passed ?? 0}/${result.total} tests`;
      const runtime = result.executionTime == null ? "" : ` · ${result.executionTime} ms`;
      setStatus(`${result.status}${testSummary}${runtime}`, result.status === "ACCEPTED" || result.status === "SUCCESS" ? "success" : "error");
    };
    const postJSON = async (url, payload) => {
      const response = await fetch(url, {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-CSRFToken": csrfToken },
        credentials: "same-origin",
        body: JSON.stringify(payload),
      });
      const body = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(body.error || "Unable to complete the request.");
      return body;
    };

    root.querySelectorAll("[data-action]").forEach((button) => {
      button.addEventListener("click", async () => {
        const action = button.dataset.action;
        const actionLabel = button.querySelector("[data-action-label]") || button;
        const oldLabel = actionLabel.textContent;
        button.disabled = true;
        actionLabel.textContent = action === "run" ? "Running..." : action === "submit" ? "Evaluating..." : action === "reset" ? "Resetting..." : "Saving...";
        try {
          const payload = {
            language: language?.value || "",
            sourceCode: getCode(),
            stdin: root.querySelector("[data-stdin]")?.value || "",
            title: root.querySelector("[data-session-title]")?.value || "Untitled session",
            sessionId,
            problemId: root.dataset.problemId || "",
          };
          if (action === "run" || action === "submit") {
            const result = await postJSON(action === "submit" ? submitUrl : sourceUrl, payload);
            showResult(result);
            activatePlaygroundTab("output");
          } else if (action === "save") {
            const result = await postJSON(saveUrl, payload);
            sessionId = String(result.sessionId || sessionId);
            root.dataset.sessionId = sessionId;
            setStatus("Saved", "success");
            if (result.redirectUrl) window.location.assign(result.redirectUrl);
          } else if (action === "reset") {
            setCode(starterCodes[language?.value] || root.dataset.starterCode || originalCode);
            setStatus("Starter code restored", "");
          }
        } catch (error) {
          setStatus(error.message || "Unable to complete the request.", "error");
          if (output) output.textContent = error.message || "Unable to complete the request.";
        } finally {
          button.disabled = false;
          actionLabel.textContent = oldLabel;
        }
      });
    });

    if (host && textarea && window.require) {
      window.require.config({ paths: { vs: "https://cdn.jsdelivr.net/npm/monaco-editor@0.45.0/min/vs" } });
      window.require(["vs/editor/editor.main"], function () {
        window.monaco.editor.defineTheme(playgroundLightTheme, {
          base: "vs",
          inherit: true,
          rules: [
            { token: "comment", foreground: "64748B", fontStyle: "italic" },
            { token: "keyword", foreground: "7C3AED" },
            { token: "string", foreground: "15803D" },
            { token: "number", foreground: "B45309" },
            { token: "type.identifier", foreground: "0369A1" },
            { token: "delimiter", foreground: "475569" },
          ],
          colors: {
            "editor.background": "#F8FAFC",
            "editor.foreground": "#1E293B",
            "editorLineNumber.foreground": "#94A3B8",
            "editorLineNumber.activeForeground": "#475569",
            "editorCursor.foreground": "#4F46E5",
            "editor.lineHighlightBackground": "#F1F5F9",
            "editor.selectionBackground": "#C7D2FE",
            "editor.inactiveSelectionBackground": "#E0E7FF",
            "editorIndentGuide.background": "#E2E8F0",
            "editorIndentGuide.activeBackground": "#A5B4FC",
            "editorWidget.background": "#FFFFFF",
            "editorWidget.border": "#CBD5E1",
          },
        });
        editor = window.monaco.editor.create(host, {
          value: textarea.value,
          language: language?.value || "plaintext",
          theme: isLightTheme() ? playgroundLightTheme : "vs-dark",
          automaticLayout: true,
          minimap: { enabled: false },
          fontSize: 16,
          lineHeight: 25,
          fontFamily: "Cascadia Code, Fira Code, Consolas, monospace",
          fontLigatures: true,
          padding: { top: 12, bottom: 12 },
          lineNumbers: "on",
          scrollBeyondLastLine: false,
          tabSize: 4,
        });
        host.hidden = false;
        textarea.hidden = true;
        language?.addEventListener("change", () => {
          window.monaco.editor.setModelLanguage(editor.getModel(), language.value);
          if (starterCodes[language.value]) setCode(starterCodes[language.value]);
        });
      });
    }
  });
})();
