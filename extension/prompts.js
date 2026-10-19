// Prompt templates for the popup menu. Each action = a small form + a builder that writes a strong prompt.
(() => {
  const pascal = (s, fallback) =>
    String(s || "").replace(/[^a-z0-9 ]/gi, " ").split(/\s+/).filter(Boolean).slice(0, 3)
      .map((w) => w[0].toUpperCase() + w.slice(1)).join("") || fallback;

  const ONE_RUN = "Do it all in one Luau script run so I only approve once.";

  const actions = [
    {
      id: "model", icon: "🧱", title: "Generate model", hint: "Build a 3D model from parts",
      fields: [
        { id: "what", label: "What should it be?", type: "text", placeholder: "a medieval watchtower", required: true },
        { id: "style", label: "Style", type: "select", options: ["Low-poly", "Stylized cartoon", "Realistic", "Voxel / blocky", "Sci-fi"] },
        { id: "size", label: "Size", type: "select", options: ["Small (a prop)", "Medium", "Large (a building)"] },
        { id: "where", label: "Place it", type: "select", options: ["In front of the camera", "At the world origin", "Near what I have selected"] },
      ],
      build: (v) => {
        const place = {
          "In front of the camera": "Position it on the ground in front of the current Studio camera (workspace.CurrentCamera.CFrame).",
          "At the world origin": "Position it at (0, 0, 0), resting on the ground.",
          "Near what I have selected": "Position it next to the object I have selected (use the Selection service); if nothing is selected, use the camera view.",
        }[v.where];
        return `Create a Roblox model: ${v.what}.

Style: ${v.style}. Size: ${v.size}.
${place}

Requirements:
- Build it from basic Parts only (Block, Cylinder, Ball, Wedge, CornerWedge). No asset IDs and no Toolbox or free-model assets.
- Use good proportions, a consistent color palette and fitting Materials. Add small details so it doesn't look like a plain box.
- Put everything in ONE Model named "${pascal(v.what, "GeneratedModel")}", set its PrimaryPart, and anchor every part.
- ${ONE_RUN}`;
      },
    },
    {
      id: "animation", icon: "🎬", title: "Generate animation", hint: "Make something move",
      fields: [
        { id: "what", label: "What should move, and how?", type: "text", placeholder: "a door that swings open when touched", required: true },
        { id: "target", label: "Animate", type: "select", options: ["What I have selected", "A new simple object", "A character rig (R15)", "A character rig (R6)"] },
        { id: "kind", label: "Type", type: "select", options: ["One-shot (plays once)", "Looping", "Triggered by the player"] },
        { id: "secs", label: "Length (seconds)", type: "select", options: ["1", "2", "3", "5", "10"] },
      ],
      build: (v) => `Create an animation: ${v.what}.

Animate: ${v.target}. Type: ${v.kind}. Length: about ${v.secs} seconds.
${v.target === "What I have selected" ? "Use the object I have selected in Studio (Selection service); if nothing is selected, make a simple placeholder to animate." : ""}

Requirements:
- Build it in code so it works without uploading an Animation asset: use TweenService and/or Motor6D / CFrame changes in a Script (or a LocalScript if it should only play on one player's screen).
- Put the script where it belongs (inside the animated model if there is one, otherwise ServerScriptService) and name it clearly.
- Say in one or two sentences how it is triggered, and add the trigger (for example a ProximityPrompt or a Touched event) if the request needs one.
- ${ONE_RUN}`.replace(/\n\n\n/g, "\n\n"),
    },
    {
      id: "ui", icon: "🖼️", title: "Generate UI", hint: "Menus, HUDs, shops",
      fields: [
        { id: "what", label: "What should it show?", type: "text", placeholder: "a shop with 6 item cards and a coin counter", required: true },
        { id: "kind", label: "Kind", type: "select", options: ["HUD", "Main menu", "Shop", "Inventory", "Dialog / popup", "Settings", "Scoreboard"] },
        { id: "theme", label: "Theme", type: "select", options: ["Dark modern", "Light clean", "Neon / cyber", "Fantasy / wood", "Cartoon"] },
      ],
      build: (v) => `Create a Roblox UI: ${v.what}.

Kind: ${v.kind}. Theme: ${v.theme}. It must work on phone and desktop.

Requirements:
- One ScreenGui named "${pascal(v.what, "GeneratedUI")}" in StarterGui with ResetOnSpawn = false.
- Use Scale-based sizing with UIAspectRatioConstraint / UIScale where needed, never fixed-pixel layouts. Use UICorner, UIStroke, UIPadding and UIListLayout / UIGridLayout for tidy spacing, and TextScaled text with a UITextSizeConstraint.
- Add a LocalScript for the interactions (open / close, hover and click feedback, simple tween animations).
- Give every element a clear name so I can edit it later. No asset IDs.
- ${ONE_RUN}`,
    },
    {
      id: "script", icon: "📜", title: "Generate script", hint: "Gameplay code",
      fields: [
        { id: "what", label: "What should it do?", type: "text", placeholder: "a sprint system with a stamina bar", required: true },
        { id: "kind", label: "Kind", type: "select", options: ["Script (server)", "LocalScript (client)", "ModuleScript"] },
        { id: "where", label: "Put it in", type: "select", options: ["ServerScriptService", "StarterPlayerScripts", "ReplicatedStorage", "What I have selected"] },
      ],
      build: (v) => `Write a Roblox ${v.kind}: ${v.what}.

Put it in: ${v.where}.
Keep it clean, comment what isn't obvious, handle edge cases (a player leaving, missing objects) and avoid memory leaks. Tell me in one sentence how to use it.
${ONE_RUN}`,
    },
    {
      id: "map", icon: "🏔️", title: "Generate map", hint: "Terrain and scenery",
      fields: [
        { id: "what", label: "What kind of place?", type: "text", placeholder: "a snowy mountain village", required: true },
        { id: "size", label: "Size", type: "select", options: ["Small (256 studs)", "Medium (512 studs)", "Large (1024 studs)"] },
        { id: "mood", label: "Mood", type: "select", options: ["Sunny day", "Sunset", "Night", "Foggy", "Stormy"] },
      ],
      build: (v) => `Build a Roblox map: ${v.what}.

Size: ${v.size}. Mood: ${v.mood}.

Requirements:
- Use workspace.Terrain (FillBlock, FillBall, FillCylinder, FillWedge, WriteVoxels) for ground, hills, water and cliffs, with sensible Materials (grass, rock, sand, snow, water).
- Set Lighting, Atmosphere and the sky to match the mood.
- Add a few props from basic Parts only (trees, rocks, buildings), grouped in a Folder named "${pascal(v.what, "Map")}Props".
- Prefer one Luau script run; if that would be too long, split it into at most three. Don't delete existing terrain without telling me.`,
    },
    {
      id: "fix", icon: "🛠️", title: "Fix a bug", hint: "Find and repair",
      fields: [
        { id: "what", label: "What's going wrong?", type: "text", placeholder: "my door script never opens", required: true },
      ],
      build: (v) => `Find and fix this problem in my game: ${v.what}.

First read the relevant scripts or objects (use my selection if I have something selected), in one read step. Then fix it with the smallest change that works, and explain the cause and the fix in two sentences.`,
    },
    {
      id: "custom", icon: "✨", title: "Anything else", hint: "Your own request",
      fields: [{ id: "what", label: "What should I build?", type: "text", placeholder: "describe it in your own words", required: true, long: true }],
      build: (v) => v.what,
    },
  ];

  globalThis.GS_ACTIONS = actions;
  globalThis.GS_PASCAL = pascal;
})();
