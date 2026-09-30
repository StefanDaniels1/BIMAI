/**
 * Prompts people copy into Claude Code. One source for the copy button and the preview,
 * so they can never drift apart. Keep them in plain language: readers paste them unchanged.
 */

/** The start prompt: installs bimai and runs the onboarding interview (docs/start/install, landing page). */
export const startPrompt = `Set up bimai (https://docs.bimai.nl) in this project folder for me. Follow these steps in order and
don't skip the confirmation.

1. Check that Python 3.11 or newer is available. Then install bimai:
   pip install "git+https://github.com/StefanDaniels1/BIMAI.git"
   Check it worked with: bimai --version

2. Look at what's already in this folder, so you can suggest answers: models (.ifc, .rvt, .nwd,
   .dgn, .dwg), BCF issues, a BEP or EIR document, planning exports, Relatics exports and meeting
   transcripts.

3. Ask me these questions one at a time, in plain language, suggesting answers where you can:
   - The project name.
   - My name.
   - My role: design coordinator, BIM coordinator, BIM modeller or information manager.
   - What I want help with. Choose from: requirements, risks, planning, reporting, issues,
     model-checks, delivery, meetings.
   - Which tools and data the project uses. Choose from: revit, civil3d, openroads, navisworks,
     bonsai, ifc, autocad, acc, bcf, ids, bep, relatics, primavera, msproject.
   - Whether I'm new to VS Code.
   - The language for documents: en (English) or nl (Dutch).

4. Show me what bimai would do, without writing anything:
   bimai init --dry-run --yes --name "<project>" --person "<my name>" --role "<role>" \\
     --goals <goals, comma-separated> --tools <tools, comma-separated> --language <en|nl>
   Add --new-to-vscode if I said I'm new to VS Code. Explain the proposed team and why each
   member is on it, in a few sentences.

5. Ask me: "Shall I set this up?" Only when I say yes, run the same command without --dry-run.

6. Run: bimai validate
   Then tell me to start a new Claude Code session, so my new team is loaded, and give me three
   example questions I can ask my team.

If a command fails, show me the error and explain it simply. Don't work around it by editing
bimai's files by hand.`;
