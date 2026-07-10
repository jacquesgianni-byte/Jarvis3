# Jarvis OS - AI Development Guide

Version: 1.0
Status: Active

---

# Mission

Jarvis OS is a privacy-first AI Operating System designed to provide a natural, intelligent, and personal computing experience across multiple platforms.

The long-term vision is one shared AI Core that powers:

- Windows
- Android
- iPhone
- Optional Cloud Services

Jarvis should feel like a trusted companion rather than just another chatbot.

---

# Development Philosophy

Build once.
Build properly.

Prefer architecture over shortcuts.

Prefer maintainability over cleverness.

Prefer simplicity over complexity.

Every change should make Jarvis easier to extend.

---

# Core Principles

## 1. Privacy First

User data belongs to the user.

Cloud services are optional.

Jarvis must always be capable of running locally.

---

## 2. Modular Architecture

Every component should have one responsibility.

Examples:

Agent
Router
Skills
Services
Memory
Tools

Each module should be independently testable.

---

## 3. Separation of Responsibilities

Agent orchestrates.

Router detects intent.

Normalizer understands human input.

Skills perform actions.

Services provide capabilities.

Memory stores information.

Tools interact with external systems.

---

## 4. Stable Architecture

Avoid unnecessary rewrites.

Improve architecture only when there is a clear long-term benefit.

Every milestone should leave Jarvis in a working state.

---

# Coding Standards

Use clear names.

Avoid unnecessary complexity.

Prefer readability over clever code.

Keep files focused on one responsibility.

Always include module docstrings.

Always include class docstrings where appropriate.

---

# Skills

Skills perform user-facing actions.

Examples:

GreetingSkill

IdentitySkill

MemorySkill

ToolSkill

Future Skills:

CalendarSkill

WeatherSkill

BluetoothSkill

CameraSkill

EmailSkill

ShoppingSkill

Skills should never contain unrelated functionality.

---

# Services

Services provide reusable system capabilities.

Examples:

ThemeService

VoiceService

PersonalityService

ProfileService

AppearanceService

Services should be reusable by Desktop, Android, Voice and future interfaces.

---

# Memory

Memory should remain independent of Skills.

Skills request information from Memory.

Memory does not depend on Skills.

---

# User Interface

The user interface should never contain business logic.

Desktop

Android

Web

Voice

should all communicate with the same Jarvis Core.

---

# Testing

Every milestone must be tested.

Jarvis must always start successfully.

Regression testing should be performed before marking a milestone complete.

---

# Refactoring Rules

Refactor only when:

- Architecture improves
- Maintainability improves
- Readability improves
- Scalability improves

Do not rewrite code simply because another approach exists.

---

# AI Collaboration

ChatGPT serves as the Architecture Lead.

Claude may assist with implementation, documentation, UI development, boilerplate, and testing.

All architecture changes must be reviewed before being merged.

Every AI contributor should follow this guide.

---

# Definition of Done

A milestone is complete only when:

- Code is reviewed.
- Jarvis starts successfully.
- Features are tested.
- No regressions are introduced.
- Documentation is updated.

---

# Long-Term Vision

Jarvis OS is not being built as a chatbot.

It is being built as an AI Operating System.

Every architectural decision should support that vision.