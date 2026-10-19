// Shared by the popup, the background worker and the content scripts.
globalThis.GS_SITES = [
  { id: "claude",   name: "Claude",   host: "claude.ai",         match: "https://claude.ai/*",         newUrl: "https://claude.ai/new",         newPath: "/new", color: "#d97757" },
  { id: "chatgpt",  name: "ChatGPT",  host: "chatgpt.com",       match: "https://chatgpt.com/*",       newUrl: "https://chatgpt.com/",          newPath: "/",    color: "#10a37f" },
  { id: "deepseek", name: "DeepSeek", host: "chat.deepseek.com", match: "https://chat.deepseek.com/*", newUrl: "https://chat.deepseek.com/",    newPath: "/",    color: "#4d6bfe" },
  { id: "gemini",   name: "Gemini",   host: "gemini.google.com", match: "https://gemini.google.com/*", newUrl: "https://gemini.google.com/app", newPath: "/app", color: "#8ab4f8" },
];
