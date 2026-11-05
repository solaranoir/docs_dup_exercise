# AI Workflow

## Tools Used

For the Document Workspace MVP, I used **ChatGPT for product planning, architecture discussions, requirements, roadmap development, and presentation materials**
I used Claude Code (Claude Opus 5.5) for planning, coding, tests, CI, GitHub issues and PRs, and checks against the live deployment. One forked Claude agent drafted the demo notes. 
The human owner made every product decision, merged every PR, and did all Render, R2 and GitHub settings work. The agent never merged anything.


## Where AI Accelerated the Work

- Translating the product requirements into a prioritized backlog
- Turning the proposal and roadmap into 22 labelled issues, split into agent tasks and tasks needing human input, in minutes.
- Building the full stack in about 90 minutes, a plan the roadmap budgeted at four weeks. That covered the FastAPI API with migrations, the React/Tiptap editor, the .txt/.md/.docx converters, object storage, and permissions.
- Writing tests alongside the code: 68 pytest, 9 Vitest and 14 Playwright, plus the CI pipeline, ADRs, the runbook and the deploy smoke script.
- Troubleshooting deployment issues
- Drafting the presentation

## What I Changed or Rejected

I treated AI-generated code and architectural recommendations as proposals, not final decisions. I retained human control over scope, security, and implementation priorities, including choosing view-only sharing for the MVP, explicit saves with revision conflict detection instead of autosave, and Cloudflare R2 for persistent file storage. AI-generated changes went through pull requests and review rather than being merged automatically.
Human review also located several bugs in the deployment process which were then fixed using AI tools.

## How I Verified Quality

Verification went beyond reviewing generated code. The completed application has **68 backend tests, 9 frontend tests, 14 Playwright end-to-end journeys**, and a deployed smoke test that passes **20 checks**. Testing uncovered real accessibility defects, a React StrictMode race condition, and a stale Render deployment. I also verified server-side authorization, persistence, file integrity, and the user experience across three seeded accounts.

## Approach to AI-Assisted Engineering

**My approach to AI-assisted engineering is to use AI for speed and breadth while retaining human ownership of technical decisions, validation, and product quality.** The goal isn't to maximize AI-generated code. It's to deliver reliable software faster without sacrificing engineering discipline.

