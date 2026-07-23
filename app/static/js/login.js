function safeNextPath(value, fallback = "/admin") {
  if (!value || !value.startsWith("/") || value.startsWith("//") || value.includes("\\")) return fallback;
  try {
    const parsed = new URL(value, window.location.origin);
    if (parsed.origin !== window.location.origin) return fallback;
    return `${parsed.pathname}${parsed.search}${parsed.hash}`;
  } catch (error) {
    return fallback;
  }
}

async function ownerLandingPath(requestedPath) {
  try {
    const response = await fetch("/api/admin/setup/status", {
      method: "GET",
      credentials: "same-origin",
      headers: { "Accept": "application/json" },
    });
    if (!response.ok) return requestedPath;
    const summary = await response.json();
    if (summary.state !== "ready") return "/setup";
  } catch (error) {
    return requestedPath;
  }
  return requestedPath === "/setup" ? "/admin" : requestedPath;
}

const form = document.getElementById("loginForm");
const errorBox = document.getElementById("loginError");

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  errorBox.hidden = true;
  const submitButton = form.querySelector('button[type="submit"]');
  submitButton.disabled = true;
  try {
    const payload = { username: form.elements.username.value };
    payload["password"] = form.elements.password.value;
    const response = await fetch("/api/auth/login", {
      method: "POST",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    if (!response.ok) throw new Error("login failed");
    const result = await response.json();
    form.elements.password.value = "";
    const fallback = result.user?.role === "owner" ? "/admin" : "/";
    const next = new URLSearchParams(window.location.search).get("next");
    let destination = safeNextPath(next, fallback);
    if (result.user?.role === "owner") destination = await ownerLandingPath(destination);
    window.location.assign(destination);
  } catch (error) {
    form.elements.password.value = "";
    errorBox.hidden = false;
  } finally {
    submitButton.disabled = false;
  }
});
