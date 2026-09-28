(function () {
  "use strict";

  const problems = [...document.querySelectorAll(".problems .problem")];
  if (!problems.length) return;

  const search = document.getElementById("problemSearch");
  const difficulty = document.getElementById("difficultyFilter");
  const topic = document.getElementById("topicFilter");
  const status = document.getElementById("statusFilter");
  const filterButtons = [...document.querySelectorAll(".filter-btn")];
  let category = "all";

  const topics = new Set();
  problems.forEach((problem) => (problem.dataset.tags || "").split("|").filter(Boolean).forEach((tag) => topics.add(tag)));
  [...topics].sort().forEach((name) => {
    const option = document.createElement("option");
    option.value = name;
    option.textContent = name.replace(/\b\w/g, (letter) => letter.toUpperCase());
    topic.append(option);
  });

  const apply = () => {
    const query = (search.value || "").trim().toLowerCase();
    problems.forEach((problem) => {
      const matches = (category === "all" || problem.dataset.category === category)
        && (difficulty.value === "all" || problem.dataset.difficulty === difficulty.value)
        && (status.value === "all" || problem.dataset.status === status.value)
        && (topic.value === "all" || (problem.dataset.tags || "").split("|").includes(topic.value))
        && (!query || (problem.dataset.name || "").includes(query) || problem.textContent.toLowerCase().includes(query));
      problem.hidden = !matches;
    });
  };

  filterButtons.forEach((button) => button.addEventListener("click", () => {
    category = button.dataset.filter;
    filterButtons.forEach((item) => item.classList.toggle("active", item === button));
    apply();
  }));
  [search, difficulty, topic, status].forEach((control) => control.addEventListener("input", apply));
  document.getElementById("filtersClear")?.addEventListener("click", () => {
    category = "all";
    search.value = "";
    difficulty.value = "all";
    topic.value = "all";
    status.value = "all";
    filterButtons.forEach((item) => item.classList.toggle("active", item.dataset.filter === "all"));
    apply();
  });
})();
