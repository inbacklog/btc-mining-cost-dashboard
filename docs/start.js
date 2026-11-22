const absolute = path => new URL(path, document.baseURI).href;

try {
  const {mount} = await import("./generated/runtime/stlite.js");
  const response = await fetch("generated/wheels.json");
  if (!response.ok) throw Error("Dashboard bundle unavailable");
  const wheels = await response.json();
  mount({
    entrypoint: "app.py",
    pyodideUrl: absolute("generated/python/pyodide.mjs"),
    env: {DASHBOARD_PAGES_ROOT: absolute("./")},
    requirements: ["pandas", "requests", ...wheels.map(name => absolute("generated/" + name))],
    files: {
      "app.py": {url: absolute("generated/app.py")}
    },
    streamlitConfig: {"theme.base": "dark", "client.toolbarMode": "viewer"}
  }, document.getElementById("root"));
} catch (error) {
  document.getElementById("message").textContent = "Could not load the dashboard. Refresh this page to retry.";
  console.error(error);
}
