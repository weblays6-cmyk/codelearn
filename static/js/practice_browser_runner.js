(function () {
  "use strict";

  const PINNED = {
    pyodide: "https://cdn.jsdelivr.net/pyodide/v0.27.7/full/pyodide.js",
    sqljs: "https://cdnjs.cloudflare.com/ajax/libs/sql.js/1.13.0/sql-wasm.js",
    sqlWasm: "https://cdnjs.cloudflare.com/ajax/libs/sql.js/1.13.0/",
    cm: "https://esm.sh/codemirror@6.0.1?bundle",
    cmView: "https://esm.sh/@codemirror/view@6.36.5?bundle",
    cmPython: "https://esm.sh/@codemirror/lang-python@6.2.1?bundle",
    cmJavascript: "https://esm.sh/@codemirror/lang-javascript@6.2.2?bundle",
    cmSql: "https://esm.sh/@codemirror/lang-sql@6.8.0?bundle"
  };
  const workerSource = `
    let pyodidePromise;
    let sqlPromise;
    const expectedOutput = test => test.expected !== undefined ? test.expected : test.output;
    const loadPython = () => pyodidePromise ||= (async () => {
      importScripts(${JSON.stringify(PINNED.pyodide)});
      return loadPyodide();
    })();
    const loadSql = () => sqlPromise ||= (async () => {
      importScripts(${JSON.stringify(PINNED.sqljs)});
      return initSqlJs({locateFile: () => ${JSON.stringify(PINNED.sqlWasm + "sql-wasm.wasm")}});
    })();
    self.onmessage = async ({data}) => {
      const output = [];
      try {
        if (data.language === "python") {
          const py = await loadPython();
          self.postMessage({ready: true});
          py.setStdout({batched: text => output.push(text)});
          py.setStderr({batched: text => output.push(text)});
          const input = data.stdin || "";
          let inputIndex = 0;
          py.setStdin({stdin: () => inputIndex < input.length ? input.charCodeAt(inputIndex++) : null});
          self.fetch = undefined; self.XMLHttpRequest = undefined; self.WebSocket = undefined;
          await py.runPythonAsync(data.code);
          const result = {output: output.join(""), status: "SUCCESS"};
          if (data.tests) {
            const fn = py.globals.get(data.functionName);
            if (!fn) throw new Error("Define the expected function before submitting.");
            result.tests = data.tests.map(test => {
              const args = Array.isArray(test.input) ? test.input : [test.input];
              const actual = fn(...args.map(value => py.toPy(value))).toJs({dict_converter: Object.fromEntries});
                const expected = expectedOutput(test);
                return {passed: JSON.stringify(actual) === JSON.stringify(expected), actual, expected, hidden: test.hidden};
              });
          }
          self.postMessage(result);
        } else if (data.language === "javascript") {
          const captured = [];
          const safeConsole = Object.fromEntries(["log","info","warn","error"].map(level => [level, (...items) => captured.push(items.map(String).join(" "))]));
          const inputLines = (data.stdin || "").split(/\\r?\\n/);
          let inputIndex = 0;
          const readline = () => inputLines[inputIndex++] || "";
          self.postMessage({ready: true});
          self.fetch = undefined; self.XMLHttpRequest = undefined; self.WebSocket = undefined;
          const runner = new Function("console", "stdin", "readline", data.code);
          const returned = await runner(safeConsole, data.stdin || "", readline);
          const result = {output: captured.join("\\n") + (returned === undefined ? "" : String(returned)), status: "SUCCESS"};
          if (data.tests) {
            const call = new Function("code", "name", "args", "const exports={}; const module={exports}; new Function('exports','module',code)(exports,module); const target=module.exports && Object.keys(module.exports).length ? module.exports : exports; const fn=target[name] || globalThis[name]; if(typeof fn!=='function') throw new Error('Define the expected function before submitting.'); return fn(...args);");
            result.tests = data.tests.map(test => {
              const actual = call(data.code, data.functionName, Array.isArray(test.input) ? test.input : [test.input]);
              const expected = expectedOutput(test);
              return {passed: JSON.stringify(actual) === JSON.stringify(expected), actual, expected, hidden: test.hidden};
            });
          }
          self.postMessage(result);
        } else if (data.language === "sql") {
          const SQL = await loadSql();
          self.postMessage({ready: true});
          self.fetch = undefined; self.XMLHttpRequest = undefined; self.WebSocket = undefined;
          const db = new SQL.Database();
          try {
            if (!data.tests) {
              db.run("CREATE TABLE learners (name TEXT, language TEXT); INSERT INTO learners VALUES ('Ada','Python'),('Grace','COBOL');");
              const rows = db.exec(data.code);
              self.postMessage({output: JSON.stringify(rows), status: "SUCCESS"});
            } else {
              const results = data.tests.map(test => {
                const testDb = new SQL.Database();
                try {
                  testDb.run(test.input.setup);
                  const rows = testDb.exec(data.code);
                  const actual = rows.flatMap(row => row.values);
                  const expected = expectedOutput(test);
                  return {passed: JSON.stringify(actual) === JSON.stringify(expected), actual, expected, hidden: test.hidden};
                } finally { testDb.close(); }
              });
              self.postMessage({output: "", tests: results, status: "SUCCESS"});
            }
          } finally { db.close(); }
        } else {
          self.postMessage({output: "", status: "SUCCESS"});
        }
      } catch (error) {
        self.postMessage({output: output.join(""), error: String(error && error.message || error), status: "RUNTIME_ERROR"});
      }
    };
  `;

  function workerRun(language, code, stdin, tests, functionName) {
    return new Promise((resolve, reject) => {
      const startedAt = performance.now();
      const blob = new Blob([workerSource], {type: "text/javascript"});
      const workerUrl = URL.createObjectURL(blob);
      const worker = new Worker(workerUrl);
      let timer = setTimeout(() => {
        worker.terminate();
        URL.revokeObjectURL(workerUrl);
        reject(new Error("The browser runtime took too long to load."));
      }, 45000);
      worker.onmessage = event => {
        if (event.data?.ready) {
          clearTimeout(timer);
          timer = setTimeout(() => {
            worker.terminate();
            URL.revokeObjectURL(workerUrl);
            reject(new Error("Time limit exceeded"));
          }, 10000);
          return;
        }
        clearTimeout(timer);
        worker.terminate();
        URL.revokeObjectURL(workerUrl);
        resolve({...event.data, runtimeMs: Math.round(performance.now() - startedAt)});
      };
      worker.onerror = event => {
        clearTimeout(timer);
        worker.terminate();
        URL.revokeObjectURL(workerUrl);
        reject(new Error(event.message || "The browser runtime could not start."));
      };
      worker.postMessage({language, code, stdin, tests, functionName});
    });
  }

  document.querySelectorAll("[data-practice-editor]").forEach(root => {
    const code = root.querySelector("[data-code-input]");
    const language = root.querySelector("[data-language]");
    const output = root.querySelector("[data-run-output]");
    const status = root.querySelector("[data-run-status]");
    const runtimeStatus = root.querySelector("[data-runtime-status]");
    const csrf = root.querySelector("[name=csrfmiddlewaretoken]")?.value || "";
    const loadJSON = id => {
      try { return JSON.parse(root.querySelector(`#${id}`)?.textContent || "[]"); }
      catch (_error) { return []; }
    };
    const starters = loadJSON(root.dataset.problemMode ? "practice-starter-codes" : "playground-starter-codes");
    const activeStarter = () => starters[language?.value] || "";
    const draftKey = (lang = language?.value) => `practice-draft-${root.dataset.problemId || root.dataset.sessionId || "playground"}-${lang}`;
    let editor;
    let hintIndex = 0;

    const getCode = () => editor ? editor.state.doc.toString() : code.value;
    const setCode = value => {
      code.value = value;
      if (editor) editor.dispatch({changes: {from: 0, to: editor.state.doc.length, insert: value}});
      localStorage.setItem(draftKey(), value);
    };
    const setStatus = (text, kind) => {
      if (status) { status.textContent = text; status.dataset.kind = kind || ""; }
    };
    const post = async (url, data) => {
      const response = await fetch(url, {
        method: "POST",
        credentials: "same-origin",
        headers: {"Content-Type": "application/json", "X-CSRFToken": csrf},
        body: JSON.stringify(data)
      });
      const body = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(body.error || "Request failed. Please try again.");
      return body;
    };
    async function start() {
      if (runtimeStatus) runtimeStatus.textContent = `Loading ${language.value === "python" ? "Python" : language.value}…`;
      try {
        if (language.value === "python") await workerRun("python", "pass", "", null, "");
        else if (language.value === "sql") await workerRun("sql", "SELECT 1;", "", null, "");
        if (runtimeStatus) runtimeStatus.textContent = `${language.value} ready`;
      } catch (error) {
        if (runtimeStatus) runtimeStatus.textContent = `Runtime unavailable. ${error.message}`;
      }
    }

    import(PINNED.cm).then(async cm => {
      const {basicSetup} = cm;
      const {EditorView} = await import(PINNED.cmView);
      const extensions = [basicSetup, EditorView.updateListener.of(update => {
        if (update.docChanged) {
          code.value = update.state.doc.toString();
          localStorage.setItem(draftKey(), code.value);
        }
      })];
      try {
        if (language.value === "python") extensions.push((await import(PINNED.cmPython)).python());
        else if (language.value === "javascript") extensions.push((await import(PINNED.cmJavascript)).javascript());
        else if (language.value === "sql") extensions.push((await import(PINNED.cmSql)).sql());
      } catch (_error) { /* The textarea remains a usable editor when an optional mode fails. */ }
      const host = root.querySelector("[data-monaco-host]");
      if (!host) return;
      extensions.push(EditorView.theme({
        "&": {height: "100%", color: "var(--text-primary, #e2e8f0)", backgroundColor: "var(--surface, #0b1220)"},
        ".cm-gutters": {backgroundColor: "var(--surface, #0b1220)", color: "var(--text-muted, #94a3b8)"},
        ".cm-activeLine": {backgroundColor: "rgba(59,130,246,.08)"}
      }));
      editor = new EditorView({doc: code.value, extensions, parent: host});
      host.hidden = false;
      code.hidden = true;
      host.classList.add("editor-fade-in");
      root.classList.remove("editor-loading");
    }).catch(() => {
      if (runtimeStatus) runtimeStatus.textContent = "Editor extension unavailable; plain text editing is ready.";
      root.classList.remove("editor-loading");
      code.classList.add("editor-fade-in");
    });

    language?.addEventListener("change", () => {
      setCode(localStorage.getItem(draftKey()) || activeStarter());
      start();
    });
    start();

    root.querySelectorAll("[data-action]").forEach(button => button.addEventListener("click", async () => {
      const action = button.dataset.action;
      const source = getCode();
      const lang = language?.value || "python";
      try {
        if (action === "run" || action === "submit") {
          const problemMode = root.dataset.problemMode === "true";
          if (lang === "html") {
            const frame = root.querySelector("[data-html-preview]");
            frame.srcdoc = source;
            frame.hidden = false;
            if (output) output.textContent = "Preview rendered in a sandboxed frame.";
            setStatus("Preview ready", "success");
          } else if (["python", "javascript", "sql"].includes(lang)) {
            const visibleTests = problemMode ? loadJSON("practice-visible-tests").map(test => ({...test, hidden: false})) : [];
            const hiddenTests = problemMode && action === "submit" ? loadJSON("practice-hidden-tests").map(test => ({...test, hidden: true})) : [];
            const tests = problemMode ? visibleTests.concat(hiddenTests) : null;
            const result = await workerRun(lang, source, root.querySelector("[data-stdin]")?.value || "", tests, root.dataset.functionName || "");
            const cases = (result.tests || []).map((test, index) => {
              const label = test.hidden ? `Hidden case ${index + 1}` : `Case ${index + 1}`;
              const details = test.hidden ? "" : ` · expected ${JSON.stringify(test.expected)} · actual ${JSON.stringify(test.actual)}`;
              return `${label}: ${test.passed ? "Passed" : "Failed"}${details}`;
            }).join("\\n");
            if (output) output.textContent = [result.output, result.error, cases].filter(Boolean).join("\\n") || "No output.";
            const accepted = action === "submit" && result.tests?.length > 0 && result.tests.every(test => test.passed);
            const resultStatus = result.error ? "RUNTIME_ERROR" : accepted ? "ACCEPTED" : action === "submit" ? "WRONG_ANSWER" : result.status;
            const resultLabel = {
              ACCEPTED: "Accepted",
              WRONG_ANSWER: "Not yet passing",
              RUNTIME_ERROR: "Runtime error",
              SUCCESS: "Run complete"
            }[resultStatus] || "Completed";
            const runtimeLabel = `Runtime: ${result.runtimeMs || 0} ms · Exit status: ${result.error ? "Error" : "Completed"}`;
            setStatus(`${resultLabel}${result.tests ? ` · ${result.tests.filter(test => test.passed).length}/${result.tests.length} cases` : ""}`, accepted || resultStatus === "SUCCESS" ? "success" : "error");
            if (output && resultStatus !== "RUNTIME_ERROR") output.textContent = [result.output, runtimeLabel, cases].filter(Boolean).join("\n") || runtimeLabel;
            if (problemMode && action === "submit") {
              await post(root.dataset.recordUrl, {
                kind: "submit", problemId: root.dataset.problemId, language: lang, sourceCode: source,
                status: resultStatus, passed: (result.tests || []).filter(test => test.passed).length,
                total: (result.tests || []).length, runtime: result.runtimeMs || 0
              });
              if (accepted) window.location.reload();
            }
          } else {
            const response = await post(root.dataset.runUrl, {language: lang, sourceCode: source, stdin: root.querySelector("[data-stdin]")?.value || ""});
            if (output) output.textContent = response.stdout || response.stderr || "No output.";
            setStatus(response.status === "ACCEPTED" ? "Accepted" : response.status === "RUNTIME_ERROR" ? "Runtime error" : "Run complete", "success");
          }
          root.querySelector('[data-playground-tab="output"]')?.click();
        } else if (action === "save") {
          const problemMode = root.dataset.problemMode === "true";
          const response = await post(root.dataset.saveUrl, {
            problemId: root.dataset.problemId || "",
            language: lang, sourceCode: source,
            stdin: root.querySelector("[data-stdin]")?.value || "",
            notes: root.querySelector("[data-problem-notes]")?.value || "",
            title: root.querySelector("[data-session-title]")?.value || "Untitled session",
            sessionId: root.dataset.sessionId || ""
          });
          if (response.sessionId) root.dataset.sessionId = response.sessionId;
          setStatus("Saved", "success");
          if (!problemMode && response.sessionId && !new URLSearchParams(location.search).has("session")) location.assign(`?session=${response.sessionId}`);
        } else if (action === "reset") {
          setCode(activeStarter());
          setStatus("Starter restored", "");
        } else if (action === "format") {
          setCode(source.split("\n").map(line => line.replace(/\s+$/, "")).join("\n").trimEnd() + "\n");
        } else if (action === "fullscreen") {
          (root.querySelector("[data-monaco-host]") || code).requestFullscreen?.();
        }
      } catch (error) {
        setStatus(error.message, "error");
        if (output) output.textContent = error.message;
      }
    }));
    root.querySelector("[data-runtime-retry]")?.addEventListener("click", start);

    root.querySelectorAll("[data-playground-tab]").forEach(button => button.addEventListener("click", () => {
      const tablist = button.closest('[role="tablist"]');
      const tabs = [...(tablist?.querySelectorAll("[data-playground-tab]") || [])];
      const paneNames = new Set(tabs.map(tab => tab.dataset.playgroundTab));
      tabs.forEach(tab => {
        const selected = tab === button;
        tab.classList.toggle("active", selected);
        tab.setAttribute("aria-selected", String(selected));
      });
      root.querySelectorAll("[data-playground-pane]").forEach(pane => {
        if (paneNames.has(pane.dataset.playgroundPane)) {
          pane.hidden = pane.dataset.playgroundPane !== button.dataset.playgroundTab;
        }
      });
    }));

    root.querySelectorAll("[data-problem-tab]").forEach(button => button.addEventListener("click", () => {
      root.querySelectorAll("[data-problem-pane]").forEach(pane => {
        pane.hidden = pane.dataset.problemPane !== button.dataset.problemTab;
      });
      root.querySelectorAll("[data-problem-tab]").forEach(tab => tab.classList.toggle("active", tab === button));
    }));
    const hints = loadJSON("practice-hints");
    root.querySelector("[data-next-hint]")?.addEventListener("click", event => {
      if (hintIndex >= hints.length) { event.currentTarget.disabled = true; return; }
      const item = document.createElement("p");
      item.textContent = `${hintIndex + 1}. ${hints[hintIndex++]}`;
      root.querySelector("[data-hint-output]")?.append(item);
      if (hintIndex >= hints.length) event.currentTarget.disabled = true;
    });

    root.querySelector("[data-file-download]")?.addEventListener("click", () => {
      const blob = new Blob([getCode()], {type: "text/plain"});
      const anchor = document.createElement("a");
      anchor.href = URL.createObjectURL(blob);
      anchor.download = `${root.querySelector("[data-session-title]")?.value || "code"}.${language.value}`;
      anchor.click();
      URL.revokeObjectURL(anchor.href);
    });
    root.querySelector("[data-file-import]")?.addEventListener("change", async event => {
      const file = event.target.files?.[0];
      if (!file) return;
      if (file.size > 20000) { setStatus("Files must be 20 KB or smaller.", "error"); return; }
      setCode(await file.text());
    });
    root.querySelector("[data-save-snippet]")?.addEventListener("click", () => {
      let snippets = [];
      try { snippets = JSON.parse(localStorage.getItem("practice-snippets") || "[]"); } catch (_error) { snippets = []; }
      snippets.unshift({language: language.value, code: getCode()});
      localStorage.setItem("practice-snippets", JSON.stringify(snippets.slice(0, 10)));
      renderSnippets();
      setStatus("Snippet saved in this browser.", "success");
    });
    const renderSnippets = () => {
      const select = root.querySelector("[data-snippet-list]");
      if (!select) return;
      let snippets = [];
      try { snippets = JSON.parse(localStorage.getItem("practice-snippets") || "[]"); } catch (_error) { snippets = []; }
      select.replaceChildren(new Option("Snippet library", ""));
      snippets.forEach((item, index) => select.add(new Option(`${item.language} snippet ${index + 1}`, String(index))));
    };
    renderSnippets();
    root.querySelector("[data-load-snippet]")?.addEventListener("click", () => {
      const select = root.querySelector("[data-snippet-list]");
      try {
        const snippets = JSON.parse(localStorage.getItem("practice-snippets") || "[]");
        const snippet = snippets[Number(select?.value)];
        if (snippet && snippet.language === language.value) setCode(snippet.code);
        else setStatus("Choose a snippet for the selected language.", "error");
      } catch (_error) {
        setStatus("The browser snippet library could not be read.", "error");
      }
    });
    root.querySelectorAll("[data-session-action]").forEach(button => button.addEventListener("click", async () => {
      const id = button.dataset.sessionId;
      const endpoint = root.dataset.sessionActionUrl.replace(/\/0\/$/, `/${id}/`);
      try {
        const result = await post(endpoint, {action: button.dataset.sessionAction});
        if (result.redirectUrl) location.assign(result.redirectUrl);
        else if (result.shareUrl) { await navigator.clipboard.writeText(result.shareUrl); setStatus("Read-only link copied.", "success"); }
        else if (result.deleted || result.revoked) location.reload();
      } catch (error) { setStatus(error.message, "error"); }
    }));
    root.addEventListener("keydown", event => {
      if ((event.ctrlKey || event.metaKey) && event.key === "Enter") {
        event.preventDefault();
        root.querySelector('[data-action="run"]')?.click();
      }
    });
    let autosaveTimer;
    code?.addEventListener("input", () => {
      localStorage.setItem(draftKey(), code.value);
      clearTimeout(autosaveTimer);
      autosaveTimer = setTimeout(() => {
        if (root.dataset.problemMode === "true") {
          post(root.dataset.saveUrl, {
            problemId: root.dataset.problemId, language: language?.value || "python",
            sourceCode: getCode(), notes: root.querySelector("[data-problem-notes]")?.value || ""
          }).catch(error => setStatus(error.message, "error"));
        }
      }, 1500);
    });
    root.querySelector("[data-ai-explain]")?.addEventListener("click", event => {
      const errorText = output?.textContent || "";
      const title = root.dataset.problemTitle || "Practice problem";
      const prompt = `Help me understand ${title}.`;
      const context = `Problem: ${title}\nLanguage: ${language.value}\nCode:\n${getCode()}\n\nOutput or error:\n${errorText}`;
      const link = event.currentTarget;
      link.href = `${root.dataset.aiUrl}?prompt=${encodeURIComponent(prompt)}&context=${encodeURIComponent(context.slice(0, 6000))}`;
    });
  });
})();
