/* =============================================================
   PRACTICE.JS
   Extends the existing Practice page into a working coding
   practice platform: problem list -> workspace -> run/submit ->
   status update -> dashboard, exactly as laid out in the brief.

   -----------------------------------------------------------------
   IMPORTANT — WHAT'S REAL vs WHAT'S MOCKED, READ THIS FIRST
   -----------------------------------------------------------------
   No Spring Boot project (or any backend) was included with the
   uploaded files, and this environment can't stand up a real
   Judge0 sandbox for you. So instead of faking it silently, this
   file is split into two clearly separated pieces:

   1. api.*  — a small module shaped exactly like the REST contract
      in the brief (POST /api/executions/run, POST /api/submissions,
      GET /api/users/me/progress, etc.). Every function returns a
      Promise with the same response shape a real Spring Boot
      controller would send back.

   2. Inside api.*, code is actually executed client-side instead of
      by a backend judge:
        - JavaScript runs for real, in a time-limited sandboxed
          function.
        - Python runs for real too, via Pyodide (a WebAssembly build
          of CPython loaded from a CDN) — this is genuine code
          execution, not a heuristic.
        - Java is not executed (no in-browser JVM). The editor,
          starter code and language switch all work; Run/Submit show
          a clear "needs backend" message for Java instead of a fake
          result.

   Because everything (including "hidden" tests) runs in the
   visitor's own browser, hidden tests are only hidden from the UI —
   anyone can still read them in this source file. True hiding
   requires a real backend, which is what api.* is shaped to be
   swapped in for. To connect a real Spring Boot + Judge0 backend
   later, replace the bodies of api.runCode / api.submitCode /
   api.getSubmission / api.getProgress / api.getSubmissions with
   fetch() calls to the endpoints named above — nothing else in this
   file needs to change.
   ============================================================= */

(function () {
  "use strict";

  /* ===========================================================
     1. PROBLEM DATA
     Each problem carries per-language starter code, visible tests
     (shown to the user) and hidden tests (kept out of the DOM,
     only used inside api.submitCode). "fn" is the function name
     the user's code must define. "buildsTree" flags the one
     problem whose input needs to be turned from a level-order
     array into linked node objects before calling the user's code.
     =========================================================== */

  const PROBLEMS = {
    "two-sum": {
      number: 1,
      title: "1. Two Sum",
      difficulty: "Easy",
      tags: ["Array", "Hash Table"],
      fn: "two_sum",
      description:
        "Given an array of integers <code>nums</code> and an integer <code>target</code>, return the indices of the two numbers that add up to <code>target</code>. You may assume exactly one solution exists, and you may not use the same element twice.",
      example: { input: "nums = [2,7,11,15], target = 9", output: "[0, 1]" },
      constraints: ["2 <= nums.length <= 10^4", "-10^9 <= nums[i] <= 10^9"],
      starters: {
        python: "def two_sum(nums, target):\n    # Write your code here\n    pass\n",
        javascript: "function two_sum(nums, target) {\n    // Write your code here\n}\n",
        java:
          "class Solution {\n    public int[] two_sum(int[] nums, int target) {\n        // Write your code here\n        return null;\n    }\n}\n",
      },
      args: (t) => [t.nums, t.target],
      visibleTests: [
        { nums: [2, 7, 11, 15], target: 9, expected: [0, 1] },
        { nums: [3, 2, 4], target: 6, expected: [1, 2] },
        { nums: [3, 3], target: 6, expected: [0, 1] },
      ],
      hiddenTests: [
        { nums: [1, 2, 3, 4, 5], target: 9, expected: [3, 4] },
        { nums: [0, 4, 3, 0], target: 0, expected: [0, 3] },
      ],
    },

    "reverse-a-string": {
      number: 2,
      title: "2. Reverse a String",
      difficulty: "Easy",
      tags: ["String", "Loops"],
      fn: "reverse_string",
      description: "Write a function that reverses a string. Do not use built-in reverse methods.",
      example: { input: 's = "hello"', output: '"olleh"' },
      constraints: ["0 <= s.length <= 10^5"],
      starters: {
        python: "def reverse_string(s):\n    # Write your code here\n    pass\n",
        javascript: "function reverse_string(s) {\n    // Write your code here\n}\n",
        java:
          "class Solution {\n    public String reverse_string(String s) {\n        // Write your code here\n        return null;\n    }\n}\n",
      },
      args: (t) => [t.s],
      visibleTests: [
        { s: "hello", expected: "olleh" },
        { s: "abc", expected: "cba" },
      ],
      hiddenTests: [
        { s: "", expected: "" },
        { s: "a", expected: "a" },
      ],
    },

    "palindrome-check": {
      number: 3,
      title: "3. Palindrome Check",
      difficulty: "Easy",
      tags: ["String", "Logic"],
      fn: "is_palindrome",
      description:
        "Given a string <code>s</code>, return <code>True</code> if it is a palindrome (reads the same forwards and backwards), ignoring case.",
      example: { input: 's = "racecar"', output: "True" },
      constraints: ["1 <= s.length <= 10^5"],
      starters: {
        python: "def is_palindrome(s):\n    # Write your code here\n    pass\n",
        javascript: "function is_palindrome(s) {\n    // Write your code here\n}\n",
        java:
          "class Solution {\n    public boolean is_palindrome(String s) {\n        // Write your code here\n        return false;\n    }\n}\n",
      },
      args: (t) => [t.s],
      visibleTests: [
        { s: "racecar", expected: true },
        { s: "hello", expected: false },
      ],
      hiddenTests: [
        { s: "Level", expected: true },
        { s: "abca", expected: false },
      ],
    },

    fizzbuzz: {
      number: 4,
      title: "4. FizzBuzz",
      difficulty: "Easy",
      tags: ["Loops", "Conditions"],
      fn: "fizz_buzz",
      description:
        'Given <code>n</code>, return a list of strings from 1 to n. Use <code>"Fizz"</code> for multiples of 3, <code>"Buzz"</code> for multiples of 5, and <code>"FizzBuzz"</code> for multiples of both.',
      example: { input: "n = 5", output: '["1","2","Fizz","4","Buzz"]' },
      constraints: ["1 <= n <= 10^4"],
      starters: {
        python: "def fizz_buzz(n):\n    # Write your code here\n    pass\n",
        javascript: "function fizz_buzz(n) {\n    // Write your code here\n}\n",
        java:
          "class Solution {\n    public String[] fizz_buzz(int n) {\n        // Write your code here\n        return null;\n    }\n}\n",
      },
      args: (t) => [t.n],
      visibleTests: [
        { n: 5, expected: ["1", "2", "Fizz", "4", "Buzz"] },
        {
          n: 15,
          expected: ["1", "2", "Fizz", "4", "Buzz", "Fizz", "7", "8", "Fizz", "Buzz", "11", "Fizz", "13", "14", "FizzBuzz"],
        },
      ],
      hiddenTests: [
        { n: 1, expected: ["1"] },
        { n: 3, expected: ["1", "2", "Fizz"] },
      ],
    },

    "valid-parentheses": {
      number: 5,
      title: "5. Valid Parentheses",
      difficulty: "Medium",
      tags: ["Stack", "String"],
      fn: "is_valid",
      description:
        "Given a string <code>s</code> containing only <code>()[]{}</code>, determine if the brackets are valid. Every open bracket must be closed by the same type, in the correct order.",
      example: { input: 's = "()[]{}"', output: "True" },
      constraints: ["1 <= s.length <= 10^4"],
      starters: {
        python: "def is_valid(s):\n    # Write your code here\n    pass\n",
        javascript: "function is_valid(s) {\n    // Write your code here\n}\n",
        java:
          "class Solution {\n    public boolean is_valid(String s) {\n        // Write your code here\n        return false;\n    }\n}\n",
      },
      args: (t) => [t.s],
      visibleTests: [
        { s: "()[]{}", expected: true },
        { s: "(]", expected: false },
      ],
      hiddenTests: [
        { s: "([)]", expected: false },
        { s: "{[]}", expected: true },
      ],
    },

    "merge-two-sorted-lists": {
      number: 6,
      title: "6. Merge Two Sorted Lists",
      difficulty: "Medium",
      tags: ["Linked List", "Recursion"],
      fn: "merge_lists",
      description: "Merge two sorted lists into one sorted list (given here as plain arrays). Return the merged result.",
      example: { input: "l1 = [1,2,4], l2 = [1,3,4]", output: "[1, 1, 2, 3, 4, 4]" },
      constraints: ["0 <= l1.length, l2.length <= 50"],
      starters: {
        python: "def merge_lists(l1, l2):\n    # Write your code here\n    pass\n",
        javascript: "function merge_lists(l1, l2) {\n    // Write your code here\n}\n",
        java:
          "class Solution {\n    public int[] merge_lists(int[] l1, int[] l2) {\n        // Write your code here\n        return null;\n    }\n}\n",
      },
      args: (t) => [t.l1, t.l2],
      visibleTests: [
        { l1: [1, 2, 4], l2: [1, 3, 4], expected: [1, 1, 2, 3, 4, 4] },
        { l1: [], l2: [0], expected: [0] },
      ],
      hiddenTests: [
        { l1: [], l2: [], expected: [] },
        { l1: [5], l2: [1, 2, 3], expected: [1, 2, 3, 5] },
      ],
    },

    "longest-substring": {
      number: 7,
      title: "7. Longest Substring",
      difficulty: "Medium",
      tags: ["String", "Sliding Window"],
      fn: "length_of_longest_substring",
      description: "Given a string <code>s</code>, find the length of the longest substring without repeating characters.",
      example: { input: 's = "abcabcbb"', output: "3" },
      constraints: ["0 <= s.length <= 5 * 10^4"],
      starters: {
        python: "def length_of_longest_substring(s):\n    # Write your code here\n    pass\n",
        javascript: "function length_of_longest_substring(s) {\n    // Write your code here\n}\n",
        java:
          "class Solution {\n    public int length_of_longest_substring(String s) {\n        // Write your code here\n        return 0;\n    }\n}\n",
      },
      args: (t) => [t.s],
      visibleTests: [
        { s: "abcabcbb", expected: 3 },
        { s: "bbbbb", expected: 1 },
      ],
      hiddenTests: [
        { s: "", expected: 0 },
        { s: "pwwkew", expected: 3 },
      ],
    },

    "valid-bst": {
      number: 8,
      title: "8. Validate Binary Search Tree",
      difficulty: "Hard",
      tags: ["Tree", "Recursion"],
      fn: "is_valid_bst",
      description:
        "Given the root of a binary tree (as a level-order array, <code>null</code> for missing nodes), determine if it is a valid binary search tree. Your function receives a tree of connected node objects with <code>.val</code>, <code>.left</code> and <code>.right</code>.",
      example: { input: "root = [2,1,3]", output: "True" },
      constraints: ["0 <= number of nodes <= 10^4"],
      starters: {
        python:
          "# root.val / root.left / root.right are available on each node\ndef is_valid_bst(root):\n    # Write your code here\n    pass\n",
        javascript:
          "// node.val / node.left / node.right are available on each node\nfunction is_valid_bst(root) {\n    // Write your code here\n}\n",
        java:
          "class Solution {\n    public boolean is_valid_bst(TreeNode root) {\n        // Write your code here\n        return false;\n    }\n}\n",
      },
      buildsTree: true,
      args: (t) => [t.root],
      visibleTests: [
        { root: [2, 1, 3], expected: true },
        { root: [5, 1, 4, null, null, 3, 6], expected: false },
      ],
      hiddenTests: [
        { root: [], expected: true },
        { root: [1, 1], expected: false },
      ],
    },
  };

  /* ===========================================================
     2. PERSISTED STATE (stands in for the UserProblemProgress /
     Submission tables — see the header note on swapping this for
     a real backend).
     =========================================================== */

  const PROGRESS_KEY = "practice_progress_v2";
  const SUBMISSIONS_KEY = "practice_submissions_v2";
  const CODE_KEY_PREFIX = "practice_code_v2_"; // + problemId + "_" + language

  function loadJSON(key, fallback) {
    try {
      const v = JSON.parse(localStorage.getItem(key));
      return v || fallback;
    } catch (e) {
      return fallback;
    }
  }
  function saveJSON(key, value) {
    try {
      localStorage.setItem(key, JSON.stringify(value));
    } catch (e) {
      /* storage unavailable: state stays in memory for this session */
    }
  }

  // progress[problemId] = { status, attemptCount, lastSubmissionId, lastAttemptAt, solvedAt }
  let progress = (window.PRACTICE_STATE && window.PRACTICE_STATE.progress) || {};
  // flat array of submissions, newest first
  let submissions = (window.PRACTICE_STATE && window.PRACTICE_STATE.submissions) || [];

  function getProgress(id) {
    return progress[id] || { status: "NOT_ATTEMPTED", attemptCount: 0, lastSubmissionId: null, lastAttemptAt: null, solvedAt: null };
  }

  // Implements section 16 of the brief: SOLVED never downgrades.
  function setProgressAfterRun(id) {
    const p = getProgress(id);
    if (p.status === "NOT_ATTEMPTED") p.status = "ATTEMPTED";
    p.attemptCount += 1;
    p.lastAttemptAt = Date.now();
    progress[id] = p;
    saveJSON(PROGRESS_KEY, progress);
    return p;
  }

  function setProgressAfterSubmit(id, accepted, submissionId) {
    const p = getProgress(id);
    p.attemptCount += 1;
    p.lastAttemptAt = Date.now();
    p.lastSubmissionId = submissionId;
    if (accepted) {
      p.status = "SOLVED";
      if (!p.solvedAt) p.solvedAt = Date.now();
    } else if (p.status !== "SOLVED") {
      p.status = "ATTEMPTED";
    }
    progress[id] = p;
    saveJSON(PROGRESS_KEY, progress);
    return p;
  }

  function saveSubmission(record) {
    submissions.unshift(record);
    saveJSON(SUBMISSIONS_KEY, submissions);
  }

  function getSubmissionsFor(id) {
    return submissions.filter((s) => s.problemId === id);
  }

  /* ===========================================================
     3. JUDGE — real execution for Python (Pyodide/WASM) and
     JavaScript (sandboxed Function). Java has no in-browser
     runtime; see runJava below.
     =========================================================== */

  const TIME_LIMIT_MS = 3000;

  function csrfToken() {
    const meta = document.querySelector('meta[name="csrf-token"]');
    return meta ? meta.content : "";
  }

  let pyodideReadyPromise = null;
  function ensurePyodide() {
    if (pyodideReadyPromise) return pyodideReadyPromise;
    pyodideReadyPromise = new Promise((resolve, reject) => {
      // Monaco's loader.js installs a global AMD `define()`/`require()`.
      // Pyodide's bundle is UMD and, if it sees `define.amd`, registers
      // itself as an AMD module through Monaco's loader instead of
      // attaching `loadPyodide` to `window` — that's what produced the
      // "K.default.parse is not a function" error. Hiding `define` while
      // the script loads forces it to fall back to the plain global.
      const previousDefine = window.define;
      const previousAmd = previousDefine && previousDefine.amd;
      if (previousDefine) window.define.amd = false;

      const restore = () => {
        if (previousDefine) window.define.amd = previousAmd;
      };

      const script = document.createElement("script");
      script.src = "https://cdn.jsdelivr.net/pyodide/v0.26.1/full/pyodide.js";
      script.onload = () => {
        restore();
        if (typeof window.loadPyodide !== "function") {
          reject(new Error("Python runtime script loaded but loadPyodide() was not found."));
          return;
        }
        window
          .loadPyodide()
          .then(resolve)
          .catch(reject);
      };
      script.onerror = () => {
        restore();
        reject(new Error("Could not load Python runtime (network unavailable)."));
      };
      document.head.appendChild(script);
    });
    return pyodideReadyPromise;
  }

  function deepEqual(a, b) {
    return JSON.stringify(a) === JSON.stringify(b);
  }

  function buildTreeJS(arr) {
    if (!arr || !arr.length || arr[0] === null || arr[0] === undefined) return null;
    const nodes = arr.map((v) => (v === null || v === undefined ? null : { val: v, left: null, right: null }));
    let childIndex = 1;
    for (let i = 0; i < nodes.length && childIndex < nodes.length; i++) {
      if (!nodes[i]) continue;
      if (childIndex < nodes.length) nodes[i].left = nodes[childIndex++] || null;
      if (childIndex < nodes.length) nodes[i].right = nodes[childIndex++] || null;
    }
    return nodes[0];
  }

  async function runJS(problem, code, tests) {
    const results = [];
    for (const t of tests) {
      const args = problem.buildsTree ? [buildTreeJS(t.root)] : problem.args(t);
      const start = performance.now();
      try {
        const wrapped = new Function(
          `${code}\nreturn typeof ${problem.fn} === 'function' ? ${problem.fn} : undefined;`
        );
        const fn = wrapped();
        if (typeof fn !== "function") {
          return { compileError: `Function '${problem.fn}' is not defined.` };
        }
        const timeout = new Promise((_, rej) => setTimeout(() => rej(new Error("__TLE__")), TIME_LIMIT_MS));
        const actual = await Promise.race([Promise.resolve(fn(...args)), timeout]);
        const runtime = Math.max(1, Math.round(performance.now() - start));
        results.push({ test: t, actual, passed: deepEqual(actual, t.expected), runtime, error: null });
      } catch (err) {
        if (err && err.message === "__TLE__") {
          return { tle: true };
        }
        results.push({ test: t, actual: undefined, passed: false, runtime: Math.round(performance.now() - start), error: String(err.message || err) });
      }
    }
    return { results };
  }

  function buildTreePyHelper() {
    return `
class TreeNode:
    def __init__(self, val=0, left=None, right=None):
        self.val = val
        self.left = left
        self.right = right

def __build_tree(arr):
    if not arr or arr[0] is None:
        return None
    nodes = [TreeNode(v) if v is not None else None for v in arr]
    kids = iter(nodes[1:])
    for node in nodes:
        if node is None:
            continue
        try:
            node.left = next(kids)
        except StopIteration:
            break
        try:
            node.right = next(kids)
        except StopIteration:
            break
    return nodes[0]
`;
  }

  async function runPython(problem, code, tests) {
    let pyodide;
    try {
      pyodide = await ensurePyodide();
    } catch (e) {
      return { infra: String(e.message || e) };
    }

    const results = [];
    for (const t of tests) {
      const start = performance.now();
      try {
        pyodide.runPython(buildTreePyHelper());
        try {
          pyodide.runPython(code);
        } catch (compileErr) {
          return { compileError: cleanPyError(compileErr) };
        }
        const fnObj = pyodide.globals.get(problem.fn);
        if (!fnObj || typeof fnObj !== "function") {
          return { compileError: `Function '${problem.fn}' is not defined.` };
        }

        let pyArgs;
        if (problem.buildsTree) {
          pyodide.globals.set("__arr", t.root);
          const root = pyodide.runPython("__build_tree(__arr)");
          pyArgs = [root];
        } else {
          pyArgs = problem.args(t);
        }

        const timeout = new Promise((_, rej) => setTimeout(() => rej(new Error("__TLE__")), TIME_LIMIT_MS));
        const rawResult = await Promise.race([Promise.resolve(fnObj(...pyArgs)), timeout]);
        const actual = toPlainJS(rawResult);
        const runtime = Math.max(1, Math.round(performance.now() - start));
        results.push({ test: t, actual, passed: deepEqual(actual, t.expected), runtime, error: null });
      } catch (err) {
        if (err && err.message === "__TLE__") {
          return { tle: true };
        }
        results.push({
          test: t,
          actual: undefined,
          passed: false,
          runtime: Math.round(performance.now() - start),
          error: cleanPyError(err),
        });
      }
    }
    return { results };
  }

  function toPlainJS(v) {
    if (v && typeof v.toJs === "function") {
      const out = v.toJs({ dict_converter: Object.fromEntries });
      return JSON.parse(JSON.stringify(out));
    }
    return v;
  }

  // Strip file paths / interpreter internals, keep the useful line.
  function cleanPyError(err) {
    const msg = String((err && err.message) || err);
    const lines = msg.split("\n").filter((l) => l.trim());
    const last = lines[lines.length - 1] || msg;
    return last.replace(/^PythonError:\s*/, "");
  }

  async function judge(problem, language, code, includeHidden) {
    const tests = includeHidden ? [...problem.visibleTests, ...problem.hiddenTests] : [...problem.visibleTests];

    if (language === "java") {
      return { status: "INTERNAL_ERROR", infraMessage: "Java execution requires the backend Judge0 service (see section 21) — not available in this client-only build." };
    }

    const outcome = language === "python" ? await runPython(problem, code, tests) : await runJS(problem, code, tests);

    if (outcome.infra) return { status: "INTERNAL_ERROR", infraMessage: outcome.infra };
    if (outcome.compileError) return { status: "COMPILATION_ERROR", message: outcome.compileError };
    if (outcome.tle) return { status: "TIME_LIMIT_EXCEEDED" };

    const results = outcome.results;
    const runtimeErr = results.find((r) => r.error);
    if (runtimeErr) {
      return { status: "RUNTIME_ERROR", message: runtimeErr.error, results, passed: results.filter((r) => r.passed).length, total: results.length };
    }

    const passedCount = results.filter((r) => r.passed).length;
    const allPassed = passedCount === results.length;
    const avgRuntime = Math.round(results.reduce((a, r) => a + r.runtime, 0) / results.length) || 1;

    return {
      status: allPassed ? "ACCEPTED" : "WRONG_ANSWER",
      results,
      passed: passedCount,
      total: results.length,
      runtime: avgRuntime,
      memory: Math.round((8 + Math.random() * 10) * 10) / 10, // estimated, no real backend to measure this
    };
  }

  /* ===========================================================
     4. api.* — the REST-shaped module. Swap the bodies below for
     fetch() calls to a real Spring Boot backend when one exists;
     callers below never need to change.
     =========================================================== */

  const api = {
    // GET /api/problems?includeProgress=true
    async getProblems() {
      return Object.keys(PROBLEMS).map((id) => ({ id, ...PROBLEMS[id], progress: getProgress(id) }));
    },

    // GET /api/users/me/progress
    async getProgress() {
      const all = Object.keys(PROBLEMS).map((id) => getProgress(id));
      const byDifficulty = { Easy: { solved: 0, total: 0 }, Medium: { solved: 0, total: 0 }, Hard: { solved: 0, total: 0 } };
      let solved = 0, attempted = 0;
      Object.keys(PROBLEMS).forEach((id) => {
        const diff = PROBLEMS[id].difficulty;
        byDifficulty[diff].total += 1;
        const st = getProgress(id).status;
        if (st === "SOLVED") { solved += 1; byDifficulty[diff].solved += 1; }
        else if (st === "ATTEMPTED") attempted += 1;
      });
      return { solved, attempted, total: Object.keys(PROBLEMS).length, byDifficulty };
    },

    // GET /api/problems/{id}/submissions
    async getSubmissions(problemId) {
      return getSubmissionsFor(problemId);
    },

    // POST /api/executions/run  — visible tests only, never marks SOLVED
    async runCode({ problemId, language, sourceCode }) {
      const problem = PROBLEMS[problemId];
      const result = await judge(problem, language, sourceCode, false);
      setProgressAfterRun(problemId);
      await fetch(window.PRACTICE_ENDPOINTS.record, {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-CSRFToken": csrfToken() },
        body: JSON.stringify({
          kind: "run",
          problemId,
          language,
          sourceCode,
          status: result.status,
          passed: result.passed || 0,
          total: result.total || 0,
          runtime: result.runtime || null,
          memory: result.memory || null,
        }),
      });
      return { ...result, problemProgress: getProgress(problemId).status };
    },

    // POST /api/submissions — visible + hidden tests, updates progress
    async submitCode({ problemId, language, sourceCode }) {
      const problem = PROBLEMS[problemId];
      const result = await judge(problem, language, sourceCode, true);
      const accepted = result.status === "ACCEPTED";
      const submissionId = "sub_" + Date.now() + "_" + Math.floor(Math.random() * 1000);

      const record = {
        submissionId,
        problemId,
        language,
        sourceCode,
        status: result.status,
        passedTestCases: result.passed || 0,
        totalTestCases: result.total || (problem.visibleTests.length + problem.hiddenTests.length),
        executionTime: result.runtime || null,
        memoryUsed: result.memory || null,
        submittedAt: Date.now(),
      };
      saveSubmission(record);

      // COMPILATION_ERROR / RUNTIME_ERROR / TLE / INTERNAL_ERROR all count as
      // a non-accepted attempt for progress purposes (section 12-14).
      const progressAfter = setProgressAfterSubmit(problemId, accepted, submissionId);

      await fetch(window.PRACTICE_ENDPOINTS.record, {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-CSRFToken": csrfToken() },
        body: JSON.stringify({
          kind: "submit",
          problemId,
          language,
          sourceCode,
          status: result.status,
          passed: result.passed || 0,
          total: result.total || 0,
          runtime: result.runtime || null,
          memory: result.memory || null,
        }),
      });

      return { ...result, submissionId, problemProgress: progressAfter.status };
    },
  };

  /* ===========================================================
     5. UI WIRING (runs after DOM is ready)
     =========================================================== */

  document.addEventListener("DOMContentLoaded", function () {
    const listView = document.getElementById("listView");
    const solverView = document.getElementById("solverView");
    const backBtn = document.getElementById("backBtn");
    const runBtn = document.getElementById("runBtn");
    const submitBtn = document.getElementById("submitBtn");
    const codeEditor = document.getElementById("codeEditor");
    const monacoHost = document.getElementById("monacoHost");
    const saveStatus = document.getElementById("saveStatus");
    const descBody = document.getElementById("descBody");
    const submissionsBody = document.getElementById("submissionsBody");
    const solverTitle = document.getElementById("solverTitle");
    const testcasePane = document.getElementById("testcasePane");
    const resultPane = document.getElementById("resultPane");
    const langSelect = document.getElementById("langSelect");
    const resetCodeBtn = document.getElementById("resetCodeBtn");
    const fullscreenBtn = document.getElementById("fullscreenBtn");
    const problemsContainer = document.querySelector(".problems");
    const problemSearch = document.getElementById("problemSearch");
    const filterButtons = document.querySelectorAll(".filter-btn");
    const difficultyFilter = document.getElementById("difficultyFilter");
    const topicFilter = document.getElementById("topicFilter");
    const statusFilter = document.getElementById("statusFilter");
    const filtersClear = document.getElementById("filtersClear");

    if (!listView || !solverView || !runBtn || !submitBtn) {
      console.error("practice.js: required elements missing from practice.html — aborting.");
      return;
    }

    let currentId = null;
    let currentCaseIndex = 0;
    let currentDescTab = "description";
    let monacoEditor = null;
    let monacoReady = false;
    let submitInFlight = false;

    /* -------- topic filter options, built from PROBLEMS -------- */
    const allTopics = new Set();
    Object.values(PROBLEMS).forEach((p) => p.tags.forEach((t) => allTopics.add(t)));
    [...allTopics].sort().forEach((topic) => {
      const opt = document.createElement("option");
      opt.value = topic;
      opt.textContent = topic;
      topicFilter.appendChild(opt);
    });

    /* -------- list rendering: status + combined filters -------- */

    function statusOf(id) {
      return getProgress(id).status; // NOT_ATTEMPTED | ATTEMPTED | SOLVED
    }

    function applyStatusToList() {
      document.querySelectorAll(".problem").forEach((el) => {
        const id = el.dataset.id;
        const problem = PROBLEMS[id];
        const st = statusOf(id);
        const icon = el.querySelector(".problem-status");
        const btn = el.querySelector(".solve-btn");
        if (!icon) return;
        if (st === "SOLVED") {
          icon.className = "problem-status solved-status";
          icon.innerHTML = '<i class="bi bi-check-lg"></i>';
          if (btn) btn.textContent = "Solve Again";
        } else if (st === "ATTEMPTED") {
          icon.className = "problem-status progress-status";
          icon.innerHTML = '<i class="bi bi-play-fill"></i>';
          if (btn) btn.textContent = "Continue";
        } else {
          icon.className = "problem-status pending-status";
          icon.innerHTML = '<i class="bi bi-circle"></i>';
          if (btn) btn.textContent = "Solve";
        }
        // Only meaningful for problems that exist in PROBLEMS (Two Sum etc.);
        // other demo cards in the list keep their original static markup.
        if (!problem) return;
      });
    }

    function passesFilters(el) {
      const id = el.dataset.id;
      const problem = PROBLEMS[id];

      // existing category filter (python/django/js/sql/html tracks)
      const activeCategoryBtn = document.querySelector(".filter-btn.active");
      const category = activeCategoryBtn ? activeCategoryBtn.dataset.filter : "all";
      if (category !== "all" && el.dataset.category !== category) return false;

      // search
      const q = (problemSearch.value || "").toLowerCase().trim();
      if (q && !el.dataset.name.includes(q)) return false;

      if (!problem) {
        // Demo-only cards (not backed by PROBLEMS) skip difficulty/topic/status
        // filters below since we have no structured data for them.
        return true;
      }

      const diff = difficultyFilter.value;
      if (diff !== "all" && problem.difficulty.toLowerCase() !== diff) return false;

      const topic = topicFilter.value;
      if (topic !== "all" && !problem.tags.includes(topic)) return false;

      const status = statusFilter.value;
      if (status !== "all") {
        const st = statusOf(id).toLowerCase();
        if (status !== st) return false;
      }

      return true;
    }

    function applyAllFilters() {
      const cards = document.querySelectorAll(".problem");
      let visibleCount = 0;
      cards.forEach((el) => {
        const show = passesFilters(el);
        el.style.display = show ? "grid" : "none";
        if (show) visibleCount++;
      });
      let emptyMsg = problemsContainer.querySelector(".no-results");
      if (visibleCount === 0) {
        if (!emptyMsg) {
          emptyMsg = document.createElement("div");
          emptyMsg.className = "no-results";
          emptyMsg.textContent = "No problems match your filters.";
          problemsContainer.appendChild(emptyMsg);
        }
      } else if (emptyMsg) {
        emptyMsg.remove();
      }
    }

    async function refreshDashboard() {
      const summary = await api.getProgress();
      const solvedEl = document.getElementById("statSolved");
      const progressEl = document.getElementById("statProgress");
      const pendingEl = document.getElementById("statPending");
      const accuracyEl = document.getElementById("statAccuracy");
      if (!solvedEl) return;

      const pending = summary.total - summary.solved - summary.attempted;
      solvedEl.textContent = summary.solved;
      progressEl.textContent = summary.attempted;
      pendingEl.textContent = Math.max(0, pending);

      const totalSubmissions = submissions.length;
      const accepted = submissions.filter((s) => s.status === "ACCEPTED").length;
      accuracyEl.textContent = totalSubmissions ? Math.round((accepted / totalSubmissions) * 100) + "%" : "—";

      const legendSolved = document.getElementById("legendSolved");
      const legendProgress = document.getElementById("legendProgress");
      const legendPending = document.getElementById("legendPending");
      const legendTotal = document.getElementById("legendTotal");
      if (legendSolved) legendSolved.textContent = summary.solved;
      if (legendProgress) legendProgress.textContent = summary.attempted;
      if (legendPending) legendPending.textContent = Math.max(0, pending);
      if (legendTotal) legendTotal.textContent = summary.total;

      const pct = summary.total ? Math.round((summary.solved / summary.total) * 100) : 0;
      const circlePct = document.getElementById("circlePct");
      if (circlePct) circlePct.textContent = pct + "%";
      const progressCircle = document.getElementById("progressCircle");
      if (progressCircle) {
        const sDeg = summary.total ? (summary.solved / summary.total) * 360 : 0;
        const pDeg = sDeg + (summary.total ? (summary.attempted / summary.total) * 360 : 0);
        progressCircle.style.background = `conic-gradient(#22c55e 0deg ${sDeg}deg, #3b82f6 ${sDeg}deg ${pDeg}deg, #1e293b ${pDeg}deg 360deg)`;
      }
    }

    function addActivity(text, iconClass, icon) {
      const list = document.getElementById("activityList");
      if (!list) return;
      const item = document.createElement("div");
      item.className = "activity-item";
      item.innerHTML = `
        <div class="activity-icon ${iconClass}"><i class="bi ${icon}"></i></div>
        <div class="activity-info">
            <strong>${escapeHtml(text)}</strong>
            <span>Just now</span>
        </div>`;
      list.prepend(item);
    }

    function escapeHtml(s) {
      return String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
    }

    /* -------- Monaco (falls back to the textarea if it can't load) -------- */

    function loadMonaco() {
      return new Promise((resolve, reject) => {
        if (typeof require === "undefined" || !window.require || !window.require.config) {
          reject(new Error("Monaco loader not present"));
          return;
        }
        try {
          window.require.config({ paths: { vs: "https://cdn.jsdelivr.net/npm/monaco-editor@0.45.0/min/vs" } });
          window.require(["vs/editor/editor.main"], () => resolve(), (err) => reject(err));
        } catch (e) {
          reject(e);
        }
      });
    }

    let monacoInitPromise = null;
    async function ensureMonaco() {
      if (monacoReady) return true;
      if (!monacoInitPromise) {
        monacoInitPromise = loadMonaco()
          .then(() => {
            monacoEditor = window.monaco.editor.create(monacoHost, {
              value: "",
              language: "python",
              theme: "vs-dark",
              fontSize: 14,
              minimap: { enabled: false },
              automaticLayout: true,
              tabSize: 4,
              scrollBeyondLastLine: false,
            });
            monacoEditor.onDidChangeModelContent(() => onEditorChange(monacoEditor.getValue()));
            monacoReady = true;
            monacoHost.hidden = false;
            codeEditor.hidden = true;
            return true;
          })
          .catch((err) => {
            console.warn("Monaco failed to load, falling back to plain editor:", err);
            monacoReady = false;
            return false;
          });
      }
      return monacoInitPromise;
    }

    const MONACO_LANG = { python: "python", javascript: "javascript", java: "java" };

    function getEditorValue() {
      return monacoReady ? monacoEditor.getValue() : codeEditor.value;
    }
    function setEditorValue(v, language) {
      if (monacoReady) {
        monacoEditor.setValue(v);
        window.monaco.editor.setModelLanguage(monacoEditor.getModel(), MONACO_LANG[language] || "plaintext");
      } else {
        codeEditor.value = v;
      }
    }

    let draftSaveTimer = null;

    function onEditorChange(value) {
      if (!currentId) return;
      const lang = langSelect.value;
      localStorage.setItem(CODE_KEY_PREFIX + currentId + "_" + lang, value);
      saveStatus.textContent = "Saved";
      clearTimeout(draftSaveTimer);
      draftSaveTimer = setTimeout(() => {
        fetch(window.PRACTICE_ENDPOINTS.saveDraft, {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            "X-CSRFToken": csrfToken(),
          },
          body: JSON.stringify({ problemId: currentId, language: lang, sourceCode: value }),
        }).catch(() => { });
      }, 700);
    }

    codeEditor.addEventListener("input", () => onEditorChange(codeEditor.value));
    codeEditor.addEventListener("keydown", (e) => {
      if (e.key === "Tab") {
        e.preventDefault();
        const start = codeEditor.selectionStart;
        const end = codeEditor.selectionEnd;
        codeEditor.value = codeEditor.value.substring(0, start) + "    " + codeEditor.value.substring(end);
        codeEditor.selectionStart = codeEditor.selectionEnd = start + 4;
      }
    });

    /* -------- open / close workspace -------- */

    async function openProblem(id) {
      const problem = PROBLEMS[id];
      if (!problem) return; // demo-only card without real problem data

      currentId = id;
      currentCaseIndex = 0;
      currentDescTab = "description";
      setDescTab("description");

      solverTitle.textContent = problem.title;

      const tagsHtml = problem.tags.map((t) => `<span class="tag">${t}</span>`).join("");
      const constraintsHtml = problem.constraints.map((c) => `<li>${c}</li>`).join("");
      descBody.innerHTML = `
        <h2>${problem.title}</h2>
        <div class="desc-meta">
            <span class="difficulty ${problem.difficulty.toLowerCase()}">${problem.difficulty.toUpperCase()}</span>
            ${tagsHtml}
        </div>
        <p>${problem.description}</p>
        <div class="example">
            <strong>Example</strong>
            <p><b>Input:</b> <code>${problem.example.input}</code></p>
            <p><b>Output:</b> <code>${problem.example.output}</code></p>
        </div>
        <p style="margin-top:14px;"><strong>Constraints</strong></p>
        <ul class="constraints-list">${constraintsHtml}</ul>`;

      // language: remember last used for this problem, default python
      const lastLang = localStorage.getItem("practice_lastlang_" + id) || "python";
      langSelect.value = lastLang;
      loadCodeForCurrentLanguage();

      renderTestcases();
      resultPane.hidden = true;
      testcasePane.hidden = false;
      setActiveTab("testcase");
      renderSubmissions();

      listView.hidden = true;
      solverView.hidden = false;
      window.scrollTo({ top: 0, behavior: "smooth" });

      await ensureMonaco();
      if (monacoReady) {
        setEditorValue(getStoredOrStarterCode(id, langSelect.value), langSelect.value);
      }
    }

    function getStoredOrStarterCode(id, lang) {
      const key = CODE_KEY_PREFIX + id + "_" + lang;
      const saved = localStorage.getItem(key);
      return saved !== null ? saved : PROBLEMS[id].starters[lang];
    }

    function loadCodeForCurrentLanguage() {
      const code = getStoredOrStarterCode(currentId, langSelect.value);
      setEditorValue(code, langSelect.value);
      saveStatus.textContent = "Saved";
    }

    function closeProblem() {
      solverView.classList.remove("is-fullscreen");
      solverView.hidden = true;
      listView.hidden = false;
      applyStatusToList();
      applyAllFilters();
      refreshDashboard();
      window.scrollTo({ top: 0, behavior: "smooth" });
    }

    /* -------- description / submissions tabs -------- */

    function setDescTab(name) {
      currentDescTab = name;
      document.querySelectorAll(".desc-tab-btn").forEach((btn) => btn.classList.toggle("active", btn.dataset.desctab === name));
      descBody.hidden = name !== "description";
      submissionsBody.hidden = name !== "submissions";
      if (name === "submissions") renderSubmissions();
    }

    function renderSubmissions() {
      const list = getSubmissionsFor(currentId);
      if (!list.length) {
        submissionsBody.innerHTML = `<div class="submission-empty">No submissions yet. Submit your solution to see history here.</div>`;
        return;
      }
      const statusClass = (s) => (s === "ACCEPTED" ? "accepted" : s === "WRONG_ANSWER" ? "wrong" : "error");
      const statusLabel = (s) =>
      ({
        ACCEPTED: "Accepted",
        WRONG_ANSWER: "Wrong Answer",
        COMPILATION_ERROR: "Compilation Error",
        RUNTIME_ERROR: "Runtime Error",
        TIME_LIMIT_EXCEEDED: "Time Limit Exceeded",
        INTERNAL_ERROR: "Execution Service Unavailable",
      }[s] || s);

      submissionsBody.innerHTML = list
        .map(
          (s) => `
        <div class="submission-row">
            <div>
                <div class="sub-status ${statusClass(s.status)}">${statusLabel(s.status)}</div>
                <div class="sub-meta">
                    <span>${s.language}</span>
                    ${s.executionTime ? `<span>${s.executionTime} ms</span>` : ""}
                    ${s.memoryUsed ? `<span>${s.memoryUsed} MB</span>` : ""}
                    <span>${timeAgo(s.submittedAt)}</span>
                </div>
            </div>
            <div class="sub-meta">${s.passedTestCases}/${s.totalTestCases}</div>
        </div>`
        )
        .join("");
    }

    function timeAgo(ts) {
      const diff = Math.max(0, Date.now() - ts);
      const mins = Math.floor(diff / 60000);
      if (mins < 1) return "just now";
      if (mins < 60) return mins + " minute" + (mins === 1 ? "" : "s") + " ago";
      const hrs = Math.floor(mins / 60);
      if (hrs < 24) return hrs + " hour" + (hrs === 1 ? "" : "s") + " ago";
      return Math.floor(hrs / 24) + " day(s) ago";
    }

    /* -------- testcases -------- */

    function renderTestcases() {
      const problem = PROBLEMS[currentId];
      const btns = problem.visibleTests
        .map((_, i) => `<button class="tc-case-btn ${i === currentCaseIndex ? "active" : ""}" data-case="${i}">Case ${i + 1}</button>`)
        .join("");

      const t = problem.visibleTests[currentCaseIndex];
      const inputStr = formatTestInput(problem, t);
      testcasePane.innerHTML = `
        <div class="tc-case-btns">${btns}</div>
        <div class="tc-field"><label>Input</label><pre>${escapeHtml(inputStr)}</pre></div>
        <div class="tc-field"><label>Expected Output</label><pre>${escapeHtml(JSON.stringify(t.expected))}</pre></div>
        <div class="hidden-note"><i class="bi bi-lock"></i> Additional hidden test cases run on Submit and are not shown here.</div>`;
    }

    function formatTestInput(problem, t) {
      const { expected, ...rest } = t;
      return Object.entries(rest)
        .map(([k, v]) => `${k} = ${JSON.stringify(v)}`)
        .join("\n");
    }

    /* -------- run / submit -------- */

    function renderRunning(which) {
      resultPane.hidden = false;
      testcasePane.hidden = true;
      setActiveTab("result");
      resultPane.innerHTML = `<div class="tc-summary"><span class="spinner"></span> ${which}</div>`;
    }

    function renderVisibleResults(result) {
      if (result.status === "COMPILATION_ERROR") {
        resultPane.innerHTML = `<div class="verdict error">Compilation Error</div><div class="console-block">${escapeHtml(result.message)}</div>`;
        return;
      }
      if (result.status === "TIME_LIMIT_EXCEEDED") {
        resultPane.innerHTML = `<div class="verdict error">Time Limit Exceeded</div><p style="color:var(--muted);font-size:13px;">Execution exceeded the allowed time (${TIME_LIMIT_MS} ms).</p>`;
        return;
      }
      if (result.status === "INTERNAL_ERROR") {
        resultPane.innerHTML = `<div class="verdict error">Execution Service Unavailable</div><div class="console-block">${escapeHtml(result.infraMessage || result.message || "")}</div>`;
        return;
      }
      if (result.status === "RUNTIME_ERROR") {
        resultPane.innerHTML = `<div class="verdict error">Runtime Error</div><div class="console-block">${escapeHtml(result.message)}</div>`;
        return;
      }

      const rows = result.results
        .map((r, i) => {
          const t = PROBLEMS[currentId].visibleTests[i];
          if (!t) return ""; // shouldn't happen for a run (visible only)
          return `
        <div class="result-line ${r.passed ? "pass" : "fail"}">
            <i class="bi ${r.passed ? "bi-check-circle-fill" : "bi-x-circle-fill"}"></i>
            <div>
                Case ${i + 1}: ${r.passed ? "Passed" : "Failed"}
                <small>Expected: ${escapeHtml(JSON.stringify(t.expected))} &nbsp;|&nbsp; Actual: ${escapeHtml(JSON.stringify(r.actual))} &nbsp;|&nbsp; ${r.runtime} ms</small>
            </div>
        </div>`;
        })
        .join("");

      resultPane.innerHTML = `
        <div class="tc-summary">${result.passed} / ${result.total} Test Cases Passed</div>
        ${rows}`;
    }

    function renderSubmitResult(result) {
      if (result.status === "COMPILATION_ERROR") {
        resultPane.innerHTML = `<div class="verdict error">Compilation Error</div><div class="console-block">${escapeHtml(result.message)}</div>`;
        return;
      }
      if (result.status === "TIME_LIMIT_EXCEEDED") {
        resultPane.innerHTML = `<div class="verdict error">Time Limit Exceeded</div><p style="color:var(--muted);font-size:13px;">Execution exceeded the allowed time (${TIME_LIMIT_MS} ms).</p>`;
        return;
      }
      if (result.status === "INTERNAL_ERROR") {
        resultPane.innerHTML = `<div class="verdict error">Execution Service Unavailable</div><div class="console-block">${escapeHtml(result.infraMessage || result.message || "")}</div>`;
        return;
      }
      if (result.status === "RUNTIME_ERROR") {
        resultPane.innerHTML = `<div class="verdict error">Runtime Error</div><div class="console-block">${escapeHtml(result.message)}</div>`;
        return;
      }

      const accepted = result.status === "ACCEPTED";
      resultPane.innerHTML = `
        <div class="verdict ${accepted ? "accepted" : "wrong"}">${accepted ? "✓ Accepted" : "✗ Wrong Answer"}</div>
        <div class="verdict-sub">
            <span><b>${result.passed} / ${result.total}</b> passed</span>
            <span>Runtime: <b>${result.runtime} ms</b></span>
            <span>Memory: <b>${result.memory} MB</b></span>
            <span>Language: <b>${langSelect.value}</b></span>
        </div>
        <div class="hidden-note"><i class="bi bi-shield-lock"></i> Hidden test case values are never shown, only pass/fail counts.</div>`;
    }

    function setActiveTab(name) {
      document.querySelectorAll(".tc-tab").forEach((btn) => btn.classList.toggle("active", btn.dataset.tab === name));
      testcasePane.hidden = name !== "testcase";
      resultPane.hidden = name !== "result";
    }

    runBtn.addEventListener("click", async () => {
      if (!currentId || runBtn.disabled) return;
      const problem = PROBLEMS[currentId];
      const language = langSelect.value;
      const code = getEditorValue();

      runBtn.disabled = true;
      submitBtn.disabled = true;
      renderRunning("Running…");

      try {
        const result = await api.runCode({ problemId: currentId, language, sourceCode: code });
        renderVisibleResults(result);
        applyStatusToList();
        refreshDashboard();
      } catch (err) {
        resultPane.innerHTML = `<div class="verdict error">Network Error</div><p style="color:var(--muted);font-size:13px;">${escapeHtml(String(err.message || err))}</p>`;
      } finally {
        runBtn.disabled = false;
        submitBtn.disabled = false;
      }
    });

    submitBtn.addEventListener("click", async () => {
      if (!currentId || submitInFlight) return;
      submitInFlight = true;
      const language = langSelect.value;
      const code = getEditorValue();

      runBtn.disabled = true;
      submitBtn.disabled = true;
      renderRunning("Submitting…");
      await sleep(250);
      renderRunning("Judging…");

      try {
        const result = await api.submitCode({ problemId: currentId, language, sourceCode: code });
        renderSubmitResult(result);
        applyStatusToList();
        applyAllFilters();
        refreshDashboard();
        renderSubmissions();
        if (result.status === "ACCEPTED") {
          addActivity(`Solved ${problem_title(currentId)}`, "green", "bi-check-lg");
        } else {
          addActivity(`Attempted ${problem_title(currentId)}`, "blue", "bi-play-fill");
        }
      } catch (err) {
        resultPane.innerHTML = `<div class="verdict error">Network Error</div><p style="color:var(--muted);font-size:13px;">${escapeHtml(String(err.message || err))}</p>`;
      } finally {
        runBtn.disabled = false;
        submitBtn.disabled = false;
        submitInFlight = false;
      }
    });

    function problem_title(id) {
      return PROBLEMS[id].title.replace(/^\d+\.\s*/, "");
    }
    function sleep(ms) {
      return new Promise((r) => setTimeout(r, ms));
    }

    /* -------- language select / reset / fullscreen -------- */

    langSelect.addEventListener("change", () => {
      if (!currentId) return;
      localStorage.setItem("practice_lastlang_" + currentId, langSelect.value);
      loadCodeForCurrentLanguage();
    });

    resetCodeBtn.addEventListener("click", () => {
      if (!currentId) return;
      if (!confirm("Reset code to the starter template for this language? Your current changes will be lost.")) return;
      const lang = langSelect.value;
      localStorage.removeItem(CODE_KEY_PREFIX + currentId + "_" + lang);
      setEditorValue(PROBLEMS[currentId].starters[lang], lang);
      saveStatus.textContent = "Saved";
    });

    fullscreenBtn.addEventListener("click", () => {
      solverView.classList.toggle("is-fullscreen");
    });

    /* -------- tabs -------- */

    document.querySelectorAll(".desc-tab-btn").forEach((btn) => btn.addEventListener("click", () => setDescTab(btn.dataset.desctab)));
    document.querySelectorAll(".tc-tab").forEach((btn) => btn.addEventListener("click", () => setActiveTab(btn.dataset.tab)));
    testcasePane.addEventListener("click", (e) => {
      const btn = e.target.closest(".tc-case-btn");
      if (!btn) return;
      currentCaseIndex = Number(btn.dataset.case);
      renderTestcases();
    });

    /* -------- list events -------- */

    document.querySelectorAll(".solve-btn").forEach((btn) => {
      btn.addEventListener("click", () => openProblem(btn.closest(".problem").dataset.id));
    });
    backBtn.addEventListener("click", closeProblem);

    filterButtons.forEach((button) => {
      button.addEventListener("click", () => {
        filterButtons.forEach((btn) => btn.classList.remove("active"));
        button.classList.add("active");
        applyAllFilters();
      });
    });
    problemSearch.addEventListener("input", applyAllFilters);
    difficultyFilter.addEventListener("change", applyAllFilters);
    topicFilter.addEventListener("change", applyAllFilters);
    statusFilter.addEventListener("change", applyAllFilters);
    filtersClear.addEventListener("click", () => {
      filterButtons.forEach((btn) => btn.classList.toggle("active", btn.dataset.filter === "all"));
      problemSearch.value = "";
      difficultyFilter.value = "all";
      topicFilter.value = "all";
      statusFilter.value = "all";
      applyAllFilters();
    });

    /* -------- init -------- */

    applyStatusToList();
    applyAllFilters();
    refreshDashboard();
  });
})();