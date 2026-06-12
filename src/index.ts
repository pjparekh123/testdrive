#!/usr/bin/env node
import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import { z } from "zod";
import {
  OBLIQUE_STRATEGIES,
  PROPHECY_TEMPLATES,
  PROPHECY_WORDS,
  CREATIVE_CONSTRAINTS,
  DEV_FORTUNES,
  PERSPECTIVE_INVERSIONS,
  COSMIC_BRIDGES,
} from "./data.js";

// Seeded pseudo-random so the same seed always yields the same result,
// but different seeds give different results (useful for "daily" fortunes).
function seededRand(seed: number): () => number {
  let s = seed;
  return () => {
    s = (s * 1664525 + 1013904223) & 0xffffffff;
    return (s >>> 0) / 0xffffffff;
  };
}

function pickRandom<T>(arr: T[], rand: () => number): T {
  return arr[Math.floor(rand() * arr.length)];
}

function dailySeed(): number {
  const d = new Date();
  return d.getFullYear() * 10000 + (d.getMonth() + 1) * 100 + d.getDate();
}

function momentSeed(): number {
  return Math.floor(Date.now() / 1000);
}

function buildProphecy(rand: () => number): string {
  const { adjectives, nouns, outcomes } = PROPHECY_WORDS;
  const template = pickRandom(PROPHECY_TEMPLATES, rand);
  return template
    .replace("{adjective}", pickRandom(adjectives, rand))
    .replace("{adjective2}", pickRandom(adjectives, rand))
    .replace("{noun}", pickRandom(nouns, rand))
    .replace("{noun2}", pickRandom(nouns, rand))
    .replace("{outcome}", pickRandom(outcomes, rand));
}

const server = new McpServer({
  name: "chaos-oracle",
  version: "1.0.0",
});

// ─── consult_oracle ───────────────────────────────────────────────────────────
server.tool(
  "consult_oracle",
  "Ask the Chaos Oracle any question. Receive an ancient prophecy, then a grounded, practical interpretation of what it might actually mean for your situation.",
  { question: z.string().describe("The question or situation you want guidance on") },
  async ({ question }) => {
    const rand = seededRand(momentSeed() ^ question.split("").reduce((a, c) => a + c.charCodeAt(0), 0));
    const prophecy = buildProphecy(rand);

    // Pick an interpretation angle
    const angles = [
      "The oracle suggests you already sense the answer — the prophecy reflects an internal tension, not an external blocker.",
      "The imagery points to a hidden assumption that may be worth questioning before proceeding.",
      "The oracle highlights a transition moment — the difficulty may be that you're between two states and trying to operate as if you're firmly in one.",
      "The core of the prophecy: the 'problem' and the 'solution' may be the same thing viewed from different angles.",
      "The oracle points toward the thing you've been avoiding because it seems too simple or too radical.",
    ];
    const interpretation = pickRandom(angles, rand);
    const strategy = pickRandom(OBLIQUE_STRATEGIES, rand);

    return {
      content: [
        {
          type: "text",
          text: [
            `🔮 **THE ORACLE SPEAKS:**`,
            ``,
            `*"${prophecy}"*`,
            ``,
            `---`,
            ``,
            `**Practical interpretation:**`,
            interpretation,
            ``,
            `**Oblique companion card:**`,
            `*"${strategy}"*`,
            ``,
            `---`,
            `*Your question: "${question}"*`,
          ].join("\n"),
        },
      ],
    };
  }
);

// ─── oblique_strategy ─────────────────────────────────────────────────────────
server.tool(
  "oblique_strategy",
  "Draw an Oblique Strategy card — a technique pioneered by Brian Eno and Peter Schmidt for breaking creative deadlock. Each card offers a lateral prompt to shift your perspective when you're stuck.",
  {
    context: z.string().optional().describe("Optional: briefly describe what you're stuck on, to get a more resonant card"),
    draw_count: z.number().min(1).max(5).optional().default(1).describe("How many cards to draw (1-5)"),
  },
  async ({ context, draw_count = 1 }) => {
    const seed = context
      ? momentSeed() ^ context.split("").reduce((a, c) => a + c.charCodeAt(0), 0)
      : momentSeed();
    const rand = seededRand(seed);

    const cards: string[] = [];
    const used = new Set<number>();
    while (cards.length < draw_count) {
      const idx = Math.floor(rand() * OBLIQUE_STRATEGIES.length);
      if (!used.has(idx)) {
        used.add(idx);
        cards.push(OBLIQUE_STRATEGIES[idx]);
      }
    }

    const lines = [`🃏 **OBLIQUE STRATEG${draw_count > 1 ? "IES" : "Y"}**`, ``];
    cards.forEach((card, i) => {
      lines.push(`${draw_count > 1 ? `**Card ${i + 1}:** ` : ""}*"${card}"*`);
      if (draw_count > 1 && i < draw_count - 1) lines.push(``);
    });

    if (context) {
      lines.push(``, `---`, `*Drawn for: "${context}"*`);
    }

    return { content: [{ type: "text", text: lines.join("\n") }] };
  }
);

// ─── flip_perspective ─────────────────────────────────────────────────────────
server.tool(
  "flip_perspective",
  "Invert a problem to find what you might be missing. Describes the situation from the opposite angle — what if the obstacle IS the path? What if the bug is honest feedback? What if the constraint is actually the feature?",
  { situation: z.string().describe("The problem, blocker, or situation you want to flip") },
  async ({ situation }) => {
    const rand = seededRand(momentSeed() ^ situation.length * 31);
    const lower = situation.toLowerCase();

    // Try to find a matching inversion pattern
    const match = PERSPECTIVE_INVERSIONS.find((p) => lower.includes(p.pattern));
    const thematicFlip = match?.inversion ?? null;

    // Always generate a structural flip
    const structuralFlips = [
      `**The reversal:** What if the goal is not to eliminate "${situation.trim()}" but to understand what it's protecting?`,
      `**The reversal:** What if "${situation.trim()}" is not the problem to solve but the signal to follow?`,
      `**The reversal:** What if the correct response to "${situation.trim()}" is to stop trying to respond to it?`,
      `**The reversal:** What if the difficulty of "${situation.trim()}" is proportional to how valuable the answer will be?`,
      `**The reversal:** What if removing "${situation.trim()}" would reveal a worse problem that it's currently masking?`,
    ];

    const structural = pickRandom(structuralFlips, rand);
    const constraint = pickRandom(CREATIVE_CONSTRAINTS, rand);

    const lines = [
      `🔄 **PERSPECTIVE FLIP**`,
      ``,
      structural,
      ``,
    ];

    if (thematicFlip) {
      lines.push(`**Thematic inversion:**`, thematicFlip, ``);
    }

    lines.push(
      `**Creative constraint to try:**`,
      `*"${constraint}"*`,
      ``,
      `---`,
      `*Situation: "${situation}"*`
    );

    return { content: [{ type: "text", text: lines.join("\n") }] };
  }
);

// ─── cosmic_coincidence ───────────────────────────────────────────────────────
server.tool(
  "cosmic_coincidence",
  "Find the unexpected connection between two seemingly unrelated concepts. Useful for cross-domain insight, analogy-based problem solving, and spotting hidden patterns.",
  {
    concept_a: z.string().describe("First concept, domain, or thing"),
    concept_b: z.string().describe("Second concept, domain, or thing — ideally something unrelated"),
  },
  async ({ concept_a, concept_b }) => {
    const seed = (concept_a + concept_b).split("").reduce((a, c) => a + c.charCodeAt(0), 0);
    const rand = seededRand(seed ^ momentSeed());

    const bridge = pickRandom(COSMIC_BRIDGES, rand);
    const strategy = pickRandom(OBLIQUE_STRATEGIES, rand);

    // Generate an application of this insight
    const applications = [
      `Apply this to your work: treat **${concept_a}** as a teacher and **${concept_b}** as the student — what does the teacher already know that the student needs?`,
      `Apply this: if you solved a hard problem in **${concept_b}**, what technique from that solution could transplant into **${concept_a}**?`,
      `Apply this: model **${concept_a}** using the vocabulary of **${concept_b}**. What becomes visible that was hidden?`,
      `Apply this: find the "failure mode" in **${concept_b}** — that failure mode likely exists latently in **${concept_a}** too.`,
      `Apply this: the most elegant solution in **${concept_b}** is probably the right shape for the problem in **${concept_a}**.`,
    ];

    const application = pickRandom(applications, rand);

    return {
      content: [
        {
          type: "text",
          text: [
            `✨ **COSMIC COINCIDENCE: ${concept_a.toUpperCase()} ↔ ${concept_b.toUpperCase()}**`,
            ``,
            `**The hidden connection:**`,
            bridge,
            ``,
            `**How to use this:**`,
            application,
            ``,
            `**Oblique prompt to deepen the insight:**`,
            `*"${strategy}"*`,
          ].join("\n"),
        },
      ],
    };
  }
);

// ─── fortune_for_devs ─────────────────────────────────────────────────────────
server.tool(
  "fortune_for_devs",
  "Draw your developer fortune for the current moment — a short, cryptic-but-true piece of wisdom seeded by the current time. Changes every few minutes.",
  {
    mood: z.enum(["hopeful", "frustrated", "stuck", "shipping", "reviewing", "any"]).optional().default("any").describe("Your current mood or activity"),
  },
  async ({ mood = "any" }) => {
    const moodSeed = mood === "any" ? 0 : mood.charCodeAt(0) * 7;
    const rand = seededRand(momentSeed() + moodSeed);

    const fortune = pickRandom(DEV_FORTUNES, rand);
    const lucky = Math.floor(rand() * 9000) + 1000;
    const luckyLang = pickRandom(
      ["TypeScript", "Rust", "Go", "Python", "Clojure", "Elixir", "OCaml", "Haskell", "Zig", "Gleam"],
      rand
    );
    const luckyWord = pickRandom(
      ["refactor", "simplify", "delete", "rename", "extract", "inline", "compose", "invert", "cache", "defer"],
      rand
    );

    return {
      content: [
        {
          type: "text",
          text: [
            `🥠 **YOUR DEVELOPER FORTUNE**`,
            ``,
            `*"${fortune}"*`,
            ``,
            `---`,
            `🔢 Lucky port: **${lucky}**`,
            `💻 Lucky language: **${luckyLang}**`,
            `✨ Lucky word: **${luckyWord}**`,
            mood !== "any" ? `\n*Fortune calibrated for mood: ${mood}*` : "",
          ]
            .join("\n")
            .trim(),
        },
      ],
    };
  }
);

// ─── random_constraint ────────────────────────────────────────────────────────
server.tool(
  "random_constraint",
  "Generate a creative constraint to break you out of a rut. Constraints force lateral thinking — they're not obstacles, they're lenses. Each call returns a fresh constraint seeded by the current moment.",
  {
    task: z.string().optional().describe("Optional: what are you working on? The constraint will be framed around it."),
    intensity: z.enum(["gentle", "moderate", "chaotic"]).optional().default("moderate").describe("How disruptive should the constraint be?"),
  },
  async ({ task, intensity = "moderate" }) => {
    const seed = momentSeed() ^ (task?.length ?? 0) * 13 ^ intensity.charCodeAt(0);
    const rand = seededRand(seed);

    // Filter by intensity: chaotic draws from full list, gentle draws from first half, moderate from middle
    let pool = [...CREATIVE_CONSTRAINTS];
    if (intensity === "gentle") pool = pool.slice(0, Math.floor(pool.length * 0.5));
    else if (intensity === "moderate") pool = pool.slice(0, Math.floor(pool.length * 0.8));

    const constraint = pickRandom(pool, rand);
    const bonus = pickRandom(OBLIQUE_STRATEGIES, rand);

    const lines = [
      `🎲 **RANDOM CONSTRAINT** *(${intensity})*`,
      ``,
      `**Your constraint:**`,
      `*"${constraint}"*`,
    ];

    if (task) {
      lines.push(``, `**Applied to your task:** "${task}"`);
      lines.push(`Take 10 minutes to attack the task *only* through the lens of this constraint. Ignore it afterward if you like — but try it first.`);
    }

    lines.push(``, `**Bonus oblique prompt:**`, `*"${bonus}"*`);

    return { content: [{ type: "text", text: lines.join("\n") }] };
  }
);

// ─── Start ────────────────────────────────────────────────────────────────────
async function main() {
  const transport = new StdioServerTransport();
  await server.connect(transport);
  console.error("Chaos Oracle MCP server running on stdio");
}

main().catch((err) => {
  console.error("Fatal error:", err);
  process.exit(1);
});
