---
name: start-feature-branch
description: Assess, research, and prepare a proposed feature before creating a Git branch. Use when a user proposes a feature, asks whether a feature is worthwhile, wants prior-art research, or asks to begin feature work on a feature/ branch. Inspect repository status and existing work first, search the web for relevance and previous implementations, present a readiness brief, and require explicit confirmation before creating the branch.
---

# Start Feature Branch

Follow this order. Do not combine the confirmation gate with branch creation.

## 1. Inspect before acting

Make the first repository action a read-only status check:

```bash
git status --short --branch
```

Then:

1. Read every applicable `AGENTS.md`.
2. Identify the current branch, HEAD, remotes, upstream, and ahead/behind state.
3. Inspect the worktree for staged, unstaged, untracked, conflicted, or
   generated files.
4. Do not discard, stash, stage, commit, or modify existing work.
5. Stop and explain any merge/rebase conflict or unsafe base-state issue.

Fetching remote refs is allowed after the initial status check when needed to
assess whether the proposed base is current. Do not switch or create branches.

## 2. Understand the proposed feature

Summarize the user-visible outcome in one or two sentences. Identify:

- likely components and interfaces affected;
- safety, compatibility, migration, or operational constraints;
- a short lowercase branch slug using letters, digits, and hyphens;
- the intended base branch, normally the repository's default branch.

Use the repository's code, documentation, tests, dependency manifests, and
architecture as evidence. Do not make implementation changes.

## 3. Find previous internal efforts

Search before assuming the feature is new:

```bash
git branch --all
git log --all --oneline --decorate
rg -n "<relevant terms>" .
```

Narrow those commands to the feature vocabulary. Also inspect:

- related modules, TODOs, design documents, changelogs, and tests;
- commit messages and branches containing relevant terms;
- repository issues, pull requests, and discussions when accessible.

Distinguish completed work, abandoned experiments, adjacent capabilities, and
genuine gaps.

## 4. Research relevance and external prior art

Use internet search for every invocation of this skill. Search for:

1. the feature within the project's technical domain;
2. official documentation or supported platform patterns;
3. existing open-source implementations and integrations;
4. known limitations, safety guidance, and maintenance concerns;
5. recent issues, discussions, or failed approaches.

Prefer primary sources: official documentation, upstream repositories, issues,
pull requests, standards, and research papers. Use current sources and cite
them near the claims they support.

Do not claim that no prior project or implementation exists. State the search
scope and say that no relevant example was found within that scope.

## 5. Present a readiness brief

Before asking for confirmation, report:

- **Codebase state:** branch, synchronization, and worktree condition.
- **Feature relevance:** the problem it solves and whether it fits the current
  architecture.
- **Previous efforts:** internal and external findings with links or commit
  references.
- **Proposed scope:** affected areas and explicit non-goals.
- **Risks and validation:** important failure modes and required tests.
- **Proposed branch:** `feature/<slug>` and its base branch.

Recommend proceeding, refining, or declining based on the evidence.

## 6. Require explicit confirmation

Ask the user to confirm the exact operation:

> Create `feature/<slug>` from `<base-branch>` now?

End the turn without creating or switching branches. Research approval,
planning approval, or a general request to implement does not satisfy this
gate. Require a clear affirmative answer after showing the readiness brief.

## 7. Create only after confirmation

In the follow-up turn:

1. Run `git status --short --branch` again.
2. Confirm the base and worktree have not changed unexpectedly.
3. Check whether the proposed local or remote branch already exists.
4. If it exists, stop and ask whether to reuse it or choose another name.
5. Otherwise create it:

   ```bash
   git switch <base-branch>
   git switch -c feature/<slug>
   ```

6. Report the resulting branch and status.

Branch confirmation authorizes only branch creation. Do not implement, stage,
commit, push, or open a pull request unless the user separately authorizes
those actions.
