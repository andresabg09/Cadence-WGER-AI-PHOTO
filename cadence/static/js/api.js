// Fetch helpers shared across pages. Relative URLs on purpose - nginx
// exposes this service under /cadence/, and absolute paths would resolve
// against the domain root instead of that prefix (see nginx.conf).

async function apiGet(path) {
  const response = await fetch(path);
  if (!response.ok) throw new Error(await safeText(response));
  return response.json();
}

async function apiPost(path, body, { isFormData = false } = {}) {
  const response = await fetch(path, {
    method: 'POST',
    headers: isFormData ? undefined : { 'Content-Type': 'application/json' },
    body: isFormData ? body : JSON.stringify(body),
  });
  if (!response.ok) throw new Error(await safeText(response));
  return response.json();
}

async function apiDelete(path) {
  const response = await fetch(path, { method: 'DELETE' });
  if (!response.ok) throw new Error(await safeText(response));
  return response.json();
}

async function safeText(response) {
  try {
    const data = await response.json();
    return data.detail || JSON.stringify(data);
  } catch {
    return response.statusText;
  }
}

function showToast(message, kind = 'error') {
  const toast = document.createElement('div');
  toast.className = `toast ${kind}`;
  toast.textContent = message;
  document.body.appendChild(toast);
  setTimeout(() => toast.remove(), 4000);
}
