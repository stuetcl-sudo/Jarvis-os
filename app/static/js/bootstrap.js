"use strict";

const form = document.getElementById("bootstrapForm");
const displayNameInput = document.getElementById("displayName");
const usernameInput = document.getElementById("username");
const passwordInput = document.getElementById("password");
const confirmPasswordInput = document.getElementById("confirmPassword");
const submitButton = document.getElementById("bootstrapSubmit");
const errorMessage = document.getElementById("bootstrapError");

function showError(message, field = null) {
  errorMessage.textContent = message;
  errorMessage.hidden = false;

  if (field) {
    field.setAttribute("aria-invalid", "true");
    field.focus();
  }
}

function clearError() {
  errorMessage.textContent = "";
  errorMessage.hidden = true;

  for (const field of [
    displayNameInput,
    usernameInput,
    passwordInput,
    confirmPasswordInput,
  ]) {
    field.removeAttribute("aria-invalid");
  }
}

function setPending(pending) {
  submitButton.disabled = pending;
  submitButton.textContent = pending
    ? "Opretter ejer…"
    : "Opret ejer og fortsæt";
}

async function readError(response) {
  try {
    const payload = await response.json();
    if (typeof payload.detail === "string" && payload.detail.trim()) {
      return payload.detail;
    }
  } catch {
    // Use the safe fallback below.
  }

  return "Ejeren kunne ikke oprettes. Prøv igen.";
}

async function verifyBootstrapState() {
  try {
    const response = await fetch("/api/bootstrap/status", {
      credentials: "same-origin",
    });

    if (!response.ok) {
      return;
    }

    const payload = await response.json();

    if (!payload.bootstrap_required) {
      window.location.replace("/login");
    }
  } catch {
    // The form remains available if the status check temporarily fails.
  }
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  clearError();

  const displayName = displayNameInput.value.trim();
  const username = usernameInput.value.trim();
  const password = passwordInput.value;
  const confirmation = confirmPasswordInput.value;

  if (!displayName) {
    showError("Skriv dit navn.", displayNameInput);
    return;
  }

  if (!username) {
    showError("Vælg et brugernavn.", usernameInput);
    return;
  }

  if (password.length < 12) {
    showError(
      "Adgangskoden skal være mindst 12 tegn.",
      passwordInput,
    );
    return;
  }

  if (password !== confirmation) {
    showError(
      "Adgangskoderne er ikke ens.",
      confirmPasswordInput,
    );
    return;
  }

  setPending(true);

  try {
    const response = await fetch("/api/bootstrap/owner", {
      method: "POST",
      credentials: "same-origin",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        display_name: displayName,
        username,
        password,
      }),
    });

    if (response.status === 409) {
      window.location.replace("/login");
      return;
    }

    if (!response.ok) {
      showError(await readError(response));
      return;
    }

    const payload = await response.json();
    window.location.replace(payload.next || "/setup");
  } catch {
    showError(
      "Jarvis kunne ikke kontaktes. Kontrollér forbindelsen og prøv igen.",
    );
  } finally {
    setPending(false);
  }
});

verifyBootstrapState();
