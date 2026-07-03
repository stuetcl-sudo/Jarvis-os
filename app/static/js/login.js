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
    window.location.assign(safeNextPath(next, fallback));
  } catch (error) {
    form.elements.password.value = "";
    errorBox.hidden = false;
  } finally {
    submitButton.disabled = false;
  }
});
