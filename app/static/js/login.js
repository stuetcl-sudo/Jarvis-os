function safeNextPath(value) {
  if (!value || !value.startsWith("/") || value.startsWith("//") || value.includes("\\")) return "/admin";
  try {
    const parsed = new URL(value, window.location.origin);
    if (parsed.origin !== window.location.origin) return "/admin";
    return `${parsed.pathname}${parsed.search}${parsed.hash}`;
  } catch (error) {
    return "/admin";
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
    const response = await fetch("/api/auth/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        username: form.elements.username.value,
        password: form.elements.password.value,
      }),
    });
    if (!response.ok) throw new Error("login failed");
    form.elements.password.value = "";
    const next = new URLSearchParams(window.location.search).get("next");
    window.location.assign(safeNextPath(next));
  } catch (error) {
    form.elements.password.value = "";
    errorBox.hidden = false;
  } finally {
    submitButton.disabled = false;
  }
});
