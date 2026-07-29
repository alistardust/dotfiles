// Extension: confirmation-gate
//
// Prevents file edits until the user has explicitly confirmed a proposed
// approach. The model must discuss first; edit/create and mutating bash stay
// locked until confirmation arrives.
//
// ---------------------------------------------------------------------------
// v2 design notes (what changed and why)
//
// 1. The grant is STICKY. v1 reset it on every user message that did not match
//    the confirm regex, so a mid-task "continue" or a correction dropped the
//    agent back into DISCUSSION_ONLY with no way to recover except repeating a
//    magic word. Multi-step work was effectively impossible. The grant now
//    persists until explicitly revoked.
//
// 2. ask_user responses count. v1 only observed typed messages via
//    onUserPromptSubmitted, so a form confirmation could never unlock the gate.
//    That directly contradicted the global instructions, which mandate ask_user
//    for approval and forbid plain-text asks: following one rule guaranteed
//    violating the other. An onPostToolUse handler now reads ask_user results.
//
// 3. The bash escape is materially narrower. v1 missed heredocs, bare
//    redirects, interpreter-stdin forms, and most destructive git verbs.
//
// 4. The injected STATE banner reports the real flag. v1 asserted
//    DISCUSSION_ONLY on every prompt including the one that had just granted
//    permission, so the model saw the context contradict the actual state.
//
// 5. request_edit_permission no longer revokes. In v1 its handler set the flag
//    to false, so calling the tool the extension itself told you to call
//    destroyed an existing grant.
//
// 6. Explicit revocation exists, and takes precedence over confirmation.
//
// 7. State persists to disk per session, so an extension-process restart (for
//    example after context compaction) does not silently strand the gate in a
//    locked state that no phrasing can clear.
//
// ---------------------------------------------------------------------------
// REMAINING LIMITATIONS (read before trusting this as a control)
//
// - This is not a sandbox. It is a speed bump against accidental edits, not a
//   defence against deliberate circumvention. An unusual interpreter, an editor
//   invocation, or a compiled helper can still write. Real enforcement needs
//   OS-level controls.
// - Stickiness is a deliberate tradeoff: one confirmation covers subsequent
//   edits until revoked. Per-action confirmation for destructive and production
//   operations is enforced by instruction, not by this gate.
// - Confirm and revoke matching is regex over prose, so it misfires both ways.
//   Revoke wins ties, and unmatched input leaves the current state unchanged.
// - `2>file` style stderr redirection is not gated; it is a write, but gating it
//   was too noisy to be worth it.
// - Cloud provider CLIs (aws, az, gcloud) are not gated here. Their verb
//   surfaces are too large to pattern-match reliably without constant false
//   positives.
// ---------------------------------------------------------------------------

import { joinSession } from "@github/copilot-sdk/extension";
import { readFileSync, writeFileSync, mkdirSync } from "node:fs";
import { dirname, join } from "node:path";
import { homedir } from "node:os";

// Runtime state deliberately lives outside the extension directory. That
// directory is a symlink into the dotfiles repo, so writing here would drop an
// untracked state.json into version control on every session.
const STATE_FILE = join(homedir(), ".copilot", "confirmation-gate-state.json");
const STATE_TTL_MS = 12 * 60 * 60 * 1000;

// Deliberately aligned with the global instructions, which state that "sounds
// good", "ok", and approval given earlier for a different step are NOT
// confirmation. Keep this list narrow: an unambiguous affirmative only.
const CONFIRM_PATTERNS = [
  /\b(yes|yep|yeah|go ahead|proceed|confirm(ed)?|approve[ds]?|do it|make the change|lgtm|ship it|build it|please do)\b/i,
];

// Revocation is checked first and wins any tie. False positives here fail
// closed, which is the correct direction for a safety control.
const REVOKE_PATTERNS = [
  /\b(stop|wait|hold on|hold up|abort|cancel|halt|never ?mind|not yet|don'?t|do not|back out|stand down|undo|revert)\b/i,
];

// Tokens that, if present anywhere in an ask_user result, block auto-grant.
// Form results may echo unselected choices, so a result containing both an
// approve option and a decline option is treated as ambiguous, not as consent.
const FORM_DECLINE_PATTERNS = [
  /\b(decline[ds]?|cancel(l?ed)?|abort(ed)?|reject(ed)?|request changes|skip|no thanks|not now)\b/i,
];

const FORM_AFFIRM_PATTERNS = [
  /\b(yes|approve[ds]?|approval|proceed|confirm(ed)?|accept(ed)?|go ahead|commit and push)\b/i,
  /\byes[_-]\w+/i,
];

const MUTATING_TOOLS = new Set(["edit", "create"]);

const MUTATING_BASH_PATTERNS = [
  // Redirection into a file. The lookbehind skips fd-qualified forms such as
  // `2>`, and the trailing class skips `>&2` and `>/dev/null`.
  /(?<![0-9<>&])>>?\s*(?!\/dev\/(null|stdout|stderr))[^|&;<>\s]/,

  // Heredocs. The body is content bound either for a file or for an
  // interpreter's stdin; both are write vectors. This is the hole that let
  // `python3 - <<'EOF'` through in v1.
  /<<-?\s*['"]?[A-Za-z_][A-Za-z0-9_]*/,

  // Interpreters taking a program from stdin or an inline flag.
  /\b(python[0-9.]*|node|ruby|perl|php|deno|bun|osascript)\s+(-c|-e|-)(\s|$)/,

  // In-place editing.
  /\bsed\s+(-[a-zA-Z]*i|--in-place)/,
  /\b(perl|ruby)\s+[^|;]*-i/,
  /\b(ed|ex|vim?|nano|emacs)\s+[^|;]*\s-\S*[cs]\b/,

  // Filesystem mutation.
  /\b(tee|mv|cp|rm|rmdir|mkdir|touch|ln|dd|truncate|install|chmod|chown|chgrp|chflags|shred|patch|rsync|unzip|xattr)\b/,
  /\btar\s+[^|;]*-[a-zA-Z]*x/,

  // Git verbs that change the worktree, the index, or history.
  /\bgit\s+(add|commit|push|merge|rebase|cherry-pick|revert|am|apply|stash|clean|rm|mv|filter-branch|gc|prune|fetch\s+--prune)\b/,
  /\bgit\s+(checkout|switch|restore|reset)\b/,
  /\bgit\s+worktree\s+(add|remove|move|prune|repair)\b/,
  /\bgit\s+(branch|tag)\s+(-[dDfmM]|--delete|--force|--move)/,
  /\bgit\s+config\s+(?!--get|--list|-l\b)/,

  // Package managers writing into the project or the environment.
  /\b(npm|pnpm|yarn|bun)\s+(install|add|remove|uninstall|link|ci)\b/,
  /\b(pip[0-9.]*|uv|poetry|pipx)\s+(install|add|remove|uninstall|sync)\b/,
  /\b(cargo|go)\s+(install|add|get|mod\s+tidy)\b/,
  /\bbrew\s+(install|uninstall|upgrade|link|unlink)\b/,

  // Infrastructure applies. Covered by instruction as well; gated here as
  // defence in depth because the blast radius is the largest on this machine.
  /\b(terraform|tofu)\s+(apply|destroy|import|taint|untaint)\b/,
  /\bterraform\s+state\s+(rm|mv|push|replace-provider)\b/,
  /\bkubectl\s+(apply|create|delete|patch|replace|scale|drain|cordon|uncordon|edit|exec|rollout|annotate|label)\b/,
  /\bansible-playbook\b(?![^|;]*--check)/,
];

let confirmationGranted = false;
let pendingPermission = null;
let activeSessionId = null;

function loadState(sessionId) {
  try {
    const raw = JSON.parse(readFileSync(STATE_FILE, "utf8"));
    if (raw.sessionId !== sessionId) return false;
    if (Date.now() - (raw.updatedAt || 0) > STATE_TTL_MS) return false;
    return raw.granted === true;
  } catch {
    return false;
  }
}

function saveState(sessionId) {
  try {
    mkdirSync(dirname(STATE_FILE), { recursive: true });
    writeFileSync(
      STATE_FILE,
      JSON.stringify({
        sessionId,
        granted: confirmationGranted,
        updatedAt: Date.now(),
      }),
    );
  } catch {
    // Persistence is a convenience. Losing it degrades to in-memory state,
    // which fails closed, so a write failure is never escalated.
  }
}

function setGrant(value, sessionId) {
  confirmationGranted = value;
  if (sessionId) saveState(sessionId);
}

function isMutatingBash(cmd) {
  return MUTATING_BASH_PATTERNS.some((p) => p.test(cmd));
}

function stateBanner() {
  return confirmationGranted
    ? "STATE: The user has confirmed your approach. edit/create and mutating " +
        "bash are unlocked for the current line of work. This grant persists " +
        "until the user revokes it. It authorises the work you described, not " +
        "arbitrary new changes: if the scope shifts materially, describe the " +
        "new scope and confirm again. Destructive, production, and " +
        "shared-infrastructure actions still require their own confirmation."
    : "STATE: You are in DISCUSSION_ONLY mode until the user explicitly " +
        "confirms your proposed approach. Do not call edit/create tools, and " +
        "do not write files through bash. Propose changes, then wait.";
}

const session = await joinSession({
  hooks: {
    onSessionStart: async (input, invocation) => {
      activeSessionId = invocation?.sessionId ?? null;
      confirmationGranted = activeSessionId ? loadState(activeSessionId) : false;
      return { additionalContext: stateBanner() };
    },

    onUserPromptSubmitted: async (input, invocation) => {
      const msg = input.prompt || "";
      const sid = invocation?.sessionId ?? activeSessionId;
      activeSessionId = sid;

      // Revocation is evaluated first and wins ties.
      if (REVOKE_PATTERNS.some((p) => p.test(msg))) {
        setGrant(false, sid);
        pendingPermission = null;
      } else if (CONFIRM_PATTERNS.some((p) => p.test(msg))) {
        setGrant(true, sid);
        pendingPermission = null;
      }
      // Otherwise the existing grant is left alone. This is the v1 fix: an
      // unrelated message must not silently revoke consent mid-task.

      return { additionalContext: stateBanner() };
    },

    onPostToolUse: async (input, invocation) => {
      if (input.toolName !== "ask_user") return;

      const text = String(input.toolResult?.textResultForLlm || "");
      if (!text) return;

      const sid = invocation?.sessionId ?? activeSessionId;

      if (FORM_DECLINE_PATTERNS.some((p) => p.test(text))) {
        // Ambiguous or negative. Do not grant, and do not revoke an existing
        // grant either: an unrelated form should not cancel prior consent.
        return;
      }
      if (FORM_AFFIRM_PATTERNS.some((p) => p.test(text))) {
        setGrant(true, sid);
      }
    },

    onPreToolUse: async (input) => {
      if (input.toolName === "bash") {
        const cmd = String(input.toolArgs?.command || "");
        if (!isMutatingBash(cmd)) {
          return { permissionDecision: "allow" };
        }
        if (confirmationGranted) {
          return { permissionDecision: "allow" };
        }
        return {
          permissionDecision: "deny",
          permissionDecisionReason:
            "BLOCKED: this bash command appears to write files or change repo " +
            "state, and the user has not confirmed an approach. Describe what " +
            "you intend to change and why, then wait for confirmation. Do not " +
            "look for a phrasing that evades this check: routing around a " +
            "safety control is itself a violation.",
        };
      }

      if (!MUTATING_TOOLS.has(input.toolName)) {
        return { permissionDecision: "allow" };
      }

      if (confirmationGranted) {
        return { permissionDecision: "allow" };
      }

      return {
        permissionDecision: "deny",
        permissionDecisionReason:
          "BLOCKED: you attempted to edit/create a file without user " +
          "confirmation. You are in DISCUSSION_ONLY mode. Present your " +
          "proposed approach and wait for the user to say 'yes', 'go ahead', " +
          "'proceed', or similar. An ask_user form answer also counts. Do not " +
          "write the file through bash instead.",
      };
    },
  },

  tools: [
    {
      name: "request_edit_permission",
      description:
        "Call this BEFORE any file edit to describe your proposed changes to " +
        "the user. After calling this, STOP and wait for user confirmation. " +
        "Do not call edit/create until the user confirms.",
      parameters: {
        type: "object",
        properties: {
          files: {
            type: "string",
            description: "Comma-separated list of files to be modified",
          },
          description: {
            type: "string",
            description: "What changes will be made and why",
          },
        },
        required: ["files", "description"],
      },
      handler: async (args) => {
        pendingPermission = {
          files: args.files,
          description: args.description,
          timestamp: Date.now(),
        };
        // Deliberately does NOT revoke an existing grant. In v1 it did, so
        // calling this tool mid-task locked the gate the user had just opened.
        return (
          "Permission request noted. STOP. Do not call edit or create tools. " +
          "Wait for the user to respond with explicit confirmation."
        );
      },
    },
  ],
});
