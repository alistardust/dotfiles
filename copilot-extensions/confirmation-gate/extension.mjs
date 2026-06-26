// Extension: confirmation-gate
// Physically prevents file edits without explicit user confirmation.
// The model MUST discuss its approach and receive a clear "yes"/"go ahead"/etc.
// before edit/create tools are unlocked. Denied attempts get a reason message
// telling the model to discuss first.
//
// KNOWN LIMITATIONS:
// - Bash escape: creative shell commands (python -c, node -e, etc.) can write
//   files without using the edit/create tools. The mutating-bash regex catches
//   common patterns but not all. True sandboxing would require OS-level enforcement.
// - False positive on confirmation: if the user says "yes" to an unrelated question,
//   edits become unlocked for that turn. Mitigated by per-turn reset.
// - Multi-tool batching: if the model batches request_edit_permission + edit in one
//   turn, the gate blocks it (unlock only happens after the NEXT user message).

import { joinSession } from "@github/copilot-sdk/extension";

const CONFIRM_PATTERNS = [
  /\b(yes|go ahead|proceed|confirmed?|approved?|do it|make the change|lgtm|ship it|build it)\b/i,
];

const MUTATING_TOOLS = new Set(["edit", "create"]);

const MUTATING_BASH =
  /\b(sed\s+-i|tee\s|mv\s|cp\s.*[^-]|rm\s|mkdir\s|cat\s*>|echo\s.*>|printf\s.*>|patch\s|git\s+(add|commit|push|checkout|merge|rebase)|python[3]?\s+-c\s.*open\(|node\s+-e\s.*fs\.)/;

let confirmationGranted = false;
let pendingPermission = null;

const session = await joinSession({
  hooks: {
    onUserPromptSubmitted: async (input) => {
      const msg = input.prompt || "";

      if (pendingPermission && CONFIRM_PATTERNS.some((p) => p.test(msg))) {
        confirmationGranted = true;
      } else if (CONFIRM_PATTERNS.some((p) => p.test(msg))) {
        confirmationGranted = true;
      } else {
        confirmationGranted = false;
      }
      pendingPermission = null;

      return {
        additionalContext:
          "STATE: You are in DISCUSSION_ONLY mode until the user explicitly " +
          "confirms your proposed approach. Do not call edit/create tools. " +
          "Propose changes, then wait for confirmation.",
      };
    },

    onPreToolUse: async (input) => {
      // Allow read-only tools unconditionally
      if (!MUTATING_TOOLS.has(input.toolName)) {
        if (input.toolName === "bash") {
          const cmd = String(input.toolArgs?.command || "");
          if (!MUTATING_BASH.test(cmd)) {
            return { permissionDecision: "allow" };
          }
          // Mutating bash detected
          if (confirmationGranted) {
            return { permissionDecision: "allow" };
          }
          return {
            permissionDecision: "deny",
            permissionDecisionReason:
              "BLOCKED: This bash command appears to modify files, but you have " +
              "not received user confirmation. Discuss your approach first, then " +
              "wait for the user to confirm before making changes.",
          };
        }
        return { permissionDecision: "allow" };
      }

      // Mutating tool (edit/create)
      if (confirmationGranted) {
        return { permissionDecision: "allow" };
      }

      return {
        permissionDecision: "deny",
        permissionDecisionReason:
          "BLOCKED: You attempted to edit/create a file without user confirmation. " +
          "You are in DISCUSSION_ONLY mode. Present your proposed approach and " +
          "wait for the user to say 'yes', 'go ahead', 'proceed', or similar " +
          "before making any changes.",
      };
    },
  },

  tools: [
    {
      name: "request_edit_permission",
      description:
        "Call this BEFORE any file edit to describe your proposed changes to the " +
        "user. After calling this, STOP and wait for user confirmation. Do not " +
        "call edit/create until the user confirms.",
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
        confirmationGranted = false;
        return (
          "Permission request noted. STOP. Do not call edit or create tools. " +
          "Wait for the user to respond with explicit confirmation."
        );
      },
    },
  ],
});
