(() => {
  const weekdayFormatter = new Intl.DateTimeFormat("da-DK", { weekday: "short" });
  const dateFormatter = new Intl.DateTimeFormat("da-DK", { day: "numeric", month: "short" });

  function setState(message) {
    const state = document.getElementById("mealPlanState");
    const data = document.getElementById("mealPlanData");
    if (state) {
      state.textContent = message;
      state.hidden = false;
    }
    if (data) data.hidden = true;
  }

  function mealText(meals) {
    return Array.isArray(meals) && meals.length ? meals.join(" · ") : "Ikke planlagt";
  }

  function createDay(day) {
    const item = document.createElement("li");
    item.className = "meal-plan-day";

    const when = document.createElement("div");
    when.className = "meal-plan-when";
    const label = document.createElement("strong");
    label.textContent = day.label || "Dag";
    const date = document.createElement("time");
    date.dateTime = day.date || "";
    const parsed = new Date(`${day.date || ""}T12:00:00`);
    date.textContent = Number.isNaN(parsed.getTime())
      ? ""
      : `${weekdayFormatter.format(parsed)} ${dateFormatter.format(parsed)}`;
    when.append(label, date);

    const meal = document.createElement("p");
    meal.textContent = mealText(day.meals);
    if (!Array.isArray(day.meals) || day.meals.length === 0) meal.className = "meal-plan-empty";

    item.append(when, meal);
    return item;
  }

  function renderMealPlan(plan) {
    if (plan.status === "authentication_required") {
      setState("Log ind for at se madplanen");
      return;
    }
    if (plan.status === "not_configured") {
      setState("Madplanen er ikke tilsluttet endnu");
      return;
    }
    if (plan.status === "unavailable") {
      setState("Madplanen kan ikke hentes lige nu");
      return;
    }

    const state = document.getElementById("mealPlanState");
    const data = document.getElementById("mealPlanData");
    if (state) state.hidden = true;
    if (data) data.hidden = false;

    const today = document.getElementById("mealPlanToday");
    if (today) today.textContent = mealText(plan.today);

    const days = document.getElementById("mealPlanDays");
    if (days) {
      days.replaceChildren();
      (plan.days || []).slice(1).forEach((day) => days.append(createDay(day)));
    }

    const notice = document.getElementById("mealPlanNotice");
    if (notice) {
      notice.textContent = plan.status === "stale" ? "Viser senest hentede madplan" : "";
      notice.hidden = plan.status !== "stale";
    }
  }

  async function refreshMealPlan() {
    try {
      const response = await fetch("/api/family/meal-plan", { credentials: "same-origin" });
      if (!response.ok) throw new Error("Madplanen kunne ikke hentes");
      renderMealPlan(await response.json());
    } catch (error) {
      setState("Madplanen kan ikke hentes lige nu");
    }
  }

  refreshMealPlan();
  setInterval(refreshMealPlan, 30000);
})();
