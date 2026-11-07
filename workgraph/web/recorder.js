(() => {
  "use strict";
  const config = window.__workgraph;
  if (!config) return;
  const local = (value) => {
    try {
      const u = new URL(value, location.href);
      if (u.origin === location.origin && !u.pathname.startsWith(config.prefix))
        u.pathname = config.prefix + u.pathname.replace(/^\//, "");
      return u.href;
    } catch {
      return value;
    }
  };
  const originalFetch = window.fetch.bind(window);
  window.fetch = (input, init) =>
    originalFetch(
      typeof input === "string" || input instanceof URL
        ? local(input)
        : new Request(local(input.url), input),
      init,
    );
  const originalOpen = XMLHttpRequest.prototype.open;
  XMLHttpRequest.prototype.open = function (method, url, ...rest) {
    return originalOpen.call(this, method, local(url), ...rest);
  };
  for (const name of ["pushState", "replaceState"]) {
    const fn = history[name].bind(history);
    history[name] = (state, title, url) =>
      fn(state, title, url ? local(url) : url);
  }
  if (parent === window) return;
  let recording = false,
    asserting = false;
  const send = (message) =>
    parent.postMessage(
      { type: "workgraph-recorder", instance: config.instance, ...message },
      config.operator,
    );
  const locator = (el) => {
    if (el.dataset.testid) return { type: "testid", value: el.dataset.testid };
    if (el.getAttribute("aria-label"))
      return { type: "label", value: el.getAttribute("aria-label") };
    if (el.labels?.length)
      return { type: "label", value: el.labels[0].innerText.trim() };
    if (el.id) return { type: "css", value: "#" + CSS.escape(el.id) };
    if (el.matches("button,a,[role=button]"))
      return {
        type: "role",
        role: el.matches("a") ? "link" : "button",
        value: (el.innerText || el.getAttribute("title") || "")
          .trim()
          .slice(0, 180),
      };
    const parts = [];
    let node = el;
    while (node && node !== document.body && parts.length < 5) {
      let part = node.tagName.toLowerCase();
      const siblings = [...node.parentElement.children].filter(
        (x) => x.tagName === node.tagName,
      );
      if (siblings.length > 1)
        part += `:nth-of-type(${siblings.indexOf(node) + 1})`;
      parts.unshift(part);
      node = node.parentElement;
    }
    return { type: "css", value: parts.join(" > ") };
  };
  window.addEventListener("message", (event) => {
    if (
      event.source !== parent ||
      event.origin !== config.operator ||
      event.data?.type !== "workgraph-control"
    )
      return;
    recording = !!event.data.recording;
    asserting = !!event.data.asserting;
    document.documentElement.style.cursor = asserting ? "crosshair" : "";
    if (event.data.command === "reload") location.reload();
    send({ event: "ready" });
  });
  document.addEventListener(
    "click",
    (event) => {
      if (!recording) return;
      const el = asserting
        ? event.target
        : event.target.closest("button,a,input,select,textarea,[role=button]");
      if (!el) return;
      if (asserting) {
        event.preventDefault();
        event.stopImmediatePropagation();
        const text = (el.innerText || el.textContent || "")
          .trim()
          .slice(0, 240);
        const stable = el.closest("[data-testid],[id]") || el;
        if (text)
          send({
            event: "step",
            step: { action: "expect", locator: locator(stable), text },
          });
        return;
      }
      if (!el.matches("input,textarea,select"))
        send({
          event: "step",
          step: { action: "click", locator: locator(el) },
        });
    },
    true,
  );
  document.addEventListener(
    "input",
    (event) => {
      if (!recording || asserting) return;
      const el = event.target;
      if (!el.matches("input,textarea,select")) return;
      if (el.type === "password") {
        send({ event: "redacted" });
        return;
      }
      send({
        event: "step",
        step: {
          action: el.tagName === "SELECT" ? "select" : "fill",
          locator: locator(el),
          value: el.value.slice(0, 2000),
        },
      });
    },
    true,
  );
  document.addEventListener(
    "keydown",
    (event) => {
      if (
        recording &&
        !asserting &&
        event.key === "Enter" &&
        event.target.matches("input")
      )
        send({
          event: "step",
          step: {
            action: "press",
            locator: locator(event.target),
            value: "Enter",
          },
        });
    },
    true,
  );
  send({ event: "ready" });
})();
