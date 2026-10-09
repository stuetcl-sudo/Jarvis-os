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
    ["uge", "Ugeoversigt", "calendar", "planning"],
    ["kalender", "Kalender", "calendar", "calendar"],
    ["opgaver", "Opgaver", "check", "tasks"],
    ["rutiner", "Rutiner", "sun", "routine"],
    ["madplan", "Madplan", "meal", "meal"],
    ["indkoeb", "Indkøb", "cart", "shopping"],
    ["medicin", "Medicin", "pill", "medication"],
    ["beloenninger", "Belønningstavle", "star", "rewards"],
    ["dagsform", "Dagsform", "smile", "wellbeing"],
    ["kaeledyr", "Kæledyr", "paw", "pets"],
    ["energi", "Energi", "energy", "energy"],
    ["kamera", "Kamera", "camera", "cameras"],
    ["hjemmet", "Hjemmet", "home", "home"],
    ["vejr", "Vejr", "sun", "weather"],
    ["beskeder", "Beskeder", "bell", "notifications"],
    ["system", "System", "settings", "technical"],
  ];
  const icon = name => window.JarvisUI?.icon(name) || document.createTextNode('');
  const cards = [...document.querySelectorAll("[data-family-card]")];
  const pages = definitions.filter(([, , , card]) => {
    if (!card) return true;
    const element = cards.find((item) => item.dataset.familyCard === card);
    if (!element) return false;
    if (card === "routine") return body.dataset.familyRole !== "anonymous";
    return getComputedStyle(element).display !== "none";
  });
  for (const [, , symbol, key] of definitions) {
    if (!key) continue;
    for (const card of cards.filter(item => item.dataset.familyCard === key)) {
      let mark = card.querySelector(':scope > .card-icon');
      if (!mark) { mark = document.createElement('div'); mark.className = 'card-icon'; mark.setAttribute('aria-hidden', 'true'); card.prepend(mark); }
      // The weather module owns its changing weather symbol.
      if (key !== 'weather') mark.replaceChildren(icon(symbol));
    }
  }
  const links = new Map();
  for (const [id, label, symbol] of pages) {
    const link = document.createElement("a");
    link.href = `#${id}`;
    link.append(icon(symbol), document.createTextNode(label));
    menu.append(link);
    links.set(id, link);
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
      card.classList.toggle("app-section-hidden", overview || card.dataset.familyCard !== page[3]);
    });
    window.dispatchEvent(new CustomEvent("jarvis:page-changed", {detail:page[0]}));
    title.hidden = overview;
    title.replaceChildren(icon(page[2]), document.createTextNode(page[1]));
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
