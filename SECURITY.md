# Security policy

## Supported versions

DRN Stack is currently pre-1.0. Security fixes target the latest `main` branch
and the most recent tagged release, if one exists. Older commits and
unpublished combinations of upstream dependencies are not supported.

The supported dependency combination is documented in
[`docs/COMPATIBILITY.md`](docs/COMPATIBILITY.md).

## Reporting a vulnerability

Do not open a public issue containing vulnerability details, credentials,
private flight data, or a working exploit.

Use GitHub's
[private vulnerability report](https://github.com/ivanrulik/drn_stack/security/advisories/new)
when it is available. If that option is unavailable, open a minimal public
issue asking the maintainer to establish a private contact channel. Do not
include technical details in that issue.

Useful reports include:

- the affected revision and environment;
- the safety or security impact;
- minimal reproduction steps;
- whether the issue can arm, move, expose, or control a vehicle unexpectedly;
- any suggested mitigation.

Reports involving unintended arming or motion, command-loss handling,
hardware-profile selection, remote Foxglove control, secret exposure, or
container escape should be treated as security-sensitive.

The maintainer will acknowledge and triage reports on a best-effort basis.
There is no guaranteed response or remediation timeline while the project is
pre-1.0. Please allow time for a coordinated fix before public disclosure.

## Safety

This policy does not certify DRN Stack for real-world flight. Reproduce
suspected control issues in SITL whenever possible. Do not test a vulnerability
on hardware unless you own the system, are authorized to test it, and have an
appropriate physical safety plan.
