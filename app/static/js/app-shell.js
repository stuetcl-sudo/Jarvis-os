/* Navigation is a presentation layer; API authorization remains on the server. */
(() => {
  const body = document.body;
  // Dedicated wall screens retain their configured, always-visible dashboard.
  if (body.dataset.wallDashboard === "true") return;
  const sidebar = document.getElementById("appSidebar");
  const menu = document.getElementById("appMenu");
  if (!sidebar || !menu) return;

  const definitions = [
    ["overblik", "Overblik", "home", null],
    ["kalender", "Kalender", "calendar", "calendar"],
    ["opgaver", "Opgaver", "check", "tasks"],
    ["rutiner", "Rutiner", "sun", "routine"],
    ["madplan", "Madplan", "meal", "meal"],
    ["hjemmet", "Hjemmet", "home", "home"],
    ["vejr", "Vejr", "sun", "weather"],
    ["system", "System", "settings", "technical"],
  ];
  const paths = {
    home: "M3 10 12 3l9 7v11h-6v-7H9v7H3Z",
    calendar: "M4 5h16v16H4ZM4 10h16M8 3v4m8-4v4",
    check: "M9 4H4v17h17V11M9 11l4 4L22 4",
    sun: "M12 2v2m0 16v2M2 12h2m16 0h2M5 5l2 2m10 10 2 2M5 19l2-2M17 7l2-2M16 12a4 4 0 1 1-8 0 4 4 0 0 1 8 0",
    meal: "M4 3v7q0 3 3 3t3-3V3M7 3v19M19 22V3q-5 4-5 10h5",
    settings: "M4 7h16M4 17h16M8 4v6m8 4v6",
    paw: "M8 13q4-5 8 0l3 5q0 4-7 1-7 3-7-1ZM5 6a2 2 0 1 0 0 .1M10 3a2 2 0 1 0 0 .1M16 4a2 2 0 1 0 0 .1M21 8a2 2 0 1 0 0 .1",
    energy: "m13 2-9 12h7l-1 8 10-13h-8Z",
    camera: "M3 6h13v14H3Zm13 5 5-3v10l-5-3",
    cart: "M2 3h3l3 13h11l3-9H6M10 20h.1M18 20h.1",
  };
  function icon(name) {
    const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
    svg.setAttribute("viewBox", "0 0 24 24");
    svg.setAttribute("aria-hidden", "true");
    const path = document.createElementNS(svg.namespaceURI, "path");
    path.setAttribute("d", paths[name]);
    svg.append(path);
    return svg;
  }
  const cards = [...document.querySelectorAll("[data-family-card]")];
  const pages = definitions.filter(([, , , card]) => {
    if (!card) return true;
    const element = cards.find((item) => item.dataset.familyCard === card);
    if (!element) return false;
    if (card === "routine") return body.dataset.familyRole !== "anonymous";
    return getComputedStyle(element).display !== "none";
  });
  const links = new Map();
  for (const [id, label, symbol] of pages) {
    const link = document.createElement("a");
    link.href = `#${id}`;
    link.append(icon(symbol), document.createTextNode(label));
    menu.append(link);
    links.set(id, link);
  }
  if (["owner", "adult"].includes(body.dataset.familyRole)) {
    const heading = document.createElement("p");
    heading.className = "app-menu-caption";
    heading.textContent = "På vej";
    menu.append(heading);
    for (const [label, symbol] of [["Indkøb", "cart"], ["Kæledyr", "paw"], ["Energi", "energy"], ["Kamera", "camera"]]) {
      const item = document.createElement("span");
      item.className = "app-planned";
      item.append(icon(symbol), document.createTextNode(label));
      const badge = document.createElement("small");
      badge.textContent = "Senere";
      item.append(badge);
      menu.append(item);
    }
  }
  const account = document.querySelector(".family-navigation");
  if (account) document.getElementById("appAccount").append(account);
  body.classList.add("jarvis-app");
  sidebar.hidden = false;
  const title = document.getElementById("appPageTitle");
  const empty = document.createElement("p");
  empty.className = "app-empty";
  empty.textContent = "Der er ingen rutine at vise lige nu.";
  empty.hidden = true;
  document.querySelector(".family-grid").after(empty);

  function selectPage(focus = false) {
    const id = location.hash.slice(1) || "overblik";
    const page = pages.find(([key]) => key === id) || pages[0];
    const overview = page[0] === "overblik";
    body.dataset.appPage = page[0];
    for (const [key, link] of links) {
      if (key === page[0]) link.setAttribute("aria-current", "page");
      else link.removeAttribute("aria-current");
    }
    cards.forEach((card) => {
      card.classList.toggle("app-section-hidden", !overview && card.dataset.familyCard !== page[3]);
    });
    title.hidden = overview;
    title.textContent = page[1];
    document.title = `Jarvis – ${page[1]}`;
    empty.hidden = page[3] !== "routine" || cards.some((card) => card.dataset.familyCard === "routine" && !card.hidden);
    if (focus) {
      (overview ? document.getElementById("mainContent") : title).focus({ preventScroll: true });
      window.scrollTo({ top: 0, behavior: "instant" });
    }
  }
  document.getElementById("mainContent").setAttribute("tabindex", "-1");
  window.addEventListener("hashchange", () => selectPage(true));
  const routine = cards.find((card) => card.dataset.familyCard === "routine");
  if (routine) new MutationObserver(() => {
    empty.hidden = body.dataset.appPage !== "rutiner" || !routine.hidden;
  }).observe(routine, { attributes: true, attributeFilter: ["hidden"] });
  selectPage();
})();
