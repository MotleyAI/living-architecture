# Living architecture, explained

Each part below is a list of problems you hit when agents write most of your code, and how the `la` plugin
handles each one.

## Part 1: a top-down architecture that is enforced

**My code drifts into spaghetti over many rounds of agent-generated changes.**
Describe the high-level structure of the code as a hierarchical [LikeC4](https://likec4.dev) model whose
nodes map to code modules. The arrows between nodes decide which modules may import which. `la-arch-check`
measures the real imports and fails when they disagree with the model, so the diagram is enforced rather than
merely drawn.

**The code today does not match the architecture I want.**
Mark an arrow `#legacy`: it is allowed for now and flagged for removal. A ratchet in `index.yaml` keeps the
number of legacy arrows from growing. `/la:arch-cleanup` retires them a batch at a time.

**Aligning modules with the target causes a lot of import churn, which costs tokens and time.**
`/la:deterministic-refactor` moves and renames code (Python with rope, TypeScript with its language service), which rewrites every import for you.
The type checker then proves that nothing was left dangling. The agent does not edit each import by hand.
See [Deterministic refactoring](deterministic-refactoring.md).

**Some principles apply only to one part of the code.**
Each model node can have its own `*.arc42.md` file listing the principles that hold for that node and its
children. `system.arc42.md` holds the cross-cutting ones. `la-arch-diagrams` writes the relevant part of the
model into each file as a mermaid diagram, so an agent can read the structure as text.

**I know my principles, but the code does not fully follow them yet.**
Every principle carries a status tag: the test that enforces it (`[enforced: …]`), the issue that will make it
hold (`[target: …]`), or `[review]` for a principle that is believed to hold but is not enforced.
`la-arch-check` verifies the tags.

**How do I make the agent follow the principles?**
Every stage of `/la:pr` starts by reading the arc42 files of the nodes the change touches and naming the
principles that apply. Those principles drive the agent's later decisions.

**Won't the agent simply change the principles to suit itself?**
The model and the arc42 files have the same status as tests: every change to them needs your explicit
approval.

`/la:arch-init` builds the first model for an existing repo. It starts from a scaffold measured from the code,
then interviews you about the target structure and the principles.

## Part 2: the four-stage PR flow

**I know what I want to build, but I need help finding the edge cases and the interactions with the rest of
the code.**
The plan stage of `/la:pr` interviews you, knowing the code. Codex then reviews the resulting plan, and the
stage writes it as a validated OpenSpec change: proposal, design, tasks and scenarios. Later stages cannot
change the plan without your approval.

**How do I know the tests cover the relevant cases?**
The tests stage writes failing tests from the plan's scenarios, and Codex reviews them for completeness
against the plan.

**What if the agent finds a problem with the plan during implementation?**
The plan has the same status as the tests: the implementation stage stops and asks you before changing it.

**The tests pass, but how do I know the change has no other bugs?**
The review stage loops over the deterministic gates (conventions, type check, architecture), CI, CodeRabbit,
Sonar and Codex, triaging and fixing findings until every gate is clean.

**Six months later: why on earth was this line written like that?**
Find the PR that introduced it. Its OpenSpec change is archived in the repo, design included.

Each stage ends at a hard stop, so you can reset the session between stages. Everything the next stage needs
is on disk or in the issue tracker, and `/la:pr` works out which stage to run from the branch alone.
