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
    const originalCode = textarea.value;
    const starterNode = root.querySelector("#practice-starter-codes");
    let starterCodes = {};
    if (starterNode) {
      try { starterCodes = JSON.parse(starterNode.textContent); } catch (_error) { starterCodes = {}; }
    }

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
        editor = window.monaco.editor.create(host, {
          value: textarea.value,
          language: language?.value || "plaintext",
          theme: "vs-dark",
          automaticLayout: true,
          minimap: { enabled: false },
          fontSize: 14,
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
