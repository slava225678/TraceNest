"use strict";

const form = document.getElementById("status-form");

if (form) {
  const fields = document.getElementById("status-fields");
  const keyInput = document.getElementById("api-key");
  const statusInput = document.getElementById("new-status");
  const feedback = document.getElementById("status-feedback");
  fields.disabled = false;

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const key = keyInput.value;
    const status = statusInput.value;
    keyInput.value = "";
    fields.disabled = true;
    feedback.textContent = "Saving…";
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), 10000);
    try {
      const response = await fetch(form.dataset.endpoint, {
        method: "PATCH",
        headers: {
          "Content-Type": "application/json",
          "X-API-Key": key,
        },
        body: JSON.stringify({ status }),
        credentials: "omit",
        redirect: "error",
        signal: controller.signal,
      });
      if (response.ok) {
        window.location.reload();
        return;
      }
      if (response.status === 401) {
        feedback.textContent = "Incorrect API key. Please try again.";
      } else {
        feedback.textContent = `Could not save (HTTP ${response.status}).`;
      }
    } catch {
      feedback.textContent =
        "Could not confirm the update. Refresh to check the current status.";
    } finally {
      clearTimeout(timer);
      fields.disabled = false;
    }
  });
}
