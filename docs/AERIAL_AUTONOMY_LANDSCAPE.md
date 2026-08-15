# Open-source Aerial Autonomy Landscape and DRN Stack Decision

Research snapshot: 2026-08-15

Status: decision document, based on papers, current default branches, releases,
issues, pull requests, and project documentation. The external stacks were not
installed or flight-tested as part of this review, so adoption still requires a
bounded hands-on evaluation.

## Executive conclusion

The original DRN Stack idea is relevant, but it is no longer sufficiently
distinctive as a general-purpose autonomy stack.

The strongest current overlap is
[aerial-autonomy-stack (AAS)](https://github.com/JacopoPan/aerial-autonomy-stack).
It now covers nearly the same product thesis: PX4 and ArduPilot, ROS 2, Gazebo
Harmonic, multi-vehicle simulation, perception, x86 simulation, Jetson
deployment, hardware/network-in-the-loop, and a behavior-tree mission layer.
The behavior-tree layer was merged in June 2026, after version 2 of the AAS
paper was published in May, which is why the paper understates this overlap.

[Aerostack2](https://github.com/aerostack2/aerostack2) remains the stronger
choice when the primary interest is a mature, extensible behavior-tree and
multi-aerial-robot framework. It has a first-class BehaviorTree.CPP package,
Groot-compatible XML trees, reusable ROS 2 action/service nodes, tests, and a
larger behavior catalog. AAS has the stronger end-to-end simulation-to-Jetson
story, but its Python `py_trees` mission layer is newer and intentionally
smaller.

The recommended direction is therefore:

1. Do not grow DRN Stack into another complete collection of perception,
   mapping, planning, swarm, and mission packages.
2. Treat AAS as the primary upstream candidate for the original product vision.
   Its maintainers have explicitly invited a PX4 ROS 2 Interface Library
   example, which directly matches work already proven in `drn_control`.
3. Treat Aerostack2 as the primary upstream candidate for deeper behavior-tree
   work.
4. Keep DRN Stack only where it is differentiated: a conservative,
   Windows-friendly integration and conformance lab with inert CI, explicit
   operator gates, evidence packs, replay, and compatibility checks.
5. Before making an irreversible pivot, run the same bounded mission and
   failure-recovery evaluation in AAS and Aerostack2. Use the results, not the
   feature lists, to decide whether DRN becomes a narrow test harness or enters
   maintenance mode.

In short: the idea was not misguided. The ecosystem has now validated it and
caught up to much of it. The highest-leverage work is likely to make an existing
stack safer, more testable, and easier to deploy instead of recreating its
autonomy modules here.

## The question this review answers

The intended DRN Stack was a software distribution that could run on both a
simulation workstation and a drone companion computer, with a growing set of
vehicles and ROS 2 packages forming an autonomy stack. Behavior trees would
compose those packages into missions.

That vision contains four separate product problems:

1. **Flight integration:** connect ROS 2 safely to the autopilot and expose
   reliable, cancellable actions.
2. **Autonomy capabilities:** estimation, perception, mapping, planning,
   control, and multi-robot coordination.
3. **Mission orchestration:** compose capabilities into inspectable and
   recoverable behavior trees.
4. **Productization:** make the same system reproducible in simulation, CI,
   companion hardware, networking, logging, and operator workflows.

No project is best at all four. The build-versus-contribute decision should be
based on which problem is the actual goal, not on whether a repository calls
itself an "autonomy stack."

## What DRN Stack is today

At commit `5629a96`, DRN Stack is already a coherent integration product rather
than an autonomy framework:

- pinned PX4 v1.17, ROS 2 Humble, Gazebo Harmonic, XRCE-DDS, and Foxglove;
- matching PowerShell and Bash lifecycle commands;
- a PX4 ROS 2 Control Interface-based `drn_control` node with mode
  registration, acknowledgement, watchdog, arbitration, and command timeout
  behavior;
- basic, depth-camera, ground-truth VIO, and LiDAR simulation profiles;
- a downstream project and inert scenario contract;
- checksummed MCAP, ULog, configuration, image, and verdict evidence packs;
- a read-only, continuously disarmed hardware-UDP acceptance profile; and
- bounded, isolated two-to-four-vehicle simulation and observation.

It does not currently contain real visual or LiDAR odometry, SLAM, mapping,
obstacle avoidance, path planning, semantic perception, a mission executive,
behavior trees, ARM64 deployment images, or validated physical companion
operation.

This is consistent with the current [roadmap](ROADMAP.md), which says the useful
niche is integration, observation, diagnosis, and validation and explicitly
excludes a general autonomous mission or swarm framework. The original personal
vision is broader than the repository's current public contract. That tension
should be resolved deliberately rather than by adding autonomy packages one at
a time.

## How the landscape is organized

The projects fall into different layers. Comparing all of them as peer stacks
creates misleading conclusions.

| Layer | Representative projects | What they primarily solve |
| --- | --- | --- |
| Autopilot and external-mode API | PX4, ArduPilot, PX4 ROS 2 Interface Library | Real-time flight, failsafes, and companion-to-autopilot control contracts |
| Vertically integrated sim-to-edge stack | AAS | One opinionated path from Gazebo and CI to Jetson aircraft containers |
| Modular aerial autonomy framework | Aerostack2 | Swappable ROS 2 platform, behavior, planning, perception, and swarm packages |
| Field-research system | MRS UAV System, Unified Autonomy Stack | Proven estimation, control, mapping, planning, and resilient navigation |
| Broad embodied autonomy platform | AirStack | Aerial and ground autonomy, Isaac Sim, planning, controls, operator tools, and research workflows |
| Specialized stack | Agilicious, Crazyswarm2, ROSplane | Agile quadrotors, Crazyflie swarms, or fixed-wing research respectively |
| Mission-composition building block | BehaviorTree.CPP, BehaviorTree.ROS2, `py_trees` | General behavior-tree execution and ROS integration, not a drone stack |
| Integration and evidence layer | DRN Stack today | Reproducible startup, safe control boundaries, profiles, CI, evidence, and replay |

### Repository snapshot

This table anchors activity claims to the reviewed default-branch commit rather
than to a repository's most recent push on any branch.

| Project | Reviewed default-branch commit | Latest release seen | License | Current BT signal |
| --- | --- | --- | --- | --- |
| AAS | [`fcb2852`, 2026-08-15](https://github.com/JacopoPan/aerial-autonomy-stack/tree/fcb2852dbd3bcaed27ff5a44576aa62729548a9f) | v1.6.0, 2026-07-27 | MIT | `py_trees` mission package added 2026-06-20 |
| Aerostack2 | [`d84c067`, 2026-08-12](https://github.com/aerostack2/aerostack2/tree/d84c06764fd665af19864650de572e49a82565a1) | 1.1.3, 2025-07-23 | BSD-3-Clause | First-class BehaviorTree.CPP package; active improvement PR |
| MRS UAV System | [`3340bfe`, 2026-08-03](https://github.com/ctu-mrs/mrs_uav_system/tree/3340bfe3ff7cf5cc694d0dfd23c5f34d4605ec43) | Rolling stable/unstable packages | BSD-3-Clause | No first-class BT found in reviewed metapackage |
| AirStack | [`e4b499d`, 2026-05-20](https://github.com/castacks/AirStack/tree/e4b499d120ef5157232c6ef6b1109488a94c9641) | 0.18.0, 2026-05-20 | MIT in repository metadata | BT documented, but referenced runtime packages absent from reviewed tree |
| Unified Autonomy Stack | [`cb78bf7`, 2026-06-28](https://github.com/ntnu-arl/unified_autonomy_stack/tree/cb78bf7f57d074fc0999dd23bb1cfa1b1754d44d) | 1.0, 2026-06-28 | BSD-3-Clause | No BT implementation found in reviewed top-level repository |

Release recency is not the same as development activity. Aerostack2, for
example, has current default-branch work despite an older numbered release;
AirStack has active August pull requests despite its reviewed `main` commit
being from May.

## Primary candidates

### 1. aerial-autonomy-stack: closest to the original DRN vision

The May 2026 [AAS paper](https://arxiv.org/abs/2602.07264) frames the problem as
the system-engineering side of the simulation-to-reality gap. Its central claim
is that simulation, networking, edge compute, perception, and autopilot
integration must be validated together. That is very close to the motivation
behind DRN Stack.

Its architecture has three principal images:

- a simulation image with Gazebo and PX4/ArduPilot SITL;
- a ground image with QGroundControl and communications; and
- an aircraft image built for x86 simulation and ARM64 Jetson deployment from
  the same source definition.

Current AAS adds important capabilities beyond the paper's comparison table:

- a YAML-defined `py_trees` mission system added by
  [PR #94](https://github.com/JacopoPan/aerial-autonomy-stack/pull/94);
- sequence, selector/fallback, and repeat composition;
- takeoff, land, orbit, offboard, reposition, speed, wait, and blackboard
  condition leaves;
- per-aircraft missions, state sharing, and perception data on the blackboard;
- Gymnasium stepping and faster-than-real-time/multi-instance simulation; and
- current PX4 v1.17, Gazebo Harmonic, ROS 2 Humble, YOLO, KISS-ICP, Zenoh, and
  Jetson deployment support.

The current behavior-tree implementation is real, not merely a roadmap item.
However, at reviewed commit
[`fcb2852`](https://github.com/JacopoPan/aerial-autonomy-stack/tree/fcb2852dbd3bcaed27ff5a44576aa62729548a9f),
it is also young and deliberately narrow:

- it is a custom YAML-to-`py_trees` builder rather than the broader
  BehaviorTree.CPP/Groot ecosystem;
- the available composite and decorator vocabulary is small;
- the mission package has no dedicated test directory in the reviewed tree;
- multi-vehicle coordination is split between per-aircraft trees and a ground
  traffic controller rather than expressed as one documented fleet-level tree;
  and
- action cancellation, recovery, persistence, and safety-policy semantics are
  not yet presented as a formal mission contract.

Those are contribution opportunities, not reasons to dismiss the project.
AAS is active, MIT-licensed, released as v1.6.0 in July 2026, and the maintainer
has been responsive in current issues and pull requests.

Most importantly for DRN, [AAS issue
#18](https://github.com/JacopoPan/aerial-autonomy-stack/issues/18) explicitly
invites a contribution demonstrating the PX4 ROS 2 Interface Library. AAS
currently exposes its own cross-autopilot ROS 2 action interface; DRN has
already invested in PX4's registered external-mode state machine. A clean AAS
integration or example could transfer that work into a much broader project.

**Best fit:** contribute here if the motivating product is an opinionated,
practical path from simulation to companion hardware, including perception and
behavior-tree missions.

**Main caution:** AAS is deliberately NVIDIA- and Jetson-centered. That gives
it strong deployment coherence but makes CPU-only, vendor-neutral, and small-CI
workflows less central than they are in DRN.

### 2. Aerostack2: strongest behavior-tree and modular-framework fit

[Aerostack2](https://github.com/aerostack2/aerostack2) is a ROS 2-native,
project-oriented framework for multi-aerial-robot systems. Its package catalog
already covers aerial platforms, controllers, state estimation, mapping,
motion and perception behaviors, path planning, trajectory generation, swarm
flocking, payloads, simulation assets, messages, and Python APIs.

Its behavior-tree implementation is substantially more mature than AAS's:

- [`as2_behavior_tree`](https://github.com/aerostack2/aerostack2/tree/d84c06764fd665af19864650de572e49a82565a1/as2_behavior_tree)
  uses BehaviorTree.CPP;
- trees use the standard XML/Groot workflow;
- ROS 2 actions and services are wrapped as non-blocking tree nodes;
- the package includes reusable arm, takeoff, land, go-to, GPS go-to,
  follow-reference, follow-path, event, and flight-state nodes;
- it includes emulators and focused tests; and
- Aerostack2 behaviors expose pause, resume, cancel, and modify semantics through
  [ROS 2 actions](https://aerostack2.github.io/_09_development/_tutorials/_tutorials/behavior.html).

Aerostack2 is BSD-3-Clause, formally documents contribution, builds as released
ROS packages, and remains active. The open
[`as2_behavior_tree` improvements PR](https://github.com/aerostack2/aerostack2/pull/961)
also shows that its BT layer has useful work available now: dependency cleanup,
ports, conditions, and action-node behavior are still being refined.

Compared with AAS, Aerostack2 favors modularity and plugins over one vertically
controlled deployment. That is attractive for research and extension but
creates more integration choices. Its current first-class platform story is
also less unified across PX4 and ArduPilot; ArduPilot compatibility remains an
active user topic.

**Best fit:** contribute here if the main goal is to learn, design, and extend
behavior-tree mission semantics or reusable aerial behaviors.

**Main caution:** adopting the whole framework means accepting its abstractions
and integration overhead. It is not simply a behavior-tree library that drops
under `drn_control` without architectural overlap.

### 3. MRS UAV System: strongest mature onboard multirotor system

The [MRS UAV System](https://github.com/ctu-mrs/mrs_uav_system) is a large,
field-oriented research platform from CTU's Multi-robot Systems group. Its
current ROS 2 branch targets Jazzy, runs entirely on a companion computer, and
includes control, estimation, mapping, and planning. The ecosystem publishes
stable and unstable packages, acceptance-test infrastructure, simulators,
multi-architecture Docker images, PX4 integration, OpenVINS, PointLIO, and
Octomap planning.

This is the strongest candidate when real multirotor control, estimation, and
field history matter more than having a small comprehensible stack. It is also
evidence that reliable open-source aerial autonomy exists, although much of its
value is spread across the CTU MRS organization rather than one repository.

There is no first-class behavior-tree mission layer in the reviewed ROS 2
metapackage, and the maintainers candidly state that documentation trails the
rapidly evolving research system.

**Best fit:** participate here for serious multirotor estimation, planning,
control, and real-world experimental infrastructure.

**Main caution:** it is a broad lab ecosystem with a steeper learning and
contribution curve, and it is less aligned with the behavior-tree goal.

### 4. Unified Autonomy Stack: strongest algorithmic resilient-autonomy scope

The 2026 [Unified Autonomy Stack
paper](https://arxiv.org/abs/2605.12735) and
[repository](https://github.com/ntnu-arl/unified_autonomy_stack) combine
multi-modal perception, multi-behavior planning, and multi-layer safe
navigation across aerial and ground robots. The reported capabilities include
LiDAR, radar, vision, and inertial fusion; semantic understanding; mapping;
sampling-based motion and informative planning; learned policies; and control
barrier-function safety filters. The paper reports field trials in cluttered,
GNSS-denied, perceptually degraded environments.

This is much more autonomy-algorithm-heavy than DRN or AAS. It is also a very
new public integration surface, built from a set of component repositories and
ROS 1/ROS 2 boundaries. A current installation issue reports a missing/private
dependency, which is a warning to validate reproducibility before committing to
it.

There is no behavior-tree implementation in the reviewed top-level repository.
Its "multi-behavior planning" is an autonomy architecture concept, not evidence
of BehaviorTree.CPP or `py_trees`.

**Best fit:** contribute here for resilient perception, exploration, planning,
or safety research.

**Main caution:** the public project is young and is not yet the clearest route
to the user's simulation-to-companion and behavior-tree product goals.

### 5. AirStack: broad and ambitious, but currently less clear as a BT target

[AirStack](https://github.com/castacks/AirStack) from CMU AirLab spans aerial
and ground autonomy, Isaac Sim, sensors, perception, local and global planning,
controls, multi-robot operation, and operator tooling. It is active, has a
formal contribution workflow, and its documentation describes a behavior-tree
and behavior-executive architecture.

The reviewed `main` branch is undergoing substantial restructuring. The current
documentation and the repository's contributor skill still reference
`behavior_tree`, `behavior_executive`, and example package paths that are absent
from the current source tree; the live behavior launch currently starts a drone
safety monitor. A new mission-runner pull request is in progress. This makes it
promising but not the most predictable place to begin behavior-tree work today.

AirStack is also centered on an NVIDIA/Isaac workflow with substantially higher
host requirements than DRN's Gazebo-first baseline.

**Best fit:** evaluate it for broad embodied-autonomy or AirLab research work,
especially if Isaac Sim is desirable.

**Main caution:** clarify the current mission-executive direction with the
maintainers before selecting it for behavior-tree contributions.

## Specialized and adjacent projects

The AAS paper's table is useful, but several entries solve deliberately narrower
problems:

- [Agilicious](https://github.com/uzh-rpg/agilicious) is a high-performance
  agile-quadrotor stack with custom flight software, controllers, estimators,
  planners, and hardware. Its public default branch has not advanced since
  March 2023 and it is ROS 1-oriented. It remains an excellent technical
  reference, not the best general ROS 2 contribution target.
- [Crazyswarm2](https://github.com/IMRCLab/crazyswarm2) is active and excellent
  for Crazyflie swarms, motion capture, and its specialized simulator/hardware
  path. Its hardware and scale assumptions do not match a general PX4 companion
  stack.
- Aerialist emphasizes automated PX4 test generation and log analysis rather
  than a deployed autonomy runtime. Its validation focus is conceptually close
  to DRN's current niche.
- XTDrone emphasizes broad multi-vehicle simulation, while GRVC UAL and KR
  Autonomous Flight have important abstraction or autonomy contributions but
  are primarily rooted in ROS 1-era architectures.
- [ROSplane 2.0](https://arxiv.org/abs/2510.01041) and
  [ROSflight 2.0](https://arxiv.org/abs/2510.00995) are relevant modern ROS 2
  projects for lean, modifiable fixed-wing/autopilot research. They are not
  direct substitutes for the PX4 multirotor companion-computer goal.

These projects matter as references and possible homes for specialized work,
but they should not drive DRN's general architecture.

## Behavior trees specifically

Behavior trees remain a good fit for aerial mission composition because they
make priority, fallback, interruption, and running state explicit. They do not,
by themselves, make a mission safe or autonomous. Their leaf-node contracts and
halt semantics are the hard part.

The three relevant implementation choices are:

| Approach | Strength | Cost or risk | Current aerial use |
| --- | --- | --- | --- |
| BehaviorTree.CPP + BehaviorTree.ROS2 | Mature C++ engine, XML/Groot tooling, plugin loading, non-blocking ROS action/service wrappers | More C++ and plugin lifecycle complexity; safety policy still belongs to the application | Aerostack2; Nav2 is the strongest general ROS precedent |
| `py_trees` + `py_trees_ros` | Fast to understand and extend in Python; direct ROS blackboard integration | Easier to create project-specific schemas; less interoperability with BT.CPP/Groot | Current AAS mission package |
| Custom mission state machine or DSL | Can encode a domain-specific safety contract precisely | Highest reinvention and maintenance risk | Common in project-specific research stacks |

[BehaviorTree.CPP](https://github.com/BehaviorTree/BehaviorTree.CPP) and
[BehaviorTree.ROS2](https://github.com/BehaviorTree/BehaviorTree.ROS2) are
healthy standalone foundations. BehaviorTree.ROS2 already provides a tree
execution server plus non-blocking action, service, publisher, and subscriber
wrappers for ROS 2 Humble and newer. If DRN ever hosts a BT runtime, it should
adopt one of these ecosystems rather than implement a new engine.

For an aerial system, the mission contract should define at least:

- which node may request mode activation, arming, takeoff, Land, or RTL;
- how a running action is halted and how cancellation is acknowledged;
- how Teleop or an operator command preempts the tree;
- timeouts and retry budgets, including what must never be retried;
- stale state, localization loss, communication loss, and low-battery policy;
- restart behavior and whether mission state is recoverable or deliberately
  discarded;
- namespaces, blackboard isolation, and coordination for multiple vehicles; and
- a trace linking every tree transition to ROS, PX4, MCAP, and ULog evidence.

This contract is a more defensible contribution than another collection of
takeoff, go-to, and land leaves.

## Decision matrix

The ratings below are qualitative and relative to the user's stated goal. They
are not claims of overall project quality.

| Project | Sim-to-companion parity | Behavior-tree maturity | Autonomy breadth | Field maturity | Contribution accessibility | Fit to the original DRN vision |
| --- | --- | --- | --- | --- | --- | --- |
| AAS | Strongest: shared x86/Jetson aircraft image and HITL/network model | Real but recent, small `py_trees` layer | Moderate and growing | Flight-proven claim plus published end-to-end evaluation | Active and responsive, but no formal contribution guide found | **Very high** |
| Aerostack2 | Strong, but more modular and integrator-driven | **Strongest aerial BT implementation reviewed** | Broad | Established academic framework and active use | Formal guide, tests, active BT PRs | **High**, especially for BT work |
| MRS UAV System | Strong onboard and multiarch story | No first-class BT found | Very broad for multirotors | **Strongest field history reviewed** | Distributed ecosystem and lagging docs raise entry cost | Medium |
| Unified Autonomy Stack | Partial; deployable research system but newer public packaging | No BT found | **Broadest resilient-autonomy algorithms** | Strong reported field trials | Young public integration surface | Medium-low |
| AirStack | Strong ambitions, Isaac/onboard-offboard split | Documented, but current runtime direction is unclear | Very broad | Research deployment history | Formal workflow but substantial restructuring | Medium |
| DRN Stack today | UDP scaffold only; no validated ARM64 aircraft image | None | Narrow | Simulation and read-only bench validation only | Small and understandable | High only as an integration/evidence layer |

## Where DRN Stack can still be distinct

DRN should not compete on the number of ROS packages. Its best existing
differentiators are process and evidence:

1. **Inert-by-default CI and startup.** No automatic arming or movement, with
   operator-gated flight and failure injection.
2. **A supported PX4 external-mode boundary.** `drn_control` uses the official
   PX4 ROS 2 Control Interface instead of rebuilding registration, watchdog,
   acknowledgement, and failsafe behavior with raw command topics.
3. **Portable evidence packs.** A run links MCAP, ULog, logs, inputs, image
   identities, revisions, checksums, and a final verdict.
4. **Explicit compatibility checks.** Firmware identity, message versions,
   disarmed state, and transport health fail closed.
5. **Windows-first operator ergonomics.** PowerShell and Bash remain equivalent,
   and GPU-less software-rendering paths are treated as supported workflows.
6. **Bounded profiles and resource qualification.** Sensor and fleet additions
   are accepted only with measured host and CI behavior.

AAS has log-analysis tools and sophisticated CI; MRS has acceptance testing;
Aerostack2 has package tests. DRN's opportunity is the tighter linkage between
mission intent, safety gates, reproducible environment, and a portable evidence
verdict. That is useful across stacks rather than being another stack.

## Build, contribute, or combine

### Recommended: contribute upstream and retain DRN as a narrow lab

This is the highest-leverage option.

For AAS, the most natural contributions are:

1. a PX4 ROS 2 Interface Library aircraft-mode example or supported adapter,
   starting from the design lessons in `drn_control`;
2. mission behavior-tree unit and integration tests, especially cancellation,
   timeout, rejected goals, stale perception, and restart behavior;
3. a machine-readable evidence manifest that ties ROS bags, autopilot logs,
   image revisions, mission input, and verdict together; and
4. a documented CPU/software-rendered smoke tier if that aligns with maintainer
   goals, without weakening AAS's NVIDIA deployment focus.

For Aerostack2, the most natural contributions are:

1. help complete and validate the open behavior-tree improvements;
2. improve halt/cancel/failure semantics and test them against real behavior
   servers;
3. add mission transition/evidence tracing; and
4. evaluate whether a PX4 ROS 2 Interface-backed platform plugin is useful
   upstream.

DRN would remain the place to reproduce and compare those behaviors under one
conservative operator and evidence workflow. It should consume upstream
packages rather than fork them.

### Valid alternative: put DRN in maintenance mode

If maintaining a separate integration lab is not personally motivating, the
rational choice is to finish the current hardware-parity commitments, document
the handoff, and direct new work to AAS or Aerostack2. A small project is not a
failure if it produced reusable knowledge and led to a stronger upstream
contribution.

### Not recommended: continue toward a complete independent autonomy stack

This path would require maintaining, at minimum, real localization, mapping,
planning, collision avoidance, perception, mission orchestration, hardware
drivers, ARM64 images, networking, simulation assets, and safety validation.
Multiple active research groups already maintain these pieces. A single
maintainer would spend most effort on dependency alignment and integration,
which is exactly the wheel AAS, Aerostack2, MRS, AirStack, and Unified Autonomy
Stack are already turning.

An independent stack becomes defensible only with a sharply different thesis,
such as certifiable mission evidence, vendor-neutral low-resource companions,
or a formally specified safety executive. "A growing list of ROS 2 packages"
is not enough differentiation.

## Proposed hands-on decision experiment

The paper and repository review is enough to reject blind duplication, but not
enough to choose an upstream community. Run a two-stack evaluation before the
next major DRN feature.

### Common scenario

Use one PX4 x500 and a manually initiated mission:

1. start and reach a healthy, disarmed state;
2. load a tree without executing it;
3. have the operator explicitly authorize activation and takeoff;
4. take off, wait, move to one bounded waypoint, and land;
5. repeat while cancelling the move with Land or RTL;
6. repeat with stale localization or a stopped action server; and
7. collect enough data to explain every transition and final outcome.

No real vehicle is needed for the first pass. Armed SITL still requires an
operator and must not be folded into ordinary smoke startup.

### Evaluate

For both AAS and Aerostack2, record:

- clean setup time on the actual Windows/WSL/Docker host;
- GPU and storage requirements;
- amount of project-specific glue;
- clarity of the autopilot action and safety boundary;
- BT authoring, inspection, cancellation, retry, and failure semantics;
- single-source simulation-to-companion build credibility;
- logging and root-cause quality after a forced failure;
- automated test coverage for the mission layer; and
- maintainer response to one small, well-scoped contribution.

### Decision gate

- Choose **AAS** if its deployment model works on the intended hardware and the
  simpler BT layer is sufficient or appealing to improve.
- Choose **Aerostack2** if reusable BT semantics and modular autonomy packages
  matter more than a single vertically controlled image pipeline.
- Keep developing **DRN** only if the experiment demonstrates a concrete,
  repeatable validation/evidence need that neither upstream wants to own.
- Do not choose based on stars, paper claims, or the number of listed features
  alone.

## Candidate DRN feature branches after the experiment

No feature branch should be opened until the experiment selects an upstream
relationship. If DRN remains active, the defensible sequence is:

1. `feature/aerostack2-evaluation-profile` -- use the project SDK to run an
   inert Aerostack2 compatibility scenario without forking its packages.
2. `feature/behavior-tree-evidence-trace` -- record tree transitions, action
   goals/results, operator interventions, and PX4 state in the existing
   evidence-pack schema. The implementation should target the selected upstream
   engine, not create a DRN-specific BT engine.
3. `feature/autonomy-conformance-scenarios` -- reusable checks for cancellation,
   stale state, timeout, restart, namespace isolation, and evidence completeness.
4. `feature/hardware-serial-companion` -- complete the already-promised hardware
   parity only when there is physical hardware available to qualify it.

If AAS is selected, it should be evaluated in its own topology rather than
forced into DRN's Compose model. In that case, the meaningful branch is likely
upstream in AAS, with DRN retaining only comparative scenarios and evidence
specifications.

## Final reflection

The project began from a real industry pattern: companies need a repeatable
software distribution that spans simulation, companion compute, perception,
mission logic, and flight-controller integration. That problem is still
relevant. The AAS paper explicitly identifies the integration side of the
sim-to-real gap, and its rapid addition of behavior-tree missions reinforces
the direction.

What changed is the opportunity cost. Building the full vertical stack alone
now competes with active projects that have lab teams, field vehicles, papers,
and growing contributor communities. DRN's work is not wasted: its safety
boundaries, evidence packs, external-mode integration, and Windows/CI discipline
are precisely the less glamorous productization work that research stacks often
need.

The useful choice is not "abandon DRN or prove it can beat every stack." It is
to decide which identity creates the most leverage:

- **AAS contributor** for the original sim-to-companion product vision;
- **Aerostack2 contributor** for behavior-tree-centered aerial autonomy; or
- **DRN maintainer** of a neutral, conservative conformance and evidence layer.

The evidence currently favors the first option, supported by the third. It does
not favor building another full autonomy stack here.

## Primary sources

### Papers and architecture

- Panerati et al., [aerial-autonomy-stack -- a Faster-than-real-time,
  Autopilot-agnostic, ROS2 Framework](https://arxiv.org/abs/2602.07264), v2,
  2026-05-02.
- Fernandez-Cortizas et al., [Aerostack2: A Software Framework for Developing
  Multi-robot Aerial Systems](https://arxiv.org/abs/2303.18237), 2023.
- Baca et al., [The MRS UAV System](https://doi.org/10.1007/s10846-021-01383-5),
  2021.
- Dharmadhikari et al., [The Unified Autonomy Stack](https://arxiv.org/abs/2605.12735),
  2026.
- Reid et al., [ROSplane 2.0](https://arxiv.org/abs/2510.01041), 2025.
- Moore et al., [ROSflight 2.0](https://arxiv.org/abs/2510.00995), 2025.

### Current implementations and contribution signals

- AAS [repository](https://github.com/JacopoPan/aerial-autonomy-stack),
  [behavior-tree PR #94](https://github.com/JacopoPan/aerial-autonomy-stack/pull/94),
  [current tree builder](https://github.com/JacopoPan/aerial-autonomy-stack/blob/fcb2852dbd3bcaed27ff5a44576aa62729548a9f/aircraft/aircraft_ws/src/mission/mission/tree_builder.py),
  and [PX4 ROS 2 Interface issue #18](https://github.com/JacopoPan/aerial-autonomy-stack/issues/18).
- Aerostack2 [repository](https://github.com/aerostack2/aerostack2),
  [`as2_behavior_tree`](https://github.com/aerostack2/aerostack2/tree/d84c06764fd665af19864650de572e49a82565a1/as2_behavior_tree),
  and [BT improvements PR #961](https://github.com/aerostack2/aerostack2/pull/961).
- MRS UAV System [ROS 2 repository](https://github.com/ctu-mrs/mrs_uav_system/tree/ros2).
- Unified Autonomy Stack [repository](https://github.com/ntnu-arl/unified_autonomy_stack)
  and [installation issue #12](https://github.com/ntnu-arl/unified_autonomy_stack/issues/12).
- AirStack [repository](https://github.com/castacks/AirStack),
  [behavior-tree documentation](https://github.com/castacks/AirStack/blob/e4b499d120ef5157232c6ef6b1109488a94c9641/docs/robot/autonomy/behavior/behavior_tree.md),
  and [mission-runner PR #366](https://github.com/castacks/AirStack/pull/366).
- [BehaviorTree.CPP](https://github.com/BehaviorTree/BehaviorTree.CPP) and
  [BehaviorTree.ROS2](https://github.com/BehaviorTree/BehaviorTree.ROS2).
- [PX4 ROS 2 Interface Library](https://github.com/Auterion/px4-ros2-interface-lib)
  and [PX4 control-interface documentation](https://docs.px4.io/v1.17/en/ros2/px4_ros2_control_interface).
- [Agilicious](https://github.com/uzh-rpg/agilicious) and
  [Crazyswarm2](https://github.com/IMRCLab/crazyswarm2).

Repository activity and license data in this document were checked through the
GitHub API on the research date. Popularity metrics were reviewed as weak
community signals but intentionally excluded from the decision matrix.
