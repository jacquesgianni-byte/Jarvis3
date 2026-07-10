# Known Issues

## Desktop Alpha

### Memory

Status: Open

Description

Memory currently only recognises specific phrases such as:

remember coffee

It does not yet understand more natural language such as:

remember my drink is coffee

Priority

Medium

Reason

Does not block Alpha development.
Will be improved when the Natural Language Understanding system is expanded.
"""
Windows SAPI Note

Although pyttsx3 supports reusing an Engine instance,
Windows SAPI has been observed to stop speaking after
the first runAndWait() call when reused.

To ensure reliable behaviour, this provider creates
a fresh engine for each speech request.

This behaviour is intentionally isolated to the
SystemTTSProvider and does not affect other providers.
"""
## Voice – Windows SAPI (pyttsx3)

### Status
Resolved

### Issue
Reusing a pyttsx3 Engine instance on Windows SAPI may result in only the first
speech request being spoken. Subsequent calls to runAndWait() can become
unreliable.

### Resolution
SystemTTSProvider creates a new pyttsx3 Engine for each speech request.

### Scope
This workaround is isolated to SystemTTSProvider and does not affect the
VoiceManager, VoiceWorker, or VoiceProvider architecture.