# Jarvis OS Engineering Decisions

This document records architectural and product decisions.

The purpose of this file is to preserve the reasoning behind important decisions so they are not revisited unnecessarily.

---

## Decision 001

Title:
Architecture Freeze

Status:
Accepted

Decision:

The overall architecture of Jarvis OS is frozen.

Major structural changes are only permitted when:

- a bug cannot otherwise be fixed
- the current architecture blocks a future capability
- there is a significant engineering advantage

Reason:

Repeated structural changes slow development and introduce unnecessary complexity.

---

## Decision 002

Title:
One Brain. Multiple Interfaces.

Status:
Accepted

Decision:

JarvisCore contains all intelligence.

Desktop, Android, CLI, Voice and future interfaces are presentation layers only.

Reason:

The same Jarvis should exist everywhere.

---

## Decision 003

Title:
Response Model

Status:
Accepted

Decision:

JarvisCore returns Response objects instead of raw strings.

Reason:

Interfaces should receive structured responses rather than text only.

This enables:

- desktop actions
- Android actions
- voice
- future interfaces

without changing JarvisCore.

---

## Decision 004

Title:
Desktop Coordinator

Status:
Accepted

Decision:

DesktopCoordinator exists as a reserved component.

It will not be implemented until it has a unique responsibility.

Reason:

Avoid unnecessary abstractions.

---

## Decision 005

Title:
First Launch

Status:
Accepted

Decision:

The Jarvis Promise is shown exactly once during the first launch of a new installation.

Reason:

It establishes trust and introduces Jarvis's values.

---

## Decision 006

Title:
Voice

Status:
Accepted

Decision:

Jarvis will have its own original voice and speech style.

It may be inspired by the feeling of a trusted cinematic AI assistant, but it will never imitate or copy another character.

Reason:

Jarvis should develop its own identity.

---

## Decision 007

Title:
Engineering Workflow

Status:
Accepted

Decision:

Every milestone must leave Jarvis in a working state.

Every significant feature is tested before moving to the next milestone.

Reason:

Reduce regressions and simplify debugging.

---

## Decision 008

Title:
Theme System

Status:
Accepted

Decision:

Visual constants belong in Theme.

Widgets should not contain hard-coded colours, fonts or spacing.

Reason:

Consistency and maintainability.