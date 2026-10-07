/**
 * Prompts people copy into Claude Code. One source for the copy button and the preview,
 * so they can never drift apart. Keep them in plain language: readers paste them unchanged.
 */

/** The start prompt: installs bimai and runs the onboarding interview (docs/start/install, landing page). */
export const startPrompt = `Set up bimai (https://docs.bimai.nl) in this project folder for me. Follow these steps in order.

1. Install bimai with its one-line installer (it needs no Python, git or administrator rights):
   - on Windows: powershell -ExecutionPolicy ByPass -c "irm https://docs.bimai.nl/install.ps1 | iex"
   - on macOS or Linux: curl -LsSf https://docs.bimai.nl/install.sh | sh
   If the bimai command isn't found afterwards, use the full path the installer printed (in the
   .local/bin folder in my user folder). Check it worked with: bimai --version

2. Get the interview: bimai init --interview
   It prints the questions as JSON, made for your AskUserQuestion tool. It also shows what bimai found
   in this folder through the suggested options.

3. Ask me step 1 with the AskUserQuestion tool, in one call. Use each question's header, question text
   and options exactly as given, in the given order, and put "(Recommended)" after the recommended
   option. Use multiSelect where multi_select is true. Leave "Other" to me for my own answer.
   - If I answer with Other on a choice, map my words to the closest value in that question's
     "allowed" list. If you're not sure, ask me to confirm the mapping in plain language.
   - For text questions (kind "text"), my own words are the answer.

4. Get step 2 for my role: bimai init --interview --role "<my role>"
   Ask it the same way, in one call.

5. Show me what bimai would set up, without writing anything:
   bimai init --dry-run --json --yes --name "<project>" --person "<my name>" --role "<role>" --goals <goals, comma-separated> --tools <tools, comma-separated> --language <en|nl>
   Add --new-to-vscode if I said I'm new to VS Code. Explain the proposed team in a few short lines:
   who is on it and why.

6. Ask me with AskUserQuestion: "Set up this team?" with the options "Yes, set it up" and "No, change
   something". Only when I say yes, run the same command without --dry-run and --json.

7. Connect my tools. The dry run listed "connections" with a status for each tool I chose:
   - "ready": already connected by bimai init.
   - "needs-install": ask me with AskUserQuestion: "Install the <label> now?" with the options "Yes,
     install it" and "Not now". Explain its "message" first: Windows may ask permission once, and the program
     it runs in (such as Civil 3D, Revit or OpenRoads) must be closed. Only on yes, run its "command".
   - "needs-app", "other-platform", "unavailable": tell me its "message" in plain words. Don't suggest a
     command for these unless the connection gives one.

8. Run: bimai validate
   Then tell me to start a new Claude Code session so my team is loaded, and give me three example
   questions I can ask my team.

If a command fails, show me the error and explain it simply. Don't work around it by editing bimai's
files by hand.`;
